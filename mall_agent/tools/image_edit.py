"""AI 修图 / 文生图模块

支持两种后端：
1. OpenAI 兼容模式（/images/generations）—— 如阿里云 MaaS endpoint
2. DashScope 原生异步格式 —— dashscope.aliyuncs.com，图像生成不走兼容模式，
   必须用 /api/v1/services/aigc/image-generation/generation + 异步轮询。

自动根据 OPENAI_BASE_URL 判断用哪种格式。
"""

import os
import base64
import io
import time
import json

import httpx

DEFAULT_IMAGE_MODEL = "qwen-image-3.0"
DEFAULT_SIZE = "1024x1024"

_MIME_MAP = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".gif": "image/gif",
    ".webp": "image/webp", ".bmp": "image/bmp",
    ".tiff": "image/tiff", ".tif": "image/tiff",
}


class ImageEditError(Exception):
    pass


def _base_url() -> str:
    return os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")


def _headers() -> dict:
    return {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY', '')}"}


def _is_dashscope() -> bool:
    return "dashscope" in _base_url().lower()


def _encode_input(image_path: str, max_side: int = 1280) -> str:
    ext = os.path.splitext(image_path)[1].lower()
    mime = _MIME_MAP.get(ext, "image/jpeg")

    try:
        from PIL import Image
        with Image.open(image_path) as im:
            im = im.convert("RGB")
            if max(im.size) > max_side:
                ratio = max_side / max(im.size)
                im = im.resize(
                    (max(1, int(im.width * ratio)), max(1, int(im.height * ratio))),
                    Image.LANCZOS,
                )
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=90)
            data = buf.getvalue()
        return "data:image/jpeg;base64," + base64.b64encode(data).decode()
    except ImportError:
        with open(image_path, "rb") as f:
            data = f.read()
        return f"data:{mime};base64," + base64.b64encode(data).decode()


def _dashscope_size(size: str) -> str:
    return size.replace("x", "*")


def _request_dashscope(prompt: str, image_paths: list[str] | None = None,
                       size: str = DEFAULT_SIZE, model: str | None = None,
                       n: int = 1, prompt_extend: bool = False,
                       negative_prompt: str | None = None,
                       timeout: float = 180.0) -> list[str]:
    dashscope_base = "https://dashscope.aliyuncs.com"
    url = dashscope_base + "/api/v1/services/aigc/image-generation/generation"

    messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]

    parameters = {
        "size": _dashscope_size(size),
        "n": n,
    }
    if prompt_extend:
        parameters["prompt_extend"] = True

    model_name = model or os.getenv("IMAGE_MODEL") or DEFAULT_IMAGE_MODEL

    print(f"[image_edit] _request_dashscope start, image_paths={image_paths}", flush=True)
    if image_paths:
        print(f"[image_edit] encoding ref_img...", flush=True)
        ref_img_uri = _encode_input(image_paths[0])
        print(f"[image_edit] ref_img encoded, len={len(ref_img_uri)}", flush=True)
        body = {
            "model": model_name,
            "input": {
                "ref_img": ref_img_uri,
                "messages": messages,
            },
            "parameters": parameters,
        }
    else:
        body = {
            "model": model_name,
            "input": {"messages": messages},
            "parameters": parameters,
        }

    async_headers = {**_headers(), "Content-Type": "application/json", "X-DashScope-Async": "enable"}

    print(f"[image_edit] POST submit...", flush=True)
    try:
        r = httpx.post(url, headers=async_headers, json=body, timeout=30)
    except httpx.HTTPError as e:
        raise ImageEditError(f"DashScope 提交失败：{e}") from e

    print(f"[image_edit] POST status={r.status_code}", flush=True)
    if r.status_code != 200:
        raise ImageEditError(f"DashScope 提交返回 {r.status_code}：{r.text[:300]}")

    submit = r.json()
    task_id = submit.get("output", {}).get("task_id")
    print(f"[image_edit] task_id={task_id}", flush=True)
    if not task_id:
        raise ImageEditError(f"DashScope 未返回 task_id：{submit}")

    query_url = f"{dashscope_base}/api/v1/tasks/{task_id}"
    start = time.time()
    poll_headers = {**_headers(), "Content-Type": "application/json"}

    poll_count = 0
    while time.time() - start < timeout:
        time.sleep(4)
        poll_count += 1
        try:
            q = httpx.get(query_url, headers=poll_headers, timeout=15)
        except httpx.HTTPError as e:
            raise ImageEditError(f"DashScope 轮询失败：{e}") from e

        if q.status_code != 200:
            continue

        data = q.json()
        status = data.get("output", {}).get("task_status", "")
        elapsed = time.time() - start
        print(f"[image_edit] poll#{poll_count} status={status} elapsed={elapsed:.0f}s", flush=True)

        if status == "SUCCEEDED":
            urls: list[str] = []
            for choice in data.get("output", {}).get("choices", []):
                for msg in choice.get("message", {}).get("content", []):
                    img_url = msg.get("image")
                    if img_url:
                        urls.append(img_url)
            if not urls:
                raise ImageEditError(f"DashScope 成功但未返回图片：{data}")
            print(f"[image_edit] SUCCEEDED, {len(urls)} urls, total={elapsed:.0f}s", flush=True)
            return urls

        if status in ("FAILED", "UNKNOWN"):
            msg = data.get("output", {}).get("message", "") or data.get("message", "")
            raise ImageEditError(f"DashScope 任务失败：{msg}")

    raise ImageEditError(f"DashScope 任务超时（{timeout}s）")


