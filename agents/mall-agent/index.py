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
import inspect

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
        "VISION_BASE_URL", "VISION_API_KEY",
        "AMAP_KEY", "AI_GATEWAY_API_KEY", "AI_GATEWAY_BASE_URL", "AI_GATEWAY_MODEL",
    )
    return {n: getattr(env, n) for n in names if getattr(env, n, None)}


def _parse_payload(payload) -> dict:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8", "ignore")
    if isinstance(payload, str) and payload.strip():
        try:
            data = json.loads(payload)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


async def _read_body(request) -> dict:
    """兼容平台注入的 request：dict / .json() / .body(属性或方法) 三种形态。"""
    if request is None:
        return {}

    for name in ("json", "body", "data", "payload"):
        value = getattr(request, name, None)
        if value is None:
            continue
        if callable(value):
            if name not in ("json", "body"):
                continue
            try:
                parsed = _parse_payload(await _maybe_await(value()))
            except Exception:
                continue
        else:
            parsed = _parse_payload(value)
        if parsed:
            return parsed

    return _parse_payload(request)


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
