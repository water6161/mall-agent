import os
import json
from dotenv import load_dotenv

load_dotenv()

import httpx
from langchain_core.tools import tool


def _get_amap_key():
    return os.getenv("AMAP_KEY", "")


def _city_location(city: str) -> str | None:
    key = _get_amap_key()
    if not key:
        return None
    try:
        r = httpx.get(
            "https://restapi.amap.com/v3/geocode/geo",
            params={"key": key, "address": city},
            timeout=10,
        )
        data = r.json()
        if data.get("status") == "1" and data.get("geocodes"):
            return data["geocodes"][0]["location"]
    except Exception:
        pass
    return None


def _text_search(city: str, keyword: str, offset: int = 10) -> list:
    key = _get_amap_key()
    if not key:
        return []
    try:
        r = httpx.get(
            "https://restapi.amap.com/v3/place/text",
            params={
                "key": key, "keywords": keyword, "city": city,
                "citylimit": "true", "output": "json", "offset": offset,
            },
            timeout=10,
        )
        data = r.json()
        if data.get("status") == "1":
            return data.get("pois", [])
    except Exception:
        pass
    return []


@tool
def search_nearby_malls(city: str, keyword: str = "商场", radius: int = 5000) -> str:
    """根据城市名称搜索附近的商场/购物中心 POI 信息。

    Args:
        city: 城市名称，例如 "北京"、"上海"、"深圳"
        keyword: 搜索关键词，默认 "商场"，可选 "购物中心"、"购物广场" 等
        radius: 搜索半径（米），默认 5000

    Returns:
        匹配的商场列表 JSON 字符串
    """
    key = _get_amap_key()
    if not key:
        return json.dumps({"error": "AMAP_KEY 未配置"}, ensure_ascii=False)

    pois = _text_search(city, keyword)
    malls = []
    for poi in pois:
        biz = poi.get("biz_ext") or {}
        malls.append({
            "name": poi.get("name"),
            "address": poi.get("address"),
            "tel": poi.get("tel") or None,
            "type": poi.get("type"),
            "rating": biz.get("rating") or None,
            "cost": biz.get("cost") or None,
            "location": poi.get("location"),
        })

    if not malls:
        return json.dumps({"message": f"在 {city} 未找到相关商场"}, ensure_ascii=False)
    return json.dumps({"malls": malls}, ensure_ascii=False)


@tool
def search_hotels(city: str, keyword: str = "酒店") -> str:
    """搜索城市内的酒店、住宿信息。

    Args:
        city: 城市名称
        keyword: 搜索关键词，默认 "酒店"，可选 "民宿"、"五星酒店"、"青年旅舍" 等

    Returns:
        酒店列表 JSON 字符串，含名称、地址、价格、评分
    """
    key = _get_amap_key()
    if not key:
        return json.dumps({"error": "AMAP_KEY 未配置"}, ensure_ascii=False)

    pois = _text_search(city, keyword)
    hotels = []
    for poi in pois:
        biz = poi.get("biz_ext") or {}
        hotels.append({
            "name": poi.get("name"),
            "address": poi.get("address"),
            "tel": poi.get("tel") or None,
            "rating": biz.get("rating") or None,
            "cost": biz.get("cost") or None,
            "type": poi.get("type"),
            "location": poi.get("location"),
        })

    if not hotels:
        return json.dumps({"message": f"在 {city} 未找到相关酒店"}, ensure_ascii=False)
    return json.dumps({"hotels": hotels}, ensure_ascii=False)


@tool
def search_sightseeing(city: str, keyword: str = "景点") -> str:
    """搜索城市内的旅游景点、地标、公园等。

    Args:
        city: 城市名称
        keyword: 搜索关键词，默认 "景点"，可选 "公园"、"博物馆"、"地标"、"古镇" 等

    Returns:
        景点列表 JSON 字符串，含名称、地址、类型
    """
    key = _get_amap_key()
    if not key:
        return json.dumps({"error": "AMAP_KEY 未配置"}, ensure_ascii=False)

    pois = _text_search(city, keyword)
    spots = []
    for poi in pois:
        biz = poi.get("biz_ext") or {}
        spots.append({
            "name": poi.get("name"),
            "address": poi.get("address"),
            "type": poi.get("type"),
            "rating": biz.get("rating") or None,
            "location": poi.get("location"),
        })

    if not spots:
        return json.dumps({"message": f"在 {city} 未找到相关景点"}, ensure_ascii=False)
    return json.dumps({"sightseeing": spots}, ensure_ascii=False)


@tool
def plan_route(origin: str, destination: str, city: str = "", mode: str = "transit") -> str:
    """路线规划：查询从起点到终点的交通方案。

    Args:
        origin: 起点地名，例如 "深圳北站"
        destination: 终点地名，例如 "万象天地"
        city: 起点所在城市
        mode: 出行方式，可选 transit(公交/地铁) / driving(驾车) / walking(步行)，默认 transit

    Returns:
        路线方案 JSON 字符串
    """
    key = _get_amap_key()
    if not key:
        return json.dumps({"error": "AMAP_KEY 未配置"}, ensure_ascii=False)

    try:
        origin_loc = None
        dest_loc = None

        if city:
            origin_loc = _city_location(f"{city}{origin}")
            dest_loc = _city_location(f"{city}{destination}")
        else:
            origin_loc = _city_location(origin)
            dest_loc = _city_location(destination)

        if not origin_loc or not dest_loc:
            return json.dumps({"error": f"无法解析起点/终点: {origin} -> {destination}"}, ensure_ascii=False)

        mode_map = {"transit": "transit/integrated", "driving": "direction/driving", "walking": "direction/walking"}
        api = mode_map.get(mode, "transit/integrated")

        r = httpx.get(
            f"https://restapi.amap.com/v3/{api}",
            params={
                "key": key,
                "origin": origin_loc,
                "destination": dest_loc,
                "city": city,
                "output": "json",
            },
            timeout=10,
        )
        data = r.json()
        if data.get("status") != "1":
            return json.dumps({"error": "路线查询失败", "info": data.get("info")}, ensure_ascii=False)

        result = {"origin": origin, "destination": destination, "mode": mode}

        if mode == "transit":
            routes = []
            for plan in (data.get("route") or {}).get("transits", [])[:3]:
                steps = []
                for seg in plan.get("segments", []):
                    bus_info = seg.get("bus", {}) or {}
                    lines = bus_info.get("buslines", []) or []
                    for line in lines:
                        steps.append(f"{line.get('name', '')} {line.get('departure_stop', {}).get('name', '')} → {line.get('arrival_stop', {}).get('name', '')}")
                    walking = seg.get("walking", {}) or {}
                    if walking:
                        steps.append(f"步行 {walking.get('distance', '?')}米")
                routes.append({
                    "duration": plan.get("duration"),
                    "distance": plan.get("distance"),
                    "steps": steps,
                })
            result["routes"] = routes
        else:
            paths = (data.get("route") or {}).get("paths", []) or []
            result["paths"] = [
                {
                    "duration": p.get("duration"),
                    "distance": p.get("distance"),
                    "steps": [s.get("instruction", "") for s in p.get("steps", [])[:5]],
                }
                for p in paths[:3]
            ]

        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"error": f"路线查询异常: {str(e)}"}, ensure_ascii=False)


ALL_TOOLS = [search_nearby_malls, search_hotels, search_sightseeing, plan_route]
