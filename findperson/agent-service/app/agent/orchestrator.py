"""AgentOrchestrator(V1.2 §4.2)。

只负责:执行顺序、条件分流、并行调度、超时、异常收敛、状态传递、降级、终态。
不实现:概念算法、SQL、RAG、Ranking、Prompt 业务逻辑。

Node 统一约定(§4.2):
    class AgentNode:
        async def execute(self, state, services) -> StateUpdate

Node = 读取 State + 调用 Service + 写回 State;业务实现都在各 Service 里。
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.contracts.agent_state import AgentState, StateUpdate, apply_update
from app.contracts.errors import AgentError, ErrorCode
from app.contracts.trace import SpanStatus

# Node 失败策略
ON_ERROR_TERMINATE = "terminate"   # 失败即终止主链(关键节点)
ON_ERROR_DEGRADE = "degrade"       # 失败降级继续(可缺失节点)


class AgentNode(ABC):
    """Agent 节点基类。子类只实现 execute(),业务逻辑放 Service。"""

    name: str = "AgentNode"
    timeout_ms: int = 10000
    on_error: str = ON_ERROR_TERMINATE

    @abstractmethod
    async def execute(self, state: AgentState, services: "ServiceRegistry") -> StateUpdate:
        """读取 state → 调用 services → 返回 StateUpdate。"""


@dataclass
class ServiceRegistry:
    """Service 容器:LLM/DB/Embedding/MCP 等,启动时装配,Node 经它取服务。

    用宽松 dict 而非强类型字段,新增 Service 不改 Orchestrator(§4.1 验收:
    新增 Node 不需要修改已有结构)。
    """

    services: dict[str, Any] = field(default_factory=dict)

    def get(self, name: str) -> Any:
        if name not in self.services:
            raise AgentError(ErrorCode.INTERNAL_ERROR, f"Service 未注册: {name}")
        return self.services[name]

    def register(self, name: str, service: Any) -> None:
        self.services[name] = service


Condition = Callable[[AgentState], bool]


@dataclass
class _Step:
    """编排步骤:单节点或并行节点组。"""

    nodes: list[AgentNode]
    condition: Condition | None = None
    label: str = ""


class AgentOrchestrator:
    """轻量有状态工作流编排器(Graph-ready,§3.1)。"""

    def __init__(self, services: ServiceRegistry | None = None) -> None:
        self.services = services or ServiceRegistry()
        self._steps: list[_Step] = []

    # ---------------- 编排 API ----------------

    def add(self, node: AgentNode, *, condition: Condition | None = None) -> "AgentOrchestrator":
        """追加一个串行节点,可带显式条件(条件分流)。"""
        self._steps.append(_Step(nodes=[node], condition=condition, label=node.name))
        return self

    def add_parallel(self, nodes: list[AgentNode], *, label: str = "parallel",
                     condition: Condition | None = None) -> "AgentOrchestrator":
        """追加一个并行节点组(如 RetrievalCoordinator 的双路检索)。"""
        self._steps.append(_Step(nodes=nodes, condition=condition, label=label))
        return self

    # ---------------- 执行 ----------------

    async def run(self, state: AgentState) -> AgentState:
        """按编排执行,返回最终 AgentState(含完整 trace,可回放)。"""
        for step in self._steps:
            if state.execution.current_stage == "__terminated__":
                break
            if step.condition is not None and not step.condition(state):
                continue
            state.execution.current_stage = step.label
            if len(step.nodes) == 1:
                await self._run_node(step.nodes[0], state)
            else:
                await asyncio.gather(*(self._run_node(n, state) for n in step.nodes))
        state.trace.finish()
        state.execution.total_latency_ms = state.trace.total_latency_ms
        state.execution.node_spans = list(state.trace.spans)
        state.execution.current_stage = "__done__" if state.execution.current_stage != "__terminated__" else "__terminated__"
        return state

    async def _run_node(self, node: AgentNode, state: AgentState) -> None:
        span = state.trace.new_span(node.name, input_summary=_summarize_input(state))
        try:
            update = await asyncio.wait_for(
                node.execute(state, self.services), timeout=node.timeout_ms / 1000,
            )
        except asyncio.TimeoutError:
            span.finish(status=SpanStatus.TIMEOUT, error_code=ErrorCode.TIMEOUT,
                        output_summary=f"节点超时({node.timeout_ms}ms)")
            self._handle_failure(node, state, ErrorCode.TIMEOUT, f"{node.name} 执行超时")
            return
        except AgentError as e:
            span.finish(status=SpanStatus.DEGRADED if e.degraded else SpanStatus.FAILED,
                        error_code=e.code, output_summary=e.message)
            if e.degraded:
                self._apply(state, StateUpdate(degraded=True, error=e.to_payload(state.trace.trace_id).model_dump()))
                span.degraded = True
            else:
                self._handle_failure(node, state, e.code, f"{node.name}: {e.message}")
            return
        except Exception as e:  # noqa: BLE001 —— 异常收敛,不让单节点炸掉整条链
            span.finish(status=SpanStatus.FAILED, error_code=ErrorCode.INTERNAL_ERROR,
                        output_summary=str(e)[:200])
            self._handle_failure(node, state, ErrorCode.INTERNAL_ERROR, f"{node.name} 未预期异常: {e}")
            return

        span.finish(
            status=SpanStatus.DEGRADED if update.degraded else SpanStatus.OK,
            output_summary=_summarize_update(update),
            degraded=update.degraded,
        )
        self._apply(state, update)

    def _apply(self, state: AgentState, update: StateUpdate) -> None:
        apply_update(state, update)
        if update.terminate:
            state.execution.current_stage = "__terminated__"

    def _handle_failure(self, node: AgentNode, state: AgentState,
                        code: ErrorCode, message: str) -> None:
        payload = {"code": code.value, "message": message, "node": node.name}
        if node.on_error == ON_ERROR_DEGRADE:
            self._apply(state, StateUpdate(degraded=True, error=payload))
        else:
            self._apply(state, StateUpdate(error=payload, terminate=True))


def _summarize_input(state: AgentState) -> str:
    q = state.request.normalized_query or state.request.original_query
    return f"query={q[:50]} stage={state.execution.current_stage}"


def _summarize_update(update: StateUpdate) -> str:
    parts = [f for f in ("intent", "understanding", "concept", "retrieval", "ranking", "response")
             if getattr(update, f) is not None]
    return "writes=" + ",".join(parts) if parts else "writes=-"
