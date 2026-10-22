import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

import gradio as gr
from mall_agent.agent import MallAgent
from mall_agent import storage
from mall_agent.tools.map_render import build_map_html

BASE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(BASE, "styles.css"), encoding="utf-8") as f:
    CSS = f.read()
with open(os.path.join(BASE, "main.js"), encoding="utf-8") as f:
    JS = f.read()

DEV_MODE = os.getenv("DEV_MODE", "0") == "1"

EXAMPLES = [
    ("周末去深圳玩两天，帮我规划下", "✈️"),
    ("北京有什么好逛的商场？我喜欢高端品牌", "💎"),
    ("上海外滩附近性价比高的酒店推荐", "🏨"),
    ("深圳北站到万象天地怎么坐地铁？", "🚇"),
]


def _save_env(api_key, base_url, model, amap_key):
    env_path = os.path.join(BASE, ".env")
    extra = ""
    vision_model = os.getenv("VISION_MODEL", "")
    if vision_model:
        extra = f"VISION_MODEL={vision_model}\n"
    content = (
        f"OPENAI_API_KEY={api_key}\n"
        f"OPENAI_BASE_URL={base_url or 'https://api.openai.com/v1'}\n"
        f"OPENAI_MODEL={model or 'gpt-4o-mini'}\n"
        f"AMAP_KEY={amap_key}\n"
        f"{extra}"
    )
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(content)

    os.environ["OPENAI_API_KEY"] = api_key
    os.environ["OPENAI_BASE_URL"] = base_url or "https://api.openai.com/v1"
    os.environ["OPENAI_MODEL"] = model or "gpt-4o-mini"
    os.environ["AMAP_KEY"] = amap_key

    return "✅ 设置已保存并生效！刷新页面即可。"


def _load_current_env():
    return (
        os.getenv("OPENAI_API_KEY", ""),
        os.getenv("OPENAI_BASE_URL", ""),
        os.getenv("OPENAI_MODEL", ""),
        os.getenv("AMAP_KEY", ""),
    )


def _normalize_files(files):
    if not files:
        return []
    result = []
    for f in files:
        if isinstance(f, str):
            result.append(f)
        elif hasattr(f, "name"):
            result.append(f.name)
    return result


def _normalize_history(messages):
    """把历史记录统一成 Chatbot 可渲染的 {role, content(str)} 列表。"""
    result = []
    for item in messages or []:
        if isinstance(item, dict):
            role = item.get("role", "assistant")
            content = item.get("content", "")
        elif isinstance(item, (tuple, list)) and len(item) == 2:
            role, content = item
        else:
            continue
        if isinstance(content, list):
            content = "".join(
                str(p.get("text", ""))
                for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            )
        result.append({"role": role, "content": content if isinstance(content, str) else str(content)})
    return result


def _render_history_list():
    sessions = storage.list_sessions()
    if not sessions:
        return '<div class="history-empty">暂无历史对话</div>'
    items = []
    for title, sid in sessions:
        label = title or sid[:8]
        items.append(
            f'<div class="history-item" data-sid="{sid}" title="{sid}">'
            f'<span class="history-dot">●</span>'
            f'<span class="history-label">{label}</span>'
            f'</div>'
        )
    return '<div class="history-list">' + "".join(items) + '</div>'


def _build_map_section(points):
    if not points:
        return ""
    header = '<div class="map-header">📍 位置地图</div>'
    return header + build_map_html(points)


