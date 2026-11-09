"""小水 Agent 核心逻辑回归测试（只用标准库 unittest，无需安装依赖）。

运行：
    python -m unittest discover -s tests -v
    # 或在项目根目录
    python tests/test_core.py -v

设计原则：不联网、不依赖真实 Key —— 所有外部调用（LLM / 高德）都用假函数替换，
只验证「路由判断」「解析容错」「缓存」「去重排序」「兜底」这些纯逻辑。
改提示词或路由规则后跑一遍，能立刻发现是否把正常问法判错了。
"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "agents", "mall-agent"))

import _core  # noqa: E402


def make_env():
    return {
        "api_key": "test-key",
        "base_url": "http://test.local/v1",
        "model": "test-model",
        "vision_model": "test-vision",
        "vision_base_url": "http://test.local/v1",
        "vision_api_key": "test-key",
        "amap_key": "test-amap",
    }


def fake_poi(name="测试地点", rating="4.5", ptype="风景名胜", cat_lng=116.4):
    return {
        "name": name, "address": "测试地址", "type": ptype,
        "rating": rating, "cost": "", "lng": cat_lng, "lat": 39.9,
    }


class TestQuickIntent(unittest.TestCase):
    """规则快速通道：命中要准，拿不准必须交回模型。"""

    def test_city_plus_single_category(self):
        cases = {
            "北京有什么好吃的": ("food", "北京"),
            "上海商场": ("shopping", "上海"),
            "成都酒店": ("hotel", "成都"),
            "深圳景点": ("sightseeing", "深圳"),
            "帮我安排北京一日游": ("plan", "北京"),
        }
        for text, (intent, city) in cases.items():
            with self.subTest(text=text):
                got = _core._quick_intent(text)
                self.assertIsNotNone(got, f"应命中规则: {text}")
                self.assertEqual(got["intent"], intent)
                self.assertEqual(got["city"], city)

    def test_ambiguous_goes_to_llm(self):
        # 对比 / 带预算 / 多品类 / 无城市 / 长句，都应返回 None 交给模型
        for text in ["北京故宫和景山哪个好", "帮我找个5000以内的相机",
                     "你好呀", "北京有什么好玩的还能吃饭逛街", ""]:
            with self.subTest(text=text):
                self.assertIsNone(_core._quick_intent(text), f"不该命中规则: {text}")


class TestParseJson(unittest.TestCase):
    """模型输出不可控，解析要能扛住代码块围栏 / 前后废话 / 坏 JSON。"""

    def test_plain_json(self):
        self.assertEqual(_core._parse_json('{"a": 1}'), {"a": 1})

    def test_fenced_json(self):
        self.assertEqual(_core._parse_json('```json\n{"a": 2}\n```'), {"a": 2})

    def test_json_with_prose(self):
        got = _core._parse_json('好的，结果如下：{"intent": "food"} 希望有帮助')
        self.assertEqual(got.get("intent"), "food")

    def test_broken_json(self):
        self.assertEqual(_core._parse_json("完全不是 JSON"), {})


class TestCache(unittest.TestCase):
    def setUp(self):
        _core._CACHE.clear()

    def test_hit_and_miss(self):
        self.assertIsNone(_core._cache_get("k"))
        _core._cache_set("k", "v", 60)
        self.assertEqual(_core._cache_get("k"), "v")

    def test_expiry(self):
        _core._cache_set("k", "v", 0.01)
        time.sleep(0.05)
        self.assertIsNone(_core._cache_get("k"))

    def test_amap_search_cached(self):
        calls = {"n": 0}

        def counting_get(url, params, timeout):
            calls["n"] += 1
            return 200, ('{"status":"1","pois":[{"name":"故宫博物院",'
                         '"location":"116.397,39.916","type":"风景名胜","address":"东城区"}]}')

        original = _core._get_json
        _core._get_json = counting_get
        try:
            first = _core._amap_search(make_env(), "北京", "故宫", 4)
            second = _core._amap_search(make_env(), "北京", "故宫", 4)
        finally:
            _core._get_json = original

        self.assertEqual(calls["n"], 1, "第二次查询应命中缓存，不再打高德")
        self.assertEqual(len(first), 1)
        self.assertEqual([p["name"] for p in second], ["故宫博物院"])


class TestRankPoints(unittest.TestCase):
    def test_dedup_keeps_best_rating(self):
        pts = [fake_poi("A", "4.5"), fake_poi("A", "4.9"), fake_poi("B", "4.2")]
        got = _core._rank_points(pts)
        self.assertEqual([p["name"] for p in got], ["A", "B"])
        self.assertEqual(got[0]["rating"], "4.9")

    def test_sorted_by_rating_desc(self):
        pts = [fake_poi("A", "4.1"), fake_poi("B", "4.8"), fake_poi("C", "")]
        got = _core._rank_points(pts)
        self.assertEqual([p["name"] for p in got], ["B", "A", "C"])

    def test_empty(self):
        self.assertEqual(_core._rank_points([]), [])


class TestSearchMany(unittest.TestCase):
    def setUp(self):
        _core._CACHE.clear()

    def test_concurrent_keeps_order(self):
        def slow(env, city, kw, limit=8):
            time.sleep(0.2)
            return [fake_poi(kw)]

        original = _core._amap_search
        _core._amap_search = slow
        try:
            plan = [("美食", "food"), ("购物", "shopping"),
                    ("景点", "sightseeing"), ("酒店", "hotel")]
            started = time.time()
            out = list(_core._search_many(make_env(), "北京", plan))
            elapsed = time.time() - started
        finally:
            _core._amap_search = original

        self.assertEqual([kw for kw, _, _ in out], ["美食", "购物", "景点", "酒店"])
        self.assertLess(elapsed, 0.6, "4 个 0.2s 的查询应并发完成（<0.6s）")

    def test_fallback_stops_early(self):
        calls = []

        def first_empty(env, city, kw, limit=8):
            calls.append(kw)
            return [] if kw == "美食" else [fake_poi(kw, "4.6", "餐饮服务;中餐厅")]

        original = _core._amap_search
        _core._amap_search = first_empty
        try:
            plan = [("美食", "food"), ("购物", "shopping")]
            for kw, _cat, pois in _core._search_many(make_env(), "北京", plan,
                                                    stop_when_found=True):
                if pois:
                    break
        finally:
            _core._amap_search = original
        self.assertEqual(calls, ["美食", "购物"], "兜底应串行且命中即停")


class TestRunFallbacks(unittest.TestCase):
    """整条链路：外部全挂也要给出人能看懂的回复，不能抛异常。"""

    def setUp(self):
        _core._CACHE.clear()
        _core._AMAP_LAST_ERR[0] = ""

    def test_amap_key_error_message(self):
        _core._chat = lambda *a, **k: "文本回复"
        _core._amap_search = lambda *a, **k: []
        _core._AMAP_LAST_ERR[0] = "10009"
        got = _core.run(make_env(), "北京有什么好吃的")
        self.assertIn("Key", got["reply"])
        self.assertEqual(got["points"], [])

    def test_llm_failure_returns_message(self):
        def boom(*a, **k):
            raise RuntimeError("模型挂了")

        original = _core._chat
        _core._chat = boom
        try:
            got = _core.run(make_env(), "随便聊聊今天天气怎么样呀朋友")
        finally:
            _core._chat = original
        self.assertIn("模型调用失败", got["reply"])

    def test_low_confidence_spot_hint(self):
        _core.recognize_spot = lambda env, img: {
            "found": True, "name": "故宫博物院", "city": "北京",
            "landmark_type": "古建筑", "description": "红墙金瓦", "confidence": 0.4,
        }
        _core._chat = lambda *a, **k: "这是故宫博物院"
        _core._amap_search = lambda *a, **k: [fake_poi("故宫博物院", "4.9")]
        got = _core.run(make_env(), "", image="data:image/jpeg;base64,xx")
        self.assertIn("认错了", got["reply"])
        self.assertEqual(got["spot"]["name"], "故宫博物院")


if __name__ == "__main__":
    unittest.main(verbosity=2)