def _request_openai_compat(prompt: str, image_paths: list[str] | None = None,
                           size: str = DEFAULT_SIZE, model: str | None = None,
                           n: int = 1, negative_prompt: str | None = None,
                           prompt_extend: bool = False, timeout: float = 240.0) -> list[str]:
    body: dict = {
        "model": model or os.getenv("IMAGE_MODEL") or DEFAULT_IMAGE_MODEL,
        "prompt": prompt,
        "size": size,
        "n": n,
    }
    if negative_prompt:
        body["negative_prompt"] = negative_prompt
    if prompt_extend:
        body["prompt_extend"] = True
    if image_paths:
        uris = [_encode_input(p) for p in image_paths]
        body["image"] = uris[0] if len(uris) == 1 else uris

    try:
        r = httpx.post(
            _base_url() + "/images/generations",
            headers=_headers(), json=body, timeout=timeout,
        )
    except httpx.HTTPError as e:
        raise ImageEditError(f"图像服务请求失败：{e}") from e

    if r.status_code != 200:
        raise ImageEditError(f"图像服务返回 {r.status_code}：{r.text[:300]}")

    data = r.json().get("data") or []
    urls = [item.get("url") for item in data if item.get("url")]
    if not urls:
        raise ImageEditError("图像服务没有返回可用图片")
    return urls


def _request_images(prompt: str, image_paths: list[str] | None = None,
                    size: str = DEFAULT_SIZE, model: str | None = None,
                    n: int = 1, negative_prompt: str | None = None,
                    prompt_extend: bool = False, timeout: float = 240.0) -> list[str]:
    if _is_dashscope():
        return _request_dashscope(
            prompt, image_paths=image_paths, size=size, model=model,
            n=n, negative_prompt=negative_prompt, prompt_extend=prompt_extend,
            timeout=timeout,
        )
    return _request_openai_compat(
        prompt, image_paths=image_paths, size=size, model=model,
        n=n, negative_prompt=negative_prompt, prompt_extend=prompt_extend,
        timeout=timeout,
    )


def generate_image(prompt: str, size: str = DEFAULT_SIZE,
                   model: str | None = None, n: int = 1) -> list[str]:
    return _request_images(prompt, image_paths=None, size=size, model=model, n=n)


def edit_image(prompt: str, image_paths: list[str], size: str = DEFAULT_SIZE,
               model: str | None = None, n: int = 1,
               negative_prompt: str | None = None,
               prompt_extend: bool = False) -> list[str]:
    return _request_images(
        prompt, image_paths=image_paths, size=size, model=model, n=n,
        negative_prompt=negative_prompt, prompt_extend=prompt_extend,
    )


def download_as_data_uri(url: str, max_side: int = 1280, quality: int = 85) -> str:
    r = httpx.get(url, timeout=120)
    r.raise_for_status()
    raw = r.content

    try:
        from PIL import Image
        with Image.open(io.BytesIO(raw)) as im:
            if im.mode in ("RGBA", "P"):
                im = im.convert("RGB")
            if max(im.size) > max_side:
                ratio = max_side / max(im.size)
                im = im.resize(
                    (max(1, int(im.width * ratio)), max(1, int(im.height * ratio))),
                    Image.LANCZOS,
                )
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=quality)
            raw = buf.getvalue()
        mime = "image/jpeg"
    except ImportError:
        mime = "image/png"

    return f"data:{mime};base64," + base64.b64encode(raw).decode()