def respond(user_input: str, history, uploaded_files, uploaded_image, session_id: str):
    if not user_input.strip():
        return user_input, history, session_id, "", gr.update(), gr.update()

    file_paths = _normalize_files(uploaded_files) if uploaded_files else None
    image_path = None
    if uploaded_image:
        if isinstance(uploaded_image, str):
            image_path = uploaded_image
        elif hasattr(uploaded_image, "name"):
            image_path = uploaded_image.name

    try:
        a = MallAgent()
        reply, points = a.chat(user_input, history, file_paths=file_paths, image_path=image_path)
    except Exception as e:
        reply, points = f"😵‍💫 出错了：{str(e)}", []

    history.append({"role": "user", "content": user_input})
    history.append({"role": "assistant", "content": reply})

    if not session_id:
        session_id = str(uuid.uuid4())
    try:
        storage.save_session(session_id, history)
    except Exception:
        pass

    sessions = storage.list_sessions()
    map_html = _build_map_section(points)

    history_html = _render_history_list()

    return (
        "", history, session_id, map_html,
        gr.update(choices=sessions, value=session_id),
        gr.HTML(value=history_html),
    )


def _new_chat():
    new_sid = str(uuid.uuid4())
    return [], new_sid, "", gr.Dropdown(choices=storage.list_sessions(), value=new_sid)


def _load_selected(selected_id: str):
    if not selected_id:
        return gr.update(), gr.update(), gr.update()
    res = storage.load_session(selected_id)
    if not res:
        return [], selected_id, ""
    _, messages = res
    return _normalize_history(messages), selected_id, ""


def _delete_selected(selected_id: str):
    if selected_id:
        storage.delete_session(selected_id)
    return gr.Dropdown(choices=storage.list_sessions(), value=None), gr.HTML(value=_render_history_list())


def _restore_latest():
    sessions = storage.list_sessions()
    res = storage.latest_session()
    if res:
        sid, _, messages = res
        return (
            gr.Dropdown(choices=sessions, value=sid), sid, _normalize_history(messages),
            gr.update(), gr.HTML(value=_render_history_list()),
        )
    return (
        gr.Dropdown(choices=sessions), "", [],
        gr.update(), gr.HTML(value=_render_history_list()),
    )


def _clear_files():
    return None, None


SIDEBAR_HTML = """
<div class="sidebar-inner">
    <div class="sidebar-logo">🧳 <span>小水</span></div>
    <button class="sidebar-btn new-chat-btn" id="sidebar-new-chat">＋ 新对话</button>
    <div class="sidebar-section-title">最近对话</div>
</div>
"""

WELCOME_HTML = f"""
<div class="welcome-screen">
    <div class="welcome-title">有什么我能帮你的吗？</div>
    <div class="welcome-tabs">
        <div class="welcome-tab active">对话</div>
        <div class="welcome-tab">地图</div>
    </div>
    <div class="welcome-recommend-title">为你推荐</div>
    <div class="welcome-examples">
        {''.join(f'<div class="welcome-example" data-text="{t.replace(chr(34), "&quot;")}">{t}</div>' for t, em in EXAMPLES)}
    </div>
</div>
"""

MAP_PANEL_HTML = """
<div class="map-panel-outer">
    <div class="map-panel-title">📍 位置地图</div>
    <div class="map-panel-body" id="map-panel-body">
        <div class="map-empty">发送消息后，查询到的位置会在这里展示 🌍</div>
    </div>
</div>
"""


