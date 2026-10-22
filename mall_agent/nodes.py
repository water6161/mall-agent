import os
import re
import json
import base64

import httpx
from openai import OpenAIError
from dotenv import load_dotenv

load_dotenv()

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI

from .state import AgentState
from .tools.amap import ALL_TOOLS, search_nearby_malls, search_hotels, search_sightseeing, plan_route


SYSTEM_PROMPT = """你是一个全能出行决策助手，名叫"小水"。用户会向你咨询各种出行相关的问题，你需要判断用户意图，调用合适的工具获取数据，最后给出清晰、实用的建议。

【你能做的事】
1. shopping    —— 找商场、购物、逛街推荐
2. hotel       —— 找酒店、住宿、性价比筛选
3. sightseeing —— 找景点、旅游目的地、游玩攻略
4. route       —— 路线规划、怎么坐车/打车、交通方案
5. photo_edit  —— AI修图（已上线真实能力）：用户上传照片后，美化调色、换背景、去杂物、生成旅行打卡效果图
6. chat        —— 闲聊、打招呼、问你叫什么
7. discover    —— 用户只说了一个城市/地名、没说要干什么时，主动帮他发现：商场+景点+酒店一起种草推荐

【工作流程】
第一步：判断用户意图属于上面哪一类。
第二步：如果用户没说城市/位置，先问"你在哪个城市呀？"
第三步：调用对应的工具获取真实数据（不要自己编）。
第四步：如果用户说的是综合需求（比如"周末去深圳玩两天"），需要同时调用景点+酒店+路线，最后合并成一份完整攻略。
第五步：用口语化、亲切的语气回答，像朋友推荐一样，不要太官方。

【回答风格】
- 不要说"根据工具返回数据"这种话，直接给结论
- 推荐景点/酒店时，说清楚为什么推荐（评分、距离、特色）
- 路线规划要写清楚：坐几号线、哪站下、大概多久
- 每次回答控制在 300 字以内，重点突出

【禁止事项】
- 不要编造不存在的地址、价格、评分
- 不要推荐你没调用工具查过的地方
- 不要用很机械的开场白"""


INTENT_ROUTE_MAP = {
    "shopping": "search_malls",
    "hotel": "search_hotels",
    "sightseeing": "search_sights",
    "route": "search_route",
    "photo_edit": "photo_edit",
    "chat": "direct_reply",
    "unknown": "direct_reply",
    "discover": "search_multi",
}


def _is_key_configured() -> bool:
    key = os.getenv("OPENAI_API_KEY", "")
    return bool(key) and "your_" not in key


def _get_llm():
    return ChatOpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0.3,
        max_retries=3,
    )


def _get_vision_llm():
    vision_model = os.getenv("VISION_MODEL", "")
    if not vision_model:
        return None
    return ChatOpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        model=vision_model,
        temperature=0.3,
        max_retries=3,
    )


