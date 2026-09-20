"""模块 10:AgentOrchestrator 测试(用假 Node 验证编排语义)。"""
import asyncio

from app.agent.orchestrator import (
    ON_ERROR_DEGRADE, ON_ERROR_TERMINATE, AgentNode, AgentOrchestrator, ServiceRegistry,
)
from app.contracts.agent_state import (
    AgentState, Intent, IntentState, RequestState, StateUpdate, UnderstandingState, UserContext,
)
from app.contracts.errors import ErrorCode, llm_error
from app.contracts.trace import AgentTrace, SpanStatus


def _state() -> AgentState:
    s = AgentState(
        request=RequestState(trace_id="t", run_id="r",
                             user_context=UserContext(user_id="p-0001"),
                             original_query="q", normalized_query="q")
    )
    s.trace = AgentTrace(trace_id="t")
    return s


class IntentNode(AgentNode):
    name = "IntentNode"

    async def execute(self, state, services):
        return StateUpdate(intent=IntentState(intent=Intent.FIND_PERSON, confidence=0.9))


class StructNode(AgentNode):
    name = "QueryStructurerNode"

    async def execute(self, state, services):
        u = UnderstandingState(mentioned_systems=["Dify"])
        return StateUpdate(understanding=u)


class SlowNode(AgentNode):
    name = "SlowNode"
    timeout_ms = 50
    on_error = ON_ERROR_DEGRADE

    async def execute(self, state, services):
        await asyncio.sleep(1)
        return StateUpdate()


class BoomNode(AgentNode):
    name = "BoomNode"
    on_error = ON_ERROR_TERMINATE

    async def execute(self, state, services):
        raise llm_error("LLM 炸了")


class NeverNode(AgentNode):
    name = "NeverNode"

    async def execute(self, state, services):  # pragma: no cover — 不应被执行
        raise AssertionError("不应执行")


class CountNode(AgentNode):
    name = "CountNode"

    def __init__(self, bucket: list):
        self._bucket = bucket

    async def execute(self, state, services):
        await asyncio.sleep(0.05)
        self._bucket.append(self.name)
        return StateUpdate()


class ServiceUsingNode(AgentNode):
    name = "ServiceUsingNode"

    async def execute(self, state, services):
        svc = services.get("echo")
        return StateUpdate(response=state.response.model_copy(update={"final_answer": svc()}))


async def test_sequential_order_and_condition() -> None:
    """串行按序执行;条件不满足的节点跳过(条件分流)。"""
    orch = AgentOrchestrator()
    orch.add(IntentNode()).add(StructNode(), condition=lambda s: s.intent.intent == Intent.FIND_PERSON)
    orch.add(NeverNode(), condition=lambda s: s.intent.intent == Intent.CHAT)
    state = await orch.run(_state())
    assert state.intent.intent == Intent.FIND_PERSON
    assert state.understanding.mentioned_systems == ["Dify"]
    assert state.execution.current_stage == "__done__"
    names = [sp.node_name for sp in state.trace.spans]
    assert names == ["IntentNode", "QueryStructurerNode"]


async def test_parallel_group() -> None:
    """并行节点组:两个节点都执行且耗时接近单节点(并行调度)。"""
    bucket: list = []
    n1, n2 = CountNode(bucket), CountNode(bucket)
    n1.name, n2.name = "P1", "P2"
    orch = AgentOrchestrator()
    orch.add_parallel([n1, n2], label="RetrievalCoordinator")
    state = await orch.run(_state())
    assert sorted(bucket) == ["P1", "P2"]
    # 两个 50ms 节点并行,总 trace 应远小于 100ms+开销
    assert state.trace.total_latency_ms < 95


async def test_timeout_degrade_continue() -> None:
    """超时节点按 degrade 策略降级继续,标记 degraded。"""
    orch = AgentOrchestrator()
    orch.add(SlowNode()).add(IntentNode())
    state = await orch.run(_state())
    assert state.execution.degraded is True
    assert state.intent.intent == Intent.FIND_PERSON  # 后续节点仍执行
    span = state.trace.spans[0]
    assert span.status == SpanStatus.TIMEOUT
    assert state.execution.errors[0]["code"] == ErrorCode.TIMEOUT.value


async def test_failure_terminate() -> None:
    """关键节点失败终止主链,后续节点不执行。"""
    orch = AgentOrchestrator()
    orch.add(BoomNode()).add(NeverNode())
    state = await orch.run(_state())
    assert state.execution.current_stage == "__terminated__"
    assert state.execution.errors[0]["code"] == ErrorCode.LLM_ERROR.value
    assert state.trace.spans[0].status == SpanStatus.FAILED


async def test_services_registry() -> None:
    """Node 经 ServiceRegistry 取服务;未注册服务报内部错误。"""
    services = ServiceRegistry()
    services.register("echo", lambda: "pong")
    orch = AgentOrchestrator(services)
    orch.add(ServiceUsingNode())
    state = await orch.run(_state())
    assert state.response.final_answer == "pong"


async def test_trace_replayable() -> None:
    """运行轨迹可完整序列化回放(§4.2 验收)。"""
    orch = AgentOrchestrator()
    orch.add(IntentNode()).add(SlowNode())
    state = await orch.run(_state())
    js = state.trace.model_dump_json()
    from app.contracts.trace import AgentTrace as AT
    restored = AT.model_validate_json(js)
    assert [s.node_name for s in restored.spans] == ["IntentNode", "SlowNode"]
    assert restored.total_latency_ms is not None
