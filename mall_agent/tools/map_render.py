"""地图可视化

配了 AMAP_JS_KEY（Web端 JS API 类型 Key）时渲染高德交互式地图；
否则用高德 staticmap 静态图（复用 Web 服务 Key）自动兜底。
"""

import os
import io
import json
import base64

import httpx

CATEGORY_COLORS = {
    "shopping": "#FF6B6B",
    "hotel": "#4D96FF",
    "sightseeing": "#2BB673",
}
CATEGORY_LABELS = {
    "shopping": "商场",
    "hotel": "酒店",
    "sightseeing": "景点",
}
STATIC_LIMIT = 12
JS_LIMIT = 60


def extract_points(mall_results: str = "", hotel_results: str = "",
                   sight_results: str = "") -> list[dict]:
    """从各工具返回的 JSON 字符串中提取带经纬度的点。"""
    sources = [
        (mall_results, "shopping", "malls"),
        (hotel_results, "hotel", "hotels"),
        (sight_results, "sightseeing", "sightseeing"),
    ]
    points: list[dict] = []
    for raw, category, arr_key in sources:
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        for item in data.get(arr_key) or []:
            loc = item.get("location")
            if not loc or "," not in str(loc):
                continue
            try:
                lng_str, lat_str = str(loc).split(",")[:2]
                lng, lat = float(lng_str), float(lat_str)
            except ValueError:
                continue
            points.append({
                "name": item.get("name") or "未命名",
                "lng": lng,
                "lat": lat,
                "category": category,
                "address": item.get("address") or "",
            })
    return points


def _legend_html() -> str:
    items = "".join(
        f'<span class="lg-item"><i style="background:{color}"></i>{CATEGORY_LABELS[cat]}</span>'
        for cat, color in CATEGORY_COLORS.items()
    )
    return f'<div class="map-legend">{items}</div>'


def _static_map_url(points: list[dict]) -> str:
    key = os.getenv("AMAP_KEY", "")
    groups: dict[str, list[dict]] = {}
    for p in points[:STATIC_LIMIT]:
        groups.setdefault(p["category"], []).append(p)

    marker_strs = []
    labels = "ABCDEFGHIJKL"
    idx = 0
    for cat, pts in groups.items():
        color = CATEGORY_COLORS[cat].replace("#", "0x")
        locs = []
        for j, p in enumerate(pts):
            if j == 0:
                locs.append(f"{labels[idx]}:{p['lng']},{p['lat']}")
            else:
                locs.append(f"{p['lng']},{p['lat']}")
            idx += 1
        marker_strs.append(f"mid,{color}," + ";".join(locs))
    # 多个样式组用 | 分隔（%7C）
    markers = "%7C".join(marker_strs)

    lngs = [p["lng"] for p in points]
    lats = [p["lat"] for p in points]
    center = f"{sum(lngs)/len(lngs)},{sum(lats)/len(lats)}"

    return (
        "https://restapi.amap.com/v3/staticmap"
        f"?key={key}&location={center}&zoom=12&size=1024*360&scale=2"
        f"&markers={markers}"
    )


def _fetch_static_data_uri(points: list[dict]) -> str:
    """服务端取静态地图并转压缩 JPEG data URI，避免浏览器跨域 ORB 拦截。"""
    url = _static_map_url(points)
    r = httpx.get(url, timeout=30)
    r.raise_for_status()
    raw = r.content

    try:
        from PIL import Image
        with Image.open(io.BytesIO(raw)) as im:
            im = im.convert("RGB")
            if im.width > 1600:
                ratio = 1600 / im.width
                im = im.resize((1600, max(1, int(im.height * ratio))), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=82)
            raw = buf.getvalue()
    except ImportError:
        pass

    mime = "image/jpeg" if raw[:3] == b"\xff\xd8\xff" else "image/png"
    return f"data:{mime};base64," + base64.b64encode(raw).decode()


def _build_static_html(points: list[dict]) -> str:
    tip = f"共 {len(points)} 个结果（地图展示前 {min(len(points), STATIC_LIMIT)} 个）"
    try:
        data_uri = _fetch_static_data_uri(points)
        img_tag = f'<img src="{data_uri}" alt="地图" />'
    except Exception as e:
        img_tag = f'<div class="map-error">静态地图加载失败：{str(e)[:120]}</div>'
    return f"""
    <div class="map-wrap static-map">
      {img_tag}
      <div class="map-tip">{tip}　如需交互地图可配置高德 JS Key</div>
      {_legend_html()}
    </div>
    """


def _build_js_html(points: list[dict]) -> str:
    js_key = os.getenv("AMAP_JS_KEY", "")
    security = os.getenv("AMAP_SECURITY_CODE", "")
    data = json.dumps(
        [
            {
                "name": p["name"], "lng": p["lng"], "lat": p["lat"],
                "color": CATEGORY_COLORS.get(p["category"], "#999"),
                "address": p["address"],
                "label": CATEGORY_LABELS.get(p["category"], ""),
            }
            for p in points[:JS_LIMIT]
        ],
        ensure_ascii=False,
    )
    return f"""
    <div class="map-wrap">
      <div id="xiaotu-map"></div>
      <div class="map-tip">共 {len(points)} 个结果 · 点击标记查看详情</div>
      {_legend_html()}
    </div>
    <script>
    window._AMapSecurityConfig = {{ securityJsCode: "{security}" }};
    (function() {{
      var points = {data};
      function initMap() {{
        var map = new AMap.Map('xiaotu-map', {{ zoom: 12, viewMode: '2D' }});
        var markers = points.map(function(p, i) {{
          var marker = new AMap.Marker({{
            position: [p.lng, p.lat],
            offset: new AMap.Pixel(-14, -34),
            content: '<div class="amap-pin" style="background:' + p.color + '">'
                   + String.fromCharCode(65 + (i > 25 ? 25 : i)) + '</div>',
            title: p.name
          }});
          marker.on('click', function() {{
            new AMap.InfoWindow({{
              offset: new AMap.Pixel(0, -36),
              content: '<div class="amap-info"><b>' + p.name + '</b>'
                     + '<br><span>' + (p.label || '') + '</span>'
                     + '<br>' + (p.address || '') + '</div>'
            }}).open(map, [p.lng, p.lat]);
          }});
          return marker;
        }});
        map.add(markers);
        map.setFitView(markers, false, [40, 40, 60, 40]);
      }}
      var s = document.createElement('script');
      s.src = 'https://webapi.amap.com/maps?v=2.0&key={js_key}&plugin=AMap.Scale,AMap.ToolBar';
      s.onload = initMap;
      s.onerror = function() {{
        document.getElementById('xiaotu-map').innerHTML
          = '<div class="map-error">地图加载失败，请检查 JS Key / 安全密钥配置</div>';
      }};
      document.head.appendChild(s);
    }})();
    </script>
    """


def build_map_html(points: list[dict]) -> str:
    if not points:
        return '<div class="map-empty">🗺️ 查询到的地点会标注在这里</div>'
    if os.getenv("AMAP_JS_KEY"):
        return _build_js_html(points)
    return _build_static_html(points)