def _encode_image(image_path: str) -> str:
    ext = os.path.splitext(image_path)[1].lower()
    mime = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif",
        ".webp": "image/webp", ".bmp": "image/bmp",
    }.get(ext, "image/jpeg")
    with open(image_path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    return f"data:{mime};base64,{data}"


def _no_key_reply() -> str:
    return (
        "⚠️ 未检测到 API Key 配置\n\n"
        "请在项目根目录创建 `.env` 文件：\n\n"
        "```\nOPENAI_API_KEY=你的key\n"
        "OPENAI_BASE_URL=https://api.openai.com/v1\n"
        "OPENAI_MODEL=gpt-4o-mini\n"
        "AMAP_KEY=你的高德key\n```"
    )


def _status_code(exc: Exception) -> int | None:
    """从异常中提取 HTTP 状态码（兼容 httpx 与 openai 的异常结构）。"""
    response = getattr(exc, "response", None)
    code = getattr(response, "status_code", None)
    if not isinstance(code, int):
        code = getattr(exc, "status_code", None)
    if isinstance(code, int):
        return code
    match = re.search(r"(?:Error code|status_code)[:\s]*(\d{3})", str(exc))
    return int(match.group(1)) if match else None


def _error_reply(exc: Exception) -> str:
    code = _status_code(exc)
    if code == 429:
        return "请求太频繁，请稍后再试。"
    if code == 401:
        return "API Key 无效，请检查 OPENAI_API_KEY 配置。"
    return f"😵‍💫 调用模型失败：{exc}"


# ─── image ──────────────────────────────────────────────────

def analyze_image(state: AgentState) -> AgentState:
    image_path = state.get("user_image")
    if not image_path or not _is_key_configured():
        return {}

    vision_llm = _get_vision_llm()
    if not vision_llm:
        return {"image_desc": None}

    try:
        img_data = _encode_image(image_path)
        human_msg = HumanMessage(content=[
            {"type": "text", "text": "请描述这张图片的内容，特别关注：是否有商场/品牌标志/购物相关场景？用中文简洁描述。"},
            {"type": "image_url", "image_url": {"url": img_data}},
        ])
        resp = vision_llm.invoke([human_msg])
        desc = resp.content if isinstance(resp.content, str) else str(resp.content)
        return {"image_desc": desc}
    except (httpx.HTTPError, OSError, ValueError):
        return {"image_desc": None}


# ─── intent ─────────────────────────────────────────────────

def understand_intent(state: AgentState) -> AgentState:
    if not _is_key_configured():
        return {
            "user_intent": "unknown",
            "final_response": _no_key_reply(),
        }

    try:
        llm = _get_llm()
        messages = list(state["messages"])

        extra_context = []
        docs_text = state.get("user_docs")
        if docs_text:
            extra_context.append(f"用户上传的文档内容（作为偏好参考）：\n{docs_text[:3000]}")
        image_desc = state.get("image_desc")
        if image_desc:
            extra_context.append(f"用户上传图片的描述：{image_desc}")

        context_block = ""
        if extra_context:
            context_block = "\n\n【额外上下文】\n" + "\n".join(extra_context)

        json_schema = """
{
  "intent": "shopping|hotel|sightseeing|route|photo_edit|chat|discover",
  "city": "提取的城市名，没有则为 null。注意：如果用户只发了一个城市/地名（比如"深圳"、"杭州"），intent 必须为 discover，city 填该地名",
  "destination": "目的地城市(比如旅游目标城市)，没有则为 null",
  "route_from": "路线起点，没有则为 null",
  "route_to": "路线终点，没有则为 null",
  "preference": "提取的偏好关键词(如高端、亲子、性价比、潮牌等)，没有则为 null",
  "needs": ["综合需求涉及的意图列表，如同时问景点+酒店就写 sightseeing,hotel"],
  "need_more_city": true/false
}"""

        prompt = SystemMessage(
            content=f"""{SYSTEM_PROMPT}{context_block}

请分析用户最近一条消息，以 JSON 输出（严格按此格式，不要加其他文字）：
{json_schema}"""
        )

        resp = llm.invoke([prompt] + messages)
        raw = resp.content.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {
                "intent": "chat", "city": None, "destination": None,
                "route_from": None, "route_to": None, "preference": None,
                "needs": [], "need_more_city": False,
            }

        intent = data.get("intent", "chat")
        needs = data.get("needs") or []
        if intent == "discover":
            needs = ["shopping", "sightseeing", "hotel"]
        elif not needs and intent not in ("chat", "photo_edit"):
            needs = [intent]

        return {
            "user_intent": intent,
            "user_location": data.get("city"),
            "user_destination": data.get("destination"),
            "user_route_from": data.get("route_from"),
            "user_route_to": data.get("route_to"),
            "user_preference": data.get("preference"),
            "needs": needs,
            "final_response": None,
        }
    except (httpx.HTTPError, OpenAIError, ValueError) as e:
        return {
            "user_intent": "unknown",
            "final_response": _error_reply(e),
        }


# ─── tool wrappers ─────────────────────────────────────────

def _run_tool(tool, **kwargs) -> str:
    try:
        return tool.invoke(kwargs)
    except (httpx.HTTPError, json.JSONDecodeError) as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def search_malls(state: AgentState) -> AgentState:
    city = state.get("user_location") or state.get("user_destination") or ""
    pref = state.get("user_preference") or "商场"
    if not city:
        return {"mall_results": ""}
    keyword = pref if pref and pref not in ("商场", "无", None) else "商场"
    result = _run_tool(search_nearby_malls, city=city, keyword=keyword)
    return {"mall_results": result}


def search_hotels_node(state: AgentState) -> AgentState:
    city = state.get("user_location") or state.get("user_destination") or ""
    pref = state.get("user_preference") or "酒店"
    if not city:
        return {"hotel_results": ""}
    keyword = pref if pref and pref not in ("酒店", "无", None) else "酒店"
    result = _run_tool(search_hotels, city=city, keyword=keyword)
    return {"hotel_results": result}


def search_sights(state: AgentState) -> AgentState:
    city = state.get("user_location") or state.get("user_destination") or ""
    pref = state.get("user_preference") or "景点"
    if not city:
        return {"sight_results": ""}
    keyword = pref if pref and pref not in ("景点", "无", None) else "景点"
    result = _run_tool(search_sightseeing, city=city, keyword=keyword)
    return {"sight_results": result}


def search_route(state: AgentState) -> AgentState:
    origin = state.get("user_route_from") or state.get("user_location") or ""
    dest = state.get("user_route_to") or state.get("user_destination") or ""
    city = state.get("user_location") or state.get("user_destination") or ""
    if not origin or not dest:
        return {"route_results": ""}
    result = _run_tool(plan_route, origin=origin, destination=dest, city=city, mode="transit")
    return {"route_results": result}


# ─── multi search ───────────────────────────────────────────

def search_multi(state: AgentState) -> AgentState:
    needs = state.get("needs") or [state.get("user_intent")]
    city = state.get("user_location") or state.get("user_destination") or ""
    results: dict = {}

    for need in needs:
        if need == "shopping" and city:
            results["shopping"] = _run_tool(search_nearby_malls, city=city, keyword=state.get("user_preference") or "商场")
        elif need == "hotel" and city:
            results["hotel"] = _run_tool(search_hotels, city=city, keyword=state.get("user_preference") or "酒店")
        elif need == "sightseeing" and city:
            results["sightseeing"] = _run_tool(search_sightseeing, city=city, keyword=state.get("user_preference") or "景点")
        elif need == "route":
            origin = state.get("user_route_from") or city
            dest = state.get("user_route_to") or state.get("user_destination") or city
            if origin and dest:
                results["route"] = _run_tool(plan_route, origin=origin, destination=dest, city=city, mode="transit")

    return {
        "mall_results": results.get("shopping", ""),
        "hotel_results": results.get("hotel", ""),
        "sight_results": results.get("sightseeing", ""),
        "route_results": results.get("route", ""),
    }


# ─── generate reply ─────────────────────────────────────────

def generate_recommend(state: AgentState) -> AgentState:
    if state.get("final_response"):
        return {"messages": [AIMessage(content=state["final_response"])]}

    if not _is_key_configured():
        reply = _no_key_reply()
    else:
        try:
            llm = _get_llm()
            intent = state.get("user_intent") or ""
            needs = state.get("needs") or [intent]
            city = state.get("user_location") or state.get("user_destination") or ""
            pref = state.get("user_preference") or "无特殊偏好"

            results_map = {
                "shopping": state.get("mall_results", ""),
                "hotel": state.get("hotel_results", ""),
                "sightseeing": state.get("sight_results", ""),
                "route": state.get("route_results", ""),
            }

            data_parts = []
            for need in needs:
                label = {"shopping": "商场", "hotel": "酒店", "sightseeing": "景点", "route": "路线"}.get(need, need)
                r = results_map.get(need, "")
                if r:
                    data_parts.append(f"【{label}数据】\n{r}")

            extra_parts = []
            docs_text = state.get("user_docs")
            if docs_text:
                extra_parts.append(f"【用户上传文档参考】\n{docs_text[:2000]}")
            image_desc = state.get("image_desc")
            if image_desc:
                extra_parts.append(f"【用户上传图片描述】\n{image_desc}")

            if not data_parts and intent != "chat":
                if not city:
                    reply = "你想查哪个城市呢？告诉我城市名我就能帮你啦～"
                else:
                    reply = f"抱歉，在 {city} 暂时没查到相关信息。要不换个关键词试试？"
            elif intent == "chat" or not data_parts:
                last_msg = state["messages"][-1].content if state["messages"] else ""
                reply = llm.invoke([
                    SystemMessage(content=SYSTEM_PROMPT),
                    HumanMessage(content=last_msg),
                ]).content
            else:
                if intent == "discover":
                    style_instruction = f"""请模仿小红书爆款笔记的风格，基于上面的真实数据，写一篇「{city} 周末怎么玩」种草短笔记：
- 开头一句有网感的钩子（可带 emoji），让人想接着看
- 分三个板块：🏬好逛（挑 2-3 个商场）、🏞️好玩（挑 2-3 个景点）、🏨住哪（挑 1-2 个酒店），每个一句话点出亮点（评分/特色/位置）
- 结尾加 3-5 个话题标签，例如 #{city}周末去哪儿 #citywalk
- 总字数 350 以内，只能推荐数据里真实存在的地方，不要编造地址和评分"""
                else:
                    style_instruction = '请用口语化语气推荐，300字以内，直接给结论不要说"根据数据"之类的话。'

                prompt = f"""{SYSTEM_PROMPT}

{chr(10).join(data_parts)}

用户意图：{intent}
用户偏好：{pref}
用户城市：{city}
{chr(10).join(extra_parts)}

{style_instruction}"""
                reply = llm.invoke([HumanMessage(content=prompt)]).content
        except (httpx.HTTPError, OpenAIError, ValueError) as e:
            reply = _error_reply(e)

    return {"messages": [AIMessage(content=reply)], "final_response": reply}


# ─── direct reply / stub ────────────────────────────────────

def direct_reply(state: AgentState) -> AgentState:
    if state.get("final_response"):
        return {"messages": [AIMessage(content=state["final_response"])]}

    if not _is_key_configured():
        reply = _no_key_reply()
    else:
        try:
            llm = _get_llm()
            last_msg = state["messages"][-1].content if state["messages"] else ""
            reply = llm.invoke([
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=last_msg),
            ]).content
        except (httpx.HTTPError, OpenAIError, ValueError) as e:
            reply = _error_reply(e)

    return {"messages": [AIMessage(content=reply)], "final_response": reply}


