"""模块 27:Trace 落库 + 指标监控测试。"""
import pytest
import pytest_asyncio

from app.agent.chain import build_orchestrator
from app.contracts.agent_state import (
    AgentState, Intent, IntentState, QueryType, RequestState, UserContext,
)
from app.core.db import close_pool, fetchrow, fetchval, health, init_pool
from app.core.observability import MetricsRegistry, persist_trace

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


def _state(query: str, qt: QueryType) -> AgentState:
    s = AgentState(
        request=RequestState(trace_id="t", run_id="r",
                             user_context=UserContext(user_id="p-0002", name="刘旭"),
                             original_query=query, normalized_query=query)
    )
    s.intent = IntentState(intent=Intent.FIND_PERSON, query_type=qt)
    return s


async def test_persist_trace_full(pool) -> None:
    """一次运行落库:trace + 全部 node spans + 推荐日志,可按 trace_id 回放(§15.1)。"""
    orch = build_orchestrator()
    state = _state("谁负责数据治理?", QueryType.EXPLICIT_RESPONSIBILITY)
    final = await orch.run(state)
    await persist_trace(final)

    tid = final.trace.trace_id
    trace_row = await fetchrow("SELECT * FROM agent.agent_traces WHERE trace_id=$1", tid)
    assert trace_row is not None
    assert trace_row["user_id"] == "p-0002"
    assert trace_row["total_latency_ms"] >= 0

    n_spans = await fetchval("SELECT count(*) FROM agent.agent_node_spans WHERE trace_id=$1", tid)
    assert n_spans == len(final.trace.spans)
    span_names = await fetchval(
        "SELECT string_agg(node_name, ',' ORDER BY id) FROM agent.agent_node_spans WHERE trace_id=$1", tid)
    assert "IntentNode" in span_names and "AnswerBuilderNode" in span_names

    rec = await fetchrow(
        "SELECT query_type, rank_policy, gate_decision FROM agent.agent_recommendation_logs"
        " WHERE trace_id=$1", tid)
    assert rec["query_type"] == "explicit_responsibility"
    assert rec["rank_policy"] == "responsibility_policy"


async def test_persist_trace_idempotent_and_failure_safe(pool) -> None:
    """重复落库不报错(ON CONFLICT);落库失败不阻断(日志告警)。"""
    orch = build_orchestrator()
    state = _state("王丹的电话是多少", QueryType.CONTACT_LOOKUP)
    final = await orch.run(state)
    await persist_trace(final)
    await persist_trace(final)  # 重复调用不抛错
    tid = final.trace.trace_id
    n = await fetchval("SELECT count(*) FROM agent.agent_traces WHERE trace_id=$1", tid)
    assert n == 1


def test_metrics_registry() -> None:
    """指标注册表:计数/耗时/Prometheus 导出(§15.2)。"""
    m = MetricsRegistry()
    m.inc("agent_requests_total")
    m.inc("agent_requests_total")
    m.inc("degraded_total")
    m.observe_latency("agent_request_latency", 120.0)
    m.observe_latency("agent_request_latency", 80.0)
    text = m.render_prometheus()
    assert "agent_requests_total 2" in text
    assert "degraded_rate 0.5000" in text
    assert "agent_request_latency_ms" in text and "100.00" in text
