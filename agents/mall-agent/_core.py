"""小水 Agent 核心逻辑（与运行时解耦，方便本地直接测试）。

只依赖 Python 标准库（urllib），无需在构建阶段安装第三方包：
- LLM 走 OpenAI 兼容协议（DashScope / Makers 内置模型网关均可）
- 地点数据走高德 Web 服务 API
- 景点识别走视觉模型（qwen3-vl 等）

不落盘、不依赖数据库，适配 EdgeOne Makers 的无状态/短会话运行方式。
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE_URL = "https://ai-gateway.edgeone.link/v1"
DEFAULT_MODEL = "@makers/deepseek-v4-flash"
DEFAULT_VISION_MODEL = "qwen3-vl-plus"

TIMEOUT = 45


# ─── HTTP（标准库） ─────────────────────────────────────────

def _send(req, timeout: int):
    """发请求，返回 (status, text)。HTTP 错误码也当正常返回处理。"""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore")


def _post_json(url: str, payload: dict, headers: dict, timeout: int):
    data = json.dumps(payload).encode("utf-8")
    return _send(urllib.request.Request(url, data=data, headers=headers, method="POST"), timeout)


def _get_json(url: str, params: dict, timeout: int):
    full = url + "?" + urllib.parse.urlencode(params)
    return _send(urllib.request.Request(full, method="GET"), timeout)

CATEGORY_LABEL = {"shopping": "商场", "hotel": "酒店", "sightseeing": "景点"}

# 搜索基础词（用户偏好是"高端/性价比"这类形容词时不能直接拿去当地点关键词）
CATEGORY_BASE = {"shopping": "购物中心", "hotel": "酒店", "sightseeing": "景点"}
GENERIC_PREFS = {
    "高端", "性价比", "性价比高", "便宜", "实惠", "豪华", "奢华", "亲子", "网红",
    "小众", "安静", "舒适", "好玩", "热门", "特色", "高评分", "有特色",
}
# 结果类型过滤，避免"高端"搜出一堆停车场、餐厅被当成酒店
TYPE_KEYWORDS = {
    "shopping": ("购物", "商场", "超市", "商业", "百货"),
    "hotel": ("住宿", "酒店", "宾馆", "旅馆", "民宿", "客栈"),
    "sightseeing": ("风景名胜", "公园", "博物馆", "景点", "纪念", "宗教", "游乐", "动物园", "植物园"),
}

INTENT_PROMPT = """你是"小水"，一个出行决策助手。判断用户这句话的意图，严格输出 JSON，不要输出任何其他文字：
{
  "intent": "shopping|hotel|sightseeing|route|spot|chat|discover",
  "city": "城市名，没有则为 null；只说了城市名（如"深圳"）时 intent 填 discover",
  "preference": "偏好关键词，如 高端/亲子/性价比，没有则为 null"
}
规则：找商场=shopping，找酒店=hotel，找景点=sightseeing，问路线=route，上传图片=spot，打招呼闲聊=chat，只给城市名=discover。"""

REPLY_PROMPT = """你是"小水"，一个亲切的出行决策助手。根据工具查到的真实地点数据，用口语化中文回答用户，像朋友推荐一样。

