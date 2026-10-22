"""景点识别：上传照片 → 视觉模型识别地标 → 返回景点名与所在城市。

只做一次同步视觉调用，不做图像生成，适配无状态/短超时运行环境。
"""

import os
import io
import re
import json
import base64

import httpx

DEFAULT_VISION_MODEL = "qwen3-vl-plus"
MAX_SIDE = 1280

_MIME_MAP = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".gif": "image/gif",
    ".webp": "image/webp", ".bmp": "image/bmp",
}

PROMPT = """识别这张照片里的景点或地标。请严格输出 JSON，不要输出任何其他文字：
{
  "found": true/false,
  "name": "景点/地标的正式名称，没认出来则为 null",
  "city": "所在城市，不确定则为 null",
  "landmark_type": "景点类型，如 古建筑/自然风光/主题乐园/城市地标",
  "description": "一句话说明画面里的关键特征，30字以内"
}
如果画面里没有可识别的景点或地标，found 填 false，name 填 null。"""


class SpotRecognitionError(Exception):
    pass


def _encode_image(image_path: str) -> str:
    ext = os.path.splitext(image_path)[1].lower()
    mime = _MIME_MAP.get(ext, "image/jpeg")

    try:
        from PIL import Image
        with Image.open(image_path) as im:
            im = im.convert("RGB")
            if max(im.size) > MAX_SIDE:
                ratio = MAX_SIDE / max(im.size)
                im = im.resize(
                    (max(1, int(im.width * ratio)), max(1, int(im.height * ratio))),
                    Image.LANCZOS,
                )
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=85)
            data = buf.getvalue()
        return "data:image/jpeg;base64," + base64.b64encode(data).decode()
    except ImportError:
        with open(image_path, "rb") as f:
            data = f.read()
        return f"data:{mime};base64," + base64.b64encode(data).decode()


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


def recognize_spot(image_path: str) -> dict:
    """返回 {found, name, city, landmark_type, description}。"""
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise SpotRecognitionError("OPENAI_API_KEY 未配置")

    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("VISION_MODEL") or DEFAULT_VISION_MODEL

    body = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": _encode_image(image_path)}},
                ],
            }
        ],
    }

    try:
        r = httpx.post(
            base_url + "/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=body,
            timeout=60,
        )
    except httpx.HTTPError as e:
        raise SpotRecognitionError(f"视觉模型请求失败：{e}") from e

    if r.status_code != 200:
        raise SpotRecognitionError(f"视觉模型返回 {r.status_code}：{r.text[:200]}")

    choices = r.json().get("choices") or []
    content = choices[0].get("message", {}).get("content", "") if choices else ""
    if isinstance(content, list):
        content = "".join(str(p.get("text", "")) for p in content if isinstance(p, dict))

    data = _parse_json(content)
    if not data:
        raise SpotRecognitionError("未能解析识别结果")

    name = data.get("name") or None
    return {
        "found": bool(data.get("found")) and bool(name),
        "name": name,
        "city": data.get("city") or None,
        "landmark_type": data.get("landmark_type") or "",
        "description": data.get("description") or "",
    }