with gr.Blocks(title="小水 · 全能出行决策助手", css=CSS, js=JS) as demo:

    session_state = gr.State(value="")

    gr.HTML("""
    <button id="sidebar-toggle" class="sidebar-toggle" title="切换侧边栏">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>
    </button>
    """)

    with gr.Row(elem_id="app-root"):

        with gr.Column(scale=0, min_width=240, elem_id="sidebar"):
            gr.HTML(SIDEBAR_HTML)

            session_dropdown = gr.Dropdown(
                choices=storage.list_sessions(),
                label="",
                interactive=True,
                container=False,
                elem_id="session-dropdown",
            )

            history_html = gr.HTML(_render_history_list(), elem_id="history-list-html")

            with gr.Row(elem_id="sidebar-history-btns"):
                load_btn = gr.Button("📂 载入", scale=1, elem_classes=["sb-btn"])
                delete_btn = gr.Button("🗑 删除", scale=1, elem_classes=["sb-btn"])

        with gr.Column(scale=1, elem_id="main-content"):

            welcome = gr.HTML(WELCOME_HTML, elem_id="welcome-screen")

            with gr.Column(elem_id="chat-wrap"):
                chatbot = gr.Chatbot(
                    elem_id="chatbot",
                    type="messages",
                    height=600,
                    min_height=480,
                    show_label=False,
                )

            with gr.Accordion("📍 位置地图", open=False, elem_id="map-accordion"):
                map_panel = gr.HTML("", elem_id="map-panel-inner")

            with gr.Column(elem_id="input-area"):
                with gr.Row(elem_id="input-wrapper"):
                    file_upload = gr.File(
                        label="",
                        file_types=[".pdf", ".txt", ".md", ".csv", ".json", ".xlsx", ".xls", ".docx"],
                        file_count="multiple",
                        visible=False,
                        elem_id="file-upload-hidden",
                    )
                    image_upload = gr.Image(
                        label="",
                        type="filepath",
                        height=None,
                        visible=False,
                        elem_id="image-upload-hidden",
                    )

                    attach_btn = gr.Button("📎", elem_id="attach-btn", size="sm")
                    image_btn = gr.Button("🖼️", elem_id="image-btn", size="sm")

                    msg = gr.Textbox(
                        show_label=False,
                        placeholder="问问附近有什么商场，或告诉我你喜欢什么风格～",
                        lines=3,
                        max_lines=8,
                        elem_id="msg-input",
                    )

                    send_btn = gr.Button("发送", elem_id="send-btn", variant="primary", size="sm")

        if DEV_MODE:
            with gr.Column(scale=0, min_width=320, elem_id="dev-sidebar"):
                gr.Markdown("### ⚙️ 开发模式设置")

                cur = _load_current_env()
                api_key_box = gr.Textbox(
                    label="OpenAI API Key",
                    value=cur[0],
                    placeholder="sk-...",
                    type="password",
                )
                base_url_box = gr.Textbox(
                    label="Base URL",
                    value=cur[1] or "https://api.openai.com/v1",
                    placeholder="https://api.openai.com/v1",
                )
                model_box = gr.Dropdown(
                    label="模型",
                    choices=["qwen-turbo", "qwen-plus", "deepseek-chat", "gpt-4o-mini", "gpt-4o"],
                    value=cur[2] or "qwen-turbo",
                    allow_custom_value=True,
                )
                amap_key_box = gr.Textbox(
                    label="高德地图 Key",
                    value=cur[3],
                    type="password",
                )
                apply_btn = gr.Button("💾 应用设置", elem_id="apply-btn", variant="primary")
                apply_status = gr.Textbox(show_label=False, interactive=False)

                apply_btn.click(
                    _save_env,
                    inputs=[api_key_box, base_url_box, model_box, amap_key_box],
                    outputs=apply_status,
                )

    msg.submit(respond, [msg, chatbot, file_upload, image_upload, session_state],
               [msg, chatbot, session_state, map_panel, session_dropdown, history_html])
    send_btn.click(respond, [msg, chatbot, file_upload, image_upload, session_state],
                   [msg, chatbot, session_state, map_panel, session_dropdown, history_html])
    attach_btn.click(lambda: gr.update(visible=True), None, file_upload, queue=False)
    image_btn.click(lambda: gr.update(visible=True), None, image_upload, queue=False)

    file_upload.change(lambda: gr.update(visible=False), None, file_upload, queue=False)
    image_upload.change(lambda: gr.update(visible=False), None, image_upload, queue=False)

    load_btn.click(_load_selected, session_dropdown,
                   [chatbot, session_state, map_panel], queue=False)
    delete_btn.click(_delete_selected, session_dropdown,
                     [session_dropdown, history_html], queue=False)

    demo.load(_restore_latest, None,
              [session_dropdown, session_state, chatbot, map_panel, history_html])


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("PORT", "7860")),
        show_error=True,
    )