要求：
- 只能推荐数据里出现过的地点，绝对不能补充数据之外的地点，绝不编造地址、价格、评分
- 直接给结论，不要说"根据工具返回的数据"
- 推荐时说清楚为什么推荐（评分、类型、位置等数据里有才说）
- 控制在 260 字以内，可以用少量条目列表
- 如果数据明显不匹配用户需求，就直说没找到合适的，并建议换个关键词
- 不要用机械的开场白"""

SPOT_PROMPT = """识别这张照片里的景点或地标。严格输出 JSON，不要输出其他文字：
{
  "found": true/false,
  "name": "景点/地标正式名称，没认出来则为 null",
  "city": "所在城市，不确定则为 null",
  "landmark_type": "类型，如 古建筑/自然风光/城市地标",
  "description": "一句话说明画面关键特征，30字以内"
}
画面里没有可识别景点时 found 填 false。"""


# ─── 环境 ───────────────────────────────────────────────────

def resolve_env(env: dict | None = None) -> dict:
    """合并运行时上下文与进程环境变量。"""
    env = dict(env or {})

    def get(name: str) -> str:
        value = env.get(name)
        if value:
            return str(value)
        import os
        return os.getenv(name, "") or ""

    api_key = get("OPENAI_API_KEY") or get("AI_GATEWAY_API_KEY") or get("MAKERS_MODELS_KEY")
    base_url = get("OPENAI_BASE_URL") or get("AI_GATEWAY_BASE_URL") or DEFAULT_BASE_URL
    model = get("OPENAI_MODEL") or get("AI_GATEWAY_MODEL") or DEFAULT_MODEL
    vision = get("VISION_MODEL") or DEFAULT_VISION_MODEL
    # 视觉模型支持独立网关：未配置 VISION_BASE_URL 时沿用主 base_url
    vision_base_url = get("VISION_BASE_URL") or base_url
    vision_api_key = get("VISION_API_KEY") or api_key

    return {
        "api_key": api_key,
        "base_url": base_url.rstrip("/"),
        "model": model,
        "vision_model": vision,
        "vision_base_url": vision_base_url.rstrip("/"),
        "vision_api_key": vision_api_key,
        "amap_key": get("AMAP_KEY"),
    }


# ─── LLM ───────────────────────────────────────────────────

def _chat(env: dict, messages: list, model: str | None = None,
          temperature: float = 0.3) -> str:
    if not env.get("api_key"):
        raise RuntimeError("未配置 OPENAI_API_KEY")

    body = {
        "model": model or env["model"],
        "temperature": temperature,
        "messages": messages,
    }
    status, text = _post_json(
        env["base_url"] + "/chat/completions",
        body,
        {
            "Authorization": f"Bearer {env['api_key']}",
            "Content-Type": "application/json",
        },
        TIMEOUT,
    )
    if status != 200:
        raise RuntimeError(f"模型返回 {status}：{text[:160]}")

    choices = json.loads(text).get("choices") or []
    content = choices[0].get("message", {}).get("content", "") if choices else ""
    if isinstance(content, list):
        content = "".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
    return content or ""


def _parse_json(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return {}


# ─── 高德 ───────────────────────────────────────────────────

def _amap_search(env: dict, city: str, keyword: str, limit: int = 8) -> list:
    key = env.get("amap_key")
    if not key or not city:
        return []
    try:
        status, text = _get_json(
            "https://restapi.amap.com/v3/place/text",
            {
                "key": key, "keywords": keyword, "city": city,
                "citylimit": "true", "output": "json", "offset": limit,
            },
            20,
        )
        if status != 200:
            return []
        data = json.loads(text)
    except (urllib.error.URLError, ValueError):
        return []

    if data.get("status") != "1":
        return []

    pois = []
    for poi in data.get("pois") or []:
        loc = poi.get("location") or ""
        if "," not in loc:
            continue
        try:
            lng, lat = [float(x) for x in loc.split(",")[:2]]
        except ValueError:
            continue
        biz = poi.get("biz_ext") or {}
        address = poi.get("address")
        rating = biz.get("rating")
        cost = biz.get("cost")
        pois.append({
            "name": poi.get("name") or "",
            "address": address if isinstance(address, str) else "",
            "type": poi.get("type") or "",
            "rating": rating if isinstance(rating, str) and rating else "",
            "cost": cost if isinstance(cost, str) and cost not in ("0", "0.00") else "",
            "lng": lng,
            "lat": lat,
        })
    return pois


def _filter_pois(pois: list, category: str) -> list:
    keys = TYPE_KEYWORDS.get(category, ())
    if not keys:
        return pois
    return [p for p in pois if any(k in (p.get("type") or "") for k in keys)]


def _keyword(preference: str, category: str) -> str:
    base = CATEGORY_BASE.get(category, "景点")
    if preference and preference not in GENERIC_PREFS and len(preference) <= 8:
        return preference + base
    return base


def _need_more_city_reply(city_keyword: str) -> str:
    return f"你想在哪个城市找{city_keyword}呀？告诉我城市名，我马上帮你查～"


def _poi_digest(points: list) -> str:
    rows = []
    for p in points[:10]:
        bits = [p["name"], CATEGORY_LABEL.get(p.get("category", ""), ""), p.get("address") or ""]
        if p.get("rating"):
            bits.append(f"评分{p['rating']}")
        rows.append(" | ".join(b for b in bits if b))
    return "\n".join(rows)


# ─── 景点识别 ───────────────────────────────────────────────

def recognize_spot(env: dict, image_data_uri: str) -> dict:
    if not env.get("api_key"):
        raise RuntimeError("未配置 OPENAI_API_KEY")
    body = {
        "model": env["vision_model"],
        "temperature": 0.1,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": SPOT_PROMPT},
                {"type": "image_url", "image_url": {"url": image_data_uri}},
            ],
        }],
    }
    status, text = _post_json(
        env["vision_base_url"] + "/chat/completions",
        body,
        {
            "Authorization": f"Bearer {env['vision_api_key']}",
            "Content-Type": "application/json",
        },
        90,
    )
    if status != 200:
        raise RuntimeError(f"视觉模型返回 {status}：{text[:160]}")
    choices = json.loads(text).get("choices") or []
    content = choices[0].get("message", {}).get("content", "") if choices else ""
    if isinstance(content, list):
        content = "".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
    data = _parse_json(content)
    name = data.get("name") or None
    return {
        "found": bool(data.get("found")) and bool(name),
        "name": name,
        "city": data.get("city") or None,
        "landmark_type": data.get("landmark_type") or "",
        "description": data.get("description") or "",
    }


# ─── 主流程 ─────────────────────────────────────────────────

def _history_messages(history: list | None) -> list:
    if not history:
        return []
    out = []
    for item in history[-6:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            out.append({"role": role, "content": content[:1500]})
    return out


def run(env: dict, message: str, history: list | None = None,
        image: str | None = None) -> dict:
    """返回 {reply, points, map_image, spot}。"""
    message = (message or "").strip()
    history_msgs = _history_messages(history)

    if not env.get("api_key"):
        return {
            "reply": "⚠️ 还没有配置模型 Key。请在 Makers 控制台为本项目添加环境变量 "
                     "OPENAI_API_KEY、OPENAI_BASE_URL、OPENAI_MODEL、VISION_MODEL、AMAP_KEY 后重新部署。",
            "points": [],
        }

    # 1) 上传图片 → 识景点 → 高德补全 → 推荐
    if image:
        try:
            spot = recognize_spot(env, image)
        except Exception as e:
            err = str(e)
            # 402 / 额度不足：模型网关没余额了，不是照片问题
            if "402" in err or "quota" in err.lower() or "insufficient" in err.lower():
                reply = (
                    "😵‍💫 图片识别失败了：视觉模型额度不足（402）。\n\n"
                    "这不是照片的问题，是你的大模型网关（百炼/Makers）账户余额不够了，"
                    "去充值或确认 VISION_MODEL 对应的模型有可用额度后再试～"
                )
            elif "401" in err or "403" in err:
                reply = (
                    "😵‍💫 图片识别失败了：视觉模型鉴权失败（401/403）。\n\n"
                    "请检查 API Key 是否正确、VISION_MODEL 这个模型你是否有权限调用。"
                )
            else:
                reply = f"😵‍💫 图片识别失败了：{err[:160]}\n\n换张清晰点的照片再试试～"
            return {"reply": reply, "points": []}

        if not spot["found"]:
            return {"reply": "🔍 这张图里没认出明显的景点或地标。\n"
                             "换一张有建筑、雕像、山水地标特征的清晰照片试试～", "points": []}

        city = spot.get("city") or ""
        pois = _amap_search(env, city, spot["name"], limit=6) if city else []
        points = [dict(p, category="sightseeing") for p in _filter_pois(pois, "sightseeing")]

        context = _poi_digest(points)
        prompt = (
            f"用户上传了一张照片，识别结果：{spot['name']}（{city or '城市未知'}），"
            f"类型 {spot.get('landmark_type') or '未知'}，画面特征：{spot.get('description') or ''}。\n"
            f"高德查到的相关信息：\n{context or '（无）'}\n\n"
            f"请告诉用户这是哪儿，并给出实用游玩建议（开放时间/门票等没查到的不要编）。"
            f"如果高德数据里有同城其他相关景点，可以顺带推荐 1-2 个。"
        )
        try:
            reply = _chat(env, [{"role": "system", "content": REPLY_PROMPT},
                                {"role": "user", "content": prompt}])
        except Exception as e:
            reply = f"认出来了：{spot['name']}（{city or '城市未知'}）" \
                    f"｜{spot.get('landmark_type') or ''}｜{spot.get('description') or ''}\n" \
                    f"（后续推荐没生成成功：{str(e)[:80]}）"

        return {
            "reply": reply,
            "points": [p for p in points if p.get("lng")],
            "map_image": "",
            "spot": spot,
        }

    if not message:
        return {"reply": "在的～想找商场、酒店、景点，还是发张照片让我认认是哪儿？", "points": []}

    # 2) 单次 LLM 判断意图
    try:
        raw = _chat(env, [{"role": "system", "content": INTENT_PROMPT},
                          {"role": "user", "content": message}],
                    temperature=0)
    except Exception as e:
        return {"reply": f"😵‍💫 模型调用失败：{str(e)[:160]}", "points": []}

    data = _parse_json(raw) or {}
    intent = data.get("intent") or "chat"
    city = data.get("city") or ""
    preference = data.get("preference") or ""

    if intent in ("chat", "spot") and not city:
        try:
            reply = _chat(env, [{"role": "system", "content": REPLY_PROMPT}] + history_msgs
                          + [{"role": "user", "content": message}])
        except Exception as e:
            reply = f"😵‍💫 模型调用失败：{str(e)[:160]}"
        return {"reply": reply, "points": []}

    if intent == "route":
        reply = "路线规划这块我先简化掉了～你可以告诉我起点和终点，我帮你查两地周边值得逛的地方。"
        return {"reply": reply, "points": []}

    # 3) 按意图查高德
    if intent == "discover":
        plan = [(_keyword("", "shopping"), "shopping"),
                (_keyword("", "sightseeing"), "sightseeing"),
                (_keyword("", "hotel"), "hotel")]
    else:
        category = {"shopping": "shopping", "hotel": "hotel", "sightseeing": "sightseeing"}.get(
            intent, "sightseeing")
        plan = [(_keyword(preference, category), category)]

    if not city:
        label = CATEGORY_LABEL.get(plan[0][1], "地点")
        return {"reply": _need_more_city_reply(label), "points": []}

    # 没配置高德 Key 时直接说明，不要误导用户说"关键词太窄"
    if not env.get("amap_key"):
        return {
            "reply": "⚠️ 还没配置高德地图 Key（AMAP_KEY），暂时没法帮你查地点。\n"
                     "请在环境变量里填上 AMAP_KEY（注意类型要选「Web服务」，不要选「Web端(JS API)」）后再试～",
            "points": [],
        }

    points = []
    for kw, cat in plan:
        raw = _amap_search(env, city, kw, limit=8)
        pois = _filter_pois(raw, cat)
        # 类型过滤太严把结果全滤掉时，回退到原始结果，避免有数据却显示"查不到"
        if not pois and raw:
            pois = raw
        for poi in pois[:6]:
            points.append(dict(poi, category=cat))

    # 第一轮没查到时，用更宽泛的基础词再兜底搜一遍
    if not points:
        fallback_plan = [
            (CATEGORY_BASE["shopping"], "shopping"),
            (CATEGORY_BASE["sightseeing"], "sightseeing"),
            (CATEGORY_BASE["hotel"], "hotel"),
        ] if intent == "discover" else [(CATEGORY_BASE.get(plan[0][1], "景点"), plan[0][1])]
        for kw, cat in fallback_plan:
            raw = _amap_search(env, city, kw, limit=8)
            pois = _filter_pois(raw, cat)
            if not pois and raw:
                pois = raw
            for poi in pois[:6]:
                points.append(dict(poi, category=cat))
            if points:
                break

    if not points:
        return {
            "reply": f"在「{city}」暂时没查到相关地点。可能是地图服务暂时不可用，"
                     f"你可以换个更具体的关键词（比如「万象城」「故宫」「如家酒店」）再试试～",
            "points": [],
        }

    # 4) 生成推荐
    prompt = (
        f"用户的话：{message}\n城市：{city}\n"
        f"高德查到这些地点（名称 | 类型 | 地址 | 评分）：\n{_poi_digest(points)}\n\n"
        f"从中挑选最合适的 4-6 个推荐给用户，说清楚推荐理由。"
    )
    try:
        reply = _chat(env, [{"role": "system", "content": REPLY_PROMPT}] + history_msgs
                      + [{"role": "user", "content": prompt}])
    except Exception as e:
        names = "、".join(p["name"] for p in points[:5])
        reply = f"给你找到这些：{names}\n（详细推荐没生成成功：{str(e)[:80]}）"

    return {
        "reply": reply,
        "points": points[:20],
        "map_image": "",
    }
