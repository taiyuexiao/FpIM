"""DeepSeek 大模型客户端(OpenAI 兼容 /chat/completions,标准库实现零依赖)。

用于邮件草稿生成;key 放 .env(.gitignore 已排除),失败时由调用方降级到模板。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from ..core.config import settings


class LLMError(Exception):
    """DeepSeek 调用异常(网络/HTTP/协议错误统一抛出,调用方降级处理)"""


def chat(messages: list[dict], temperature: float = 0.7, max_tokens: int = 1024) -> str:
    """调用 DeepSeek 对话接口,返回首个回复文本。

    messages: OpenAI 格式 [{"role": "system"|"user"|"assistant", "content": "..."}]
    """
    if not settings.DEEPSEEK_API_KEY:
        raise LLMError("DEEPSEEK_API_KEY 未配置")

    url = f"{settings.DEEPSEEK_BASE_URL.rstrip('/')}/chat/completions"
    payload = json.dumps({
        "model": settings.DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.DEEPSEEK_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        raise LLMError(f"DeepSeek HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LLMError(f"DeepSeek 连接失败: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise LLMError(f"DeepSeek 响应非 JSON: {exc}") from exc

    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"DeepSeek 响应结构异常: {data}") from exc
