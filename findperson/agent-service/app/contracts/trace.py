"""Trace 契约(V1.2 §15.1)。

每个 Node 执行必须产生一条 NodeSpan;一次请求的所有 NodeSpan 用同一 trace_id 串联。
模块 27 会把这些 span 落库到 agent.agent_traces / agent_node_spans。
"""
from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.contracts.errors import ErrorCode


class SpanStatus(str, Enum):
    """节点执行状态。"""

    OK = "ok"
    EMPTY = "empty"          # 正常但无结果
    DEGRADED = "degraded"    # 降级完成
    FAILED = "failed"
    TIMEOUT = "timeout"


class NodeSpan(BaseModel):
    """单个 Node 的执行跨度(V1.2 §15.1 字段)。"""

    node_name: str
    start_time: float
    end_time: float | None = None
    latency_ms: float | None = None
    input_summary: str = ""
    output_summary: str = ""
    status: SpanStatus = SpanStatus.OK
    degraded: bool = False
    error_code: ErrorCode | None = None
    llm_tokens: int = 0
    tool_calls: list[str] = Field(default_factory=list)

    def finish(
        self,
        *,
        status: SpanStatus = SpanStatus.OK,
        output_summary: str = "",
        degraded: bool = False,
        error_code: ErrorCode | None = None,
    ) -> None:
        """结束 span 并计算耗时。"""
        self.end_time = time.time()
        self.latency_ms = round((self.end_time - self.start_time) * 1000, 2)
        self.status = status
        if output_summary:
            self.output_summary = output_summary
        self.degraded = degraded
        self.error_code = error_code


class AgentTrace(BaseModel):
    """一次 Agent 运行的完整轨迹,可序列化用于回放和评测(V1.2 §4.1 验收)。"""

    trace_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    session_id: str | None = None
    spans: list[NodeSpan] = Field(default_factory=list)
    total_latency_ms: float | None = None

    def new_span(self, node_name: str, input_summary: str = "") -> NodeSpan:
        """开启一个节点 span 并登记。"""
        span = NodeSpan(node_name=node_name, start_time=time.time(), input_summary=input_summary)
        self.spans.append(span)
        return span

    def finish(self) -> None:
        """汇总整条 trace 的总耗时。"""
        if self.spans:
            start = min(s.start_time for s in self.spans)
            end = max(s.end_time or time.time() for s in self.spans)
            self.total_latency_ms = round((end - start) * 1000, 2)


def new_trace_id() -> str:
    """生成 trace_id(请求接入层使用,V1.2 §5.1:每次请求具有唯一 trace)。"""
    return uuid.uuid4().hex
