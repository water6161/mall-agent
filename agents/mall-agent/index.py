"""小水 Agent 入口：EdgeOne Makers 会话模式（agents/ 目录）。

POST /mall-agent
请求头：Makers-Conversation-Id（平台强制要求）
请求体：{"message": "...", "history": [{"role": "user|assistant", "content": "..."}],
        "image": "data:image/jpeg;base64,..."}
响应体：{"reply": "...", "points": [...], "map_image": "data:image/png;base64,...", "spot": {...}}
"""

import os
import sys
import json

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:  # 私有模块 _core.py：包内相对导入优先，本地直跑时退回绝对导入
    from ._core import resolve_env, run
except (ImportError, SystemError):
    from _core import resolve_env, run  # type: ignore


def _context_env(context) -> dict:
    """兼容 context.env 为 dict / Mapping / 对象属性三种形态。"""
    env = getattr(context, "env", None)
    if env is None:
        return {}
    if isinstance(env, dict):
        return dict(env)
    try:
        return dict(env)
    except (TypeError, ValueError):
        pass

    names = (
        "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL", "VISION_MODEL",
        "AMAP_KEY", "AI_GATEWAY_API_KEY", "AI_GATEWAY_BASE_URL", "AI_GATEWAY_MODEL",
    )
    return {n: getattr(env, n) for n in names if getattr(env, n, None)}


async def _read_body(request) -> dict:
    if request is None:
        return {}
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        pass
    try:
        raw = await request.text()
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


async def handler(context):
    body = await _read_body(getattr(context, "request", None))

    message = body.get("message") or body.get("user_input") or ""
    history = body.get("history") or body.get("messages") or []
    image = body.get("image") or None

    env = resolve_env(_context_env(context))

    try:
        result = run(env, message, history=history, image=image)
    except Exception as e:  # 兜底：任何未捕获异常都不让页面直接 500
        result = {"reply": f"😵‍💫 出错了：{str(e)[:200]}", "points": []}

    return result
