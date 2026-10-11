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

agent = MallAgent()

MAP_HEADER = '<div class="map-header">📍 结果地图</div>'
MAP_PLACEHOLDER = MAP_HEADER + build_map_html([])

EXAMPLES = [
    ("周末去深圳玩两天，帮我规划下", "✈️"),
    ("北京有什么好逛的商场？我喜欢高端品牌", "💎"),
    ("上海外滩附近性价比高的酒店推荐", "🏨"),
    ("深圳北站到万象天地怎么坐地铁？", "🚇"),
    ("杭州西湖有什么必去的景点？", "🏞️"),
    ("你好，你能帮我做什么呀？", "👋"),
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


def respond(user_input: str, history, uploaded_files, uploaded_image, session_id: str):
    if not user_input.strip():
        return user_input, history, session_id, gr.update(), gr.update()

    file_paths = _normalize_files(uploaded_files) if uploaded_files else None
    image_path = None
    if uploaded_image:
        if isinstance(uploaded_image, str):
            image_path = uploaded_image
        elif hasattr(uploaded_image, "name"):
            image_path = uploaded_image.name

    try:
        reply, points = agent.chat(user_input, history, file_paths=file_paths, image_path=image_path)
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
    map_html = MAP_HEADER + build_map_html(points)
    return "", history, session_id, map_html, gr.Dropdown(choices=sessions, value=session_id)


def _new_chat():
    global agent
    agent = MallAgent()
    return [], str(uuid.uuid4()), MAP_PLACEHOLDER, gr.Dropdown(value=None)


def _load_selected(selected_id: str):
    if not selected_id:
        return gr.update(), gr.update(), gr.update()
    res = storage.load_session(selected_id)
    if not res:
        return [], selected_id, MAP_PLACEHOLDER
    _, messages = res
    return messages, selected_id, MAP_PLACEHOLDER


def _delete_selected(selected_id: str):
    if selected_id:
        storage.delete_session(selected_id)
    return gr.Dropdown(choices=storage.list_sessions(), value=None)


def _restore_latest():
    sessions = storage.list_sessions()
    res = storage.latest_session()
    if res:
        sid, _, messages = res
        return gr.Dropdown(choices=sessions, value=sid), sid, messages, MAP_PLACEHOLDER
    return gr.Dropdown(choices=sessions), "", [], MAP_PLACEHOLDER


def _clear_files():
    return None, None


with gr.Blocks(title="小途 · 全能出行决策助手") as demo:

    session_state = gr.State(value="")

    with gr.Row(elem_id="main-row"):
        with gr.Column(scale=1):

            gr.Markdown("""
            # 🧳 小途 · 出行决策助手
            **LangGraph** 构建 · 7 大能力 · 高德地图数据 · 文档/图片智能融合 · AI 修图
            """)

            chips_html = '<div id="chips-row">' + "".join(
                f'<div class="chip" data-text="{t.replace(chr(34), "&quot;")}">{em} {t}</div>'
                for t, em in EXAMPLES
            ) + '</div>'
            gr.HTML(chips_html)

            with gr.Row(elem_id="history-row"):
                session_dropdown = gr.Dropdown(
                    label="📜 历史对话（自动保存，重启可恢复）",
                    choices=storage.list_sessions(),
                    scale=8,
                )
                load_btn = gr.Button("📂 载入", scale=1)
                delete_btn = gr.Button("🗑 删除", scale=1)

            chatbot = gr.Chatbot(
                elem_id="chatbot",
                height=520,
                layout="bubble",
            )

            with gr.Row(elem_id="input-row"):
                msg = gr.Textbox(
                    elem_classes=["input-textbox"],
                    show_label=False,
                    placeholder="问问附近有什么商场，或告诉我你喜欢什么风格～",
                    lines=1,
                    scale=8,
                )
                send_btn = gr.Button("🚀 发送", elem_id="send-btn", scale=1)
                clear_btn = gr.Button("🗑️ 新对话", elem_id="clear-btn", scale=1)

            with gr.Row(elem_id="attach-row"):
                with gr.Column(scale=1):
                    file_upload = gr.File(
                        label="📎 上传文档（PDF / TXT / Excel / Word）",
                        file_types=[".pdf", ".txt", ".md", ".csv", ".json", ".xlsx", ".xls", ".docx"],
                        file_count="multiple",
                    )
                with gr.Column(scale=1):
                    image_upload = gr.Image(
                        label="🖼️ 上传图片（品牌/商场照片）",
                        type="filepath",
                    )

        if DEV_MODE:
            with gr.Column(scale=0, min_width=320, elem_id="sidebar"):
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
                    choices=["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo", "deepseek-chat", "qwen-plus", "qwen-turbo"],
                    value=cur[2] or "gpt-4o-mini",
                    allow_custom_value=True,
                )
                amap_key_box = gr.Textbox(
                    label="高德地图 Key",
                    value=cur[3],
                    placeholder="高德开放平台 Web 服务 Key",
                    type="password",
                )
                apply_btn = gr.Button("💾 应用设置", elem_id="apply-btn", variant="primary")
                apply_status = gr.Textbox(show_label=False, interactive=False)

                apply_btn.click(
                    _save_env,
                    inputs=[api_key_box, base_url_box, model_box, amap_key_box],
                    outputs=apply_status,
                )

                gr.Markdown("""
                ---
                **💡 部署提示：**
                - 生产部署请设置环境变量 `DEV_MODE=0`（默认），隐藏此面板
                - 生产环境通过 `.env` 文件配置所有 Key
                - VISION_MODEL 可选（如 `qwen3-vl-plus`），启用图片识别
                - IMAGE_MODEL 可选（默认 qwen-image-3.0），AMAP_JS_KEY/AMAP_SECURITY_CODE 可选
                """)

    map_panel = gr.HTML(MAP_PLACEHOLDER, elem_id="map-panel")

    msg.submit(respond, [msg, chatbot, file_upload, image_upload, session_state],
               [msg, chatbot, session_state, map_panel, session_dropdown])
    send_btn.click(respond, [msg, chatbot, file_upload, image_upload, session_state],
                   [msg, chatbot, session_state, map_panel, session_dropdown])
    clear_btn.click(_new_chat, None,
                    [chatbot, session_state, map_panel, session_dropdown], queue=False)
    load_btn.click(_load_selected, session_dropdown,
                   [chatbot, session_state, map_panel], queue=False)
    delete_btn.click(_delete_selected, session_dropdown, session_dropdown, queue=False)

    demo.load(_restore_latest, None,
              [session_dropdown, session_state, chatbot, map_panel])


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("PORT", "7860")),
        theme=gr.themes.Soft(),
        css=CSS,
        js=JS,
        show_error=True,
    )