def _build_edit_instruction(raw: str) -> tuple[str, bool]:
    """把用户的修图诉求转成图像编辑提示词；泛化诉求时给专业默认指令并开启 prompt_extend。"""
    text = (raw or "").strip()
    specific = any(k in text for k in ("换", "去", "加", "背景", "风格", "变成", "改成", "移除", "删除", "天空", "海边"))
    if len(text) <= 10 and not specific:
        return (
            "对这张照片做专业级美化：精致调色，光影层次更通透，肤色自然红润，"
            "旅行摄影大片质感，保持人物五官与真实场景不变",
            True,
        )
    return text, False


def photo_edit(state: AgentState) -> AgentState:
    image_path = state.get("user_image")
    if not image_path:
        reply = (
            "好呀，修图我拿手 🎨 不过你得先上传一张照片～\n"
            "点输入框下方的图片上传按钮选张图，再告诉我想怎么调，比如：\n"
            "「帮我美化一下」「换成海边日落背景」「去掉画面里的路人」"
        )
        return {"messages": [AIMessage(content=reply)], "final_response": reply}

    if not _is_key_configured():
        reply = _no_key_reply()
        return {"messages": [AIMessage(content=reply)], "final_response": reply}

    try:
        from .tools.image_edit import edit_image, download_as_data_uri, ImageEditError

        last_msg = state["messages"][-1].content if state["messages"] else ""
        instruction, prompt_extend = _build_edit_instruction(last_msg)

        urls = edit_image(
            instruction, [image_path],
            size="1024x1024", prompt_extend=prompt_extend,
        )
        data_uri = download_as_data_uri(urls[0])
        reply = (
            "🎨 修好啦，看看效果～\n\n"
            f"![AI修图结果]({data_uri})\n\n"
            "想继续调风格、换背景或改细节，直接告诉我！"
        )
    except (httpx.HTTPError, OSError, ValueError, ImportError, ImageEditError) as e:
        reply = f"😣 修图失败了：{str(e)[:200]}\n\n可以换张图或稍后再试～"

    return {"messages": [AIMessage(content=reply)], "final_response": reply}


# ─── routers ────────────────────────────────────────────────

def route_after_image(state: AgentState) -> str:
    if state.get("user_image"):
        return "analyze_image"
    return "understand_intent"


def route_after_intent(state: AgentState) -> str:
    if state.get("final_response"):
        return "generate_recommend"

    intent = state.get("user_intent", "chat")
    needs = state.get("needs") or [intent]
    city = state.get("user_location") or state.get("user_destination")

    if intent == "photo_edit":
        return "photo_edit"

    if intent == "chat" or intent == "unknown":
        return "direct_reply"

    if intent == "discover":
        return "search_multi" if city else "direct_reply"

    if len(needs) > 1:
        if not city and intent != "route":
            return "direct_reply"
        return "search_multi"

    if intent == "route":
        return "search_route"

    if not city:
        return "direct_reply"

    return INTENT_ROUTE_MAP.get(intent, "direct_reply")
