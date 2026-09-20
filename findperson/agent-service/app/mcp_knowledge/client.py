"""KnowledgeMcpClient(V1.2 §12.2)。

Agent 侧类型化工具 Client:超时、熔断、参数 Schema、trace、错误转换、Mock/Real 切换。
不负责:RAG 算法、SQL、权限规则实现。
"""
from __future__ import annotations

import asyncio
import time

from app.config import get_settings
from app.contracts.agent_state import UserContext
from app.contracts.errors import AgentError, ErrorCode
from app.contracts.mcp import McpResponse, McpTool


class _CircuitBreaker:
    """简单熔断器:连续失败 N 次断开,冷却期后半开试探(§12.2 熔断;模块 29 完善)。"""

    def __init__(self, threshold: int = 3, cooldown_seconds: float = 30.0) -> None:
        self._threshold = threshold
        self._cooldown = cooldown_seconds
        self._failures = 0
        self._opened_at: float | None = None

    def allow(self) -> bool:
        if self._opened_at is None:
            return True
        if time.time() - self._opened_at >= self._cooldown:
            return True  # 半开:允许一次试探
        return False

    def on_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def on_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold:
            self._opened_at = time.time()


class KnowledgeMcpClient:
    """Agent 侧 MCP 客户端。"""

    def __init__(self, server=None, *, timeout_ms: int | None = None) -> None:
        # server 为 None 时按配置装配(MCP_USE_MOCK 时由调用方注入 Mock server)
        if server is None:
            from app.mcp_knowledge.server import KnowledgeMcpServer
            server = KnowledgeMcpServer()
        self._server = server
        s = get_settings()
        self._timeout = (timeout_ms or s.mcp_timeout_ms) / 1000
        self._breaker = _CircuitBreaker()

    async def call_tool(self, tool: McpTool, params: dict, *,
                        user_context: UserContext, trace_id: str) -> McpResponse:
        """统一调用:熔断 → 超时包装 → 错误转换为统一 McpResponse。"""
        if not self._breaker.allow():
            return McpResponse(ok=False, tool=tool, error=ErrorCode.MCP_ERROR.value,
                               degraded=True, trace_id=trace_id,
                               data={"reason": "circuit_open"})
        try:
            result = await asyncio.wait_for(
                self._server.call(tool, params, user_context=user_context, trace_id=trace_id),
                timeout=self._timeout,
            )
            self._breaker.on_success()
            return McpResponse(ok=True, tool=tool, data=result, trace_id=trace_id)
        except asyncio.TimeoutError:
            self._breaker.on_failure()
            return McpResponse(ok=False, tool=tool, error=ErrorCode.TIMEOUT.value,
                               degraded=True, trace_id=trace_id)
        except AgentError as e:
            # 业务错误(AUTH/INPUT/RAG)不算熔断失败;输出转换保留错误码
            if e.code in (ErrorCode.MCP_ERROR, ErrorCode.INTERNAL_ERROR):
                self._breaker.on_failure()
            return McpResponse(ok=False, tool=tool, error=e.code.value,
                               degraded=e.degraded, trace_id=trace_id,
                               data={"message": e.message})

    # ---------------- 类型化便捷方法 ----------------

    async def search_knowledge(self, query: str, *, user_context: UserContext,
                               trace_id: str, top_k: int = 5) -> McpResponse:
        return await self.call_tool(McpTool.SEARCH_KNOWLEDGE,
                                    {"query": query, "top_k": top_k},
                                    user_context=user_context, trace_id=trace_id)

    async def get_responsibility(self, concept_names: list[str], *,
                                 user_context: UserContext, trace_id: str) -> McpResponse:
        return await self.call_tool(McpTool.GET_RESPONSIBILITY,
                                    {"concept_names": concept_names},
                                    user_context=user_context, trace_id=trace_id)

    async def get_document(self, document_id: str, *,
                           user_context: UserContext, trace_id: str) -> McpResponse:
        return await self.call_tool(McpTool.GET_DOCUMENT, {"document_id": document_id},
                                    user_context=user_context, trace_id=trace_id)

    async def get_person_profile(self, person_id: str, *,
                                 user_context: UserContext, trace_id: str) -> McpResponse:
        return await self.call_tool(McpTool.GET_PERSON_PROFILE, {"person_id": person_id},
                                    user_context=user_context, trace_id=trace_id)

    async def knowledge_health(self, *, user_context: UserContext,
                               trace_id: str) -> McpResponse:
        return await self.call_tool(McpTool.KNOWLEDGE_HEALTH, {},
                                    user_context=user_context, trace_id=trace_id)


_client: KnowledgeMcpClient | None = None


def get_mcp_client() -> KnowledgeMcpClient:
    """Client 单例(§12.2 Mock/Real 切换点:MCP_USE_MOCK 时由装配层注入 Mock server)。"""
    global _client
    if _client is None:
        _client = KnowledgeMcpClient()
    return _client
