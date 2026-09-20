"""模块 25:Knowledge MCP Server + Client 测试。"""
import pytest
import pytest_asyncio

from app.contracts.agent_state import UserContext
from app.contracts.errors import AgentError, ErrorCode
from app.contracts.mcp import McpTool
from app.core.db import close_pool, fetchval, health, init_pool
from app.mcp_knowledge.client import KnowledgeMcpClient, _CircuitBreaker
from app.mcp_knowledge.server import KnowledgeMcpServer

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def pool():
    try:
        await init_pool()
    except Exception:
        pytest.skip("数据库不可用")
    if not await health():
        pytest.skip()
    yield
    await close_pool()


def _ctx() -> UserContext:
    return UserContext(user_id="p-0001", name="王丹", sensitivity_level=0)


async def test_all_8_tools_registered(pool) -> None:
    """8 个工具都有对应 handler(§12.1)。"""
    server = KnowledgeMcpServer()
    for tool in McpTool:
        assert getattr(server, f"_{tool.value}", None) is not None, tool.value


async def test_user_context_required(pool) -> None:
    """无 user_context 的调用被拒绝(§12.1 验收)。"""
    server = KnowledgeMcpServer()
    with pytest.raises(AgentError) as exc:
        await server.call(McpTool.SEARCH_KNOWLEDGE, {"query": "数据治理"},
                          user_context=None, trace_id="t")
    assert exc.value.code == ErrorCode.AUTH_ERROR


async def test_search_knowledge(pool) -> None:
    """search_knowledge 返回 hits 并写 mcp_call_logs(§15.1)。"""
    server = KnowledgeMcpServer()
    result = await server.call(McpTool.SEARCH_KNOWLEDGE, {"query": "数据治理"},
                               user_context=_ctx(), trace_id="t-mcp-1")
    assert result["has_evidence"] is True
    assert result["hits"]
    n = await fetchval("SELECT count(*) FROM agent.mcp_call_logs WHERE trace_id='t-mcp-1'")
    assert n >= 1  # 表跨测试持久,断言至少写入一条


async def test_get_responsibility(pool) -> None:
    """get_responsibility 返回正式责任全字段(§9.4)。"""
    server = KnowledgeMcpServer()
    result = await server.call(McpTool.GET_RESPONSIBILITY,
                               {"concept_names": ["数据治理"]},
                               user_context=_ctx(), trace_id="t-mcp-2")
    records = result["responsibilities"]
    assert records
    r = records[0]
    assert r["owner_department"] and r["escalation_path"]
    assert r["source_uri"].startswith("public.responsibility_assignments/")
    assert r["version"] >= 1


async def test_get_document_and_profile(pool) -> None:
    """get_document / get_person_profile。"""
    server = KnowledgeMcpServer()
    doc = await server.call(McpTool.GET_DOCUMENT,
                            {"document_id": "responsibility-ra-mock-0001"},
                            user_context=_ctx(), trace_id="t")
    assert doc["metadata"]["id"] == "responsibility-ra-mock-0001"
    profile = await server.call(McpTool.GET_PERSON_PROFILE, {"person_id": "p-0001"},
                                user_context=_ctx(), trace_id="t")
    assert "王丹" in profile["body"]
    assert "raw_tags" not in profile["body"]  # 动态标签不进(§10.4)


async def test_health_and_sources(pool) -> None:
    """knowledge_health 与 list_sources 一致性。"""
    server = KnowledgeMcpServer()
    health_r = await server.call(McpTool.KNOWLEDGE_HEALTH, {},
                                 user_context=_ctx(), trace_id="t")
    assert health_r["published_okf"] == 374
    assert health_r["ok"] is True
    sources = await server.call(McpTool.LIST_SOURCES, {}, user_context=_ctx(), trace_id="t")
    assert sources["total"] == 374


async def test_client_timeout_and_breaker() -> None:
    """Client:超时返回统一 McpResponse;熔断器开/合。"""
    class SlowServer:
        async def call(self, tool, params, *, user_context, trace_id):
            import asyncio
            await asyncio.sleep(5)

    client = KnowledgeMcpClient(SlowServer(), timeout_ms=50)
    resp = await client.search_knowledge("x", user_context=_ctx(), trace_id="t")
    assert resp.ok is False and resp.error == ErrorCode.TIMEOUT.value
    assert resp.degraded is True

    breaker = _CircuitBreaker(threshold=2, cooldown_seconds=0.01)
    assert breaker.allow()
    breaker.on_failure()
    breaker.on_failure()
    assert not breaker.allow()       # 断开
    import time
    time.sleep(0.02)
    assert breaker.allow()           # 半开
    breaker.on_success()
    assert breaker.allow()           # 闭合


async def test_client_error_conversion(pool) -> None:
    """业务错误转为统一 McpResponse(错误码保留),不触发熔断。"""
    client = KnowledgeMcpClient()
    resp = await client.get_document("not-exists-doc", user_context=_ctx(), trace_id="t")
    assert resp.ok is False
    assert resp.error == ErrorCode.RAG_ERROR.value
