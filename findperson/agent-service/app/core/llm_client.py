"""LLM Client(V1.2 §14.1)。

职责:Hermes/OpenAI 兼容 API 调用、timeout、并发控制、model config、Mock、
usage/Token 统计、error mapping。不维护任何业务 Prompt(业务 Prompt 归各 Node)。

- 真实实现:DeepSeek(OpenAI 兼容)httpx 直连
- Mock 实现:确定性规则应答,离线开发/测试用(LLM_USE_MOCK=1)

V1.2 §18:LLM 输出永远视为候选判断;Schema 二次失败率 < 0.5%(§5.2 验收)——
structured_chat 用 JSON 模式 + 校验重试保证。
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.config import get_settings
from app.contracts.errors import AgentError, ErrorCode


# ---------------------------------------------------------------- 共享 HTTP 客户端
# 复用 TCP/TLS 连接(Keep-Alive),避免每次调用重付握手开销(验收:响应慢)

_http_client: httpx.AsyncClient | None = None


def _get_http_client(timeout: float) -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=timeout,
            limits=httpx.Limits(max_connections=16, max_keepalive_connections=8),
        )
    return _http_client


@dataclass
class LLMUsage:
    """Token 用量统计(§14.1 usage/Token;§15.1 llm_tokens 入 span)。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0


@dataclass
class LLMResult:
    """一次 LLM 调用结果。"""

    content: str
    tokens: int = 0
    model: str = ""
    latency_ms: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


class LLMPort(Protocol):
    """LLM 抽象端口。业务模块只依赖此接口,便于 Mock/Real 切换(§23)。"""

    async def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.1) -> LLMResult: ...

    async def structured_chat(
        self,
        messages: list[dict[str, str]],
        *,
        required_keys: list[str],
        temperature: float = 0.1,
        max_retries: int = 1,
    ) -> tuple[dict[str, Any], LLMResult]: ...


# ---------------------------------------------------------------- 真实实现(DeepSeek)

class DeepSeekLLM:
    """DeepSeek OpenAI 兼容客户端。"""

    def __init__(self, max_concurrency: int = 8) -> None:
        s = get_settings()
        self._url = s.llm_base_url
        self._model = s.llm_model
        self._api_key = s.llm_api_key
        self._timeout = s.llm_timeout_ms / 1000
        self._sem = asyncio.Semaphore(max_concurrency)

    async def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.1) -> LLMResult:
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }
        return await self._call(payload)

    async def structured_chat(
        self,
        messages: list[dict[str, str]],
        *,
        required_keys: list[str],
        temperature: float = 0.1,
        max_retries: int = 1,
    ) -> tuple[dict[str, Any], LLMResult]:
        """JSON 模式输出 + required_keys 校验,失败重试(§5.2:Schema 二次失败率 < 0.5%)。"""
        last_err: AgentError | None = None
        for attempt in range(max_retries + 1):
            payload = {
                "model": self._model,
                "messages": messages,
                "temperature": temperature,
                "response_format": {"type": "json_object"},
            }
            try:
                result = await self._call(payload)
                data = json.loads(result.content)
                missing = [k for k in required_keys if k not in data]
                if missing:
                    raise AgentError(ErrorCode.LLM_ERROR, f"LLM 输出缺少字段: {missing}")
                return data, result
            except (json.JSONDecodeError, AgentError) as e:
                last_err = e if isinstance(e, AgentError) else AgentError(ErrorCode.LLM_ERROR, f"LLM 输出非 JSON: {e}")
        raise last_err  # type: ignore[misc]

    async def _call(self, payload: dict[str, Any]) -> LLMResult:
        if not self._api_key:
            raise AgentError(ErrorCode.LLM_ERROR, "LLM_API_KEY 未配置")
        start = time.time()
        try:
            async with self._sem:
                resp = await _get_http_client(self._timeout).post(
                    self._url,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
        except httpx.TimeoutException as e:
            raise AgentError(ErrorCode.TIMEOUT, f"LLM 调用超时: {e}") from e
        except httpx.HTTPError as e:
            raise AgentError(ErrorCode.LLM_ERROR, f"LLM 网络错误: {e}") from e

        latency = (time.time() - start) * 1000
        if resp.status_code != 200:
            raise AgentError(
                ErrorCode.LLM_ERROR,
                f"LLM HTTP {resp.status_code}",
                detail={"body": resp.text[:500]},
            )
        data = resp.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise AgentError(ErrorCode.LLM_ERROR, f"LLM 响应结构异常: {e}") from e
        tokens = int(data.get("usage", {}).get("total_tokens", 0))
        return LLMResult(content=content, tokens=tokens, model=self._model, latency_ms=round(latency, 2))


# ---------------------------------------------------------------- Mock 实现(离线确定性)

class MockLLM:
    """确定性 Mock:不访问网络,按消息内容给出可预期应答。

    用于离线开发与 CI;structured_chat 按 required_keys 返回空骨架,
    业务 Node 的单测可自行替换为更具体的 stub。
    """

    async def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.1) -> LLMResult:
        user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return LLMResult(content=f"[mock-answer] {user_msg[:200]}", tokens=0, model="mock-llm", latency_ms=1.0)

    async def structured_chat(
        self,
        messages: list[dict[str, str]],
        *,
        required_keys: list[str],
        temperature: float = 0.1,
        max_retries: int = 1,
    ) -> tuple[dict[str, Any], LLMResult]:
        data: dict[str, Any] = {k: None for k in required_keys}
        return data, LLMResult(content=json.dumps(data), tokens=0, model="mock-llm", latency_ms=1.0)


# ---------------------------------------------------------------- 工厂

def get_llm() -> LLMPort:
    """按配置返回 Real 或 Mock 实例(§23:未确认时 OpenAI-compatible Adapter + Mock)。"""
    if get_settings().llm_use_mock:
        return MockLLM()
    return DeepSeekLLM()
