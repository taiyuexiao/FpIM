"""Trace 落库 + 指标监控(V1.2 §15)。

§15.1:每个 Node 的 span 落库(agent_traces / agent_node_spans),
       推荐结果落 agent_recommendation_logs,一次请求可用同一 trace_id 完整回放。
§15.2:Prometheus 指标(进程内注册表 + /metrics 文本导出)。
"""
from __future__ import annotations

import json
import time

from app.contracts.agent_state import AgentState
from app.core import db


# ---------------------------------------------------------------- Trace 落库(§15.1)

async def persist_trace(state: AgentState) -> None:
    """把一次运行的 trace + spans + 推荐日志落库。失败不阻断业务(只打印)。"""
    trace = state.trace
    try:
        await db.execute(
            "INSERT INTO agent.agent_traces(trace_id, run_id, session_id, user_id,"
            " original_query, total_latency_ms, degraded)"
            " VALUES($1,$2,$3,$4,$5,$6,$7) ON CONFLICT (trace_id) DO NOTHING",
            trace.trace_id, trace.run_id, trace.session_id,
            state.request.user_context.user_id, state.request.original_query,
            trace.total_latency_ms, state.execution.degraded,
        )
        for span in trace.spans:
            await db.execute(
                "INSERT INTO agent.agent_node_spans(trace_id, node_name, latency_ms,"
                " status, degraded, error_code, llm_tokens, tool_calls,"
                " input_summary, output_summary)"
                " VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",
                trace.trace_id, span.node_name, span.latency_ms,
                span.status.value, span.degraded,
                span.error_code.value if span.error_code else None,
                span.llm_tokens, json.dumps(span.tool_calls),
                span.input_summary[:500], span.output_summary[:500],
            )
        if state.ranking.ranked_candidates:
            await db.execute(
                "INSERT INTO agent.agent_recommendation_logs(trace_id, user_id,"
                " query_type, rank_policy, ranked_candidates, gate_decision)"
                " VALUES($1,$2,$3,$4,$5,$6)",
                trace.trace_id, state.request.user_context.user_id,
                state.intent.query_type.value if state.intent.query_type else None,
                state.ranking.rank_policy or None,
                json.dumps(state.ranking.ranked_candidates, ensure_ascii=False, default=str),
                state.ranking.gate_decision.value if state.ranking.gate_decision else None,
            )
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning("persist_trace failed: %s", e)


# ---------------------------------------------------------------- 指标注册表(§15.2)

class MetricsRegistry:
    """进程内指标注册表(Prometheus 文本格式导出)。

    指标清单对齐 §15.2:agent_requests_total / agent_request_latency /
    llm_calls_total / llm_tokens_total / rag_latency / mcp_failure_rate /
    degraded_rate / error_rate 等。V1 用进程内实现,真实联调可换 prometheus_client。
    """

    def __init__(self) -> None:
        self.counters: dict[str, float] = {}
        self.latency_sum: dict[str, float] = {}
        self.latency_count: dict[str, int] = {}

    def inc(self, name: str, value: float = 1.0) -> None:
        self.counters[name] = self.counters.get(name, 0.0) + value

    def observe_latency(self, name: str, latency_ms: float) -> None:
        self.latency_sum[name] = self.latency_sum.get(name, 0.0) + latency_ms
        self.latency_count[name] = self.latency_count.get(name, 0) + 1

    def record_request(self, state: AgentState) -> None:
        """一次 /agent/chat 请求的指标记录。"""
        self.inc("agent_requests_total")
        if state.execution.total_latency_ms:
            self.observe_latency("agent_request_latency", state.execution.total_latency_ms)
        for span in state.trace.spans:
            self.observe_latency(f"node_latency:{span.node_name}", span.latency_ms or 0)
            if span.llm_tokens:
                self.inc("llm_tokens_total", span.llm_tokens)
        if state.execution.degraded:
            self.inc("degraded_total")
        if state.execution.errors:
            self.inc("error_total")
        if not state.retrieval.rag_documents and state.intent.intent and state.intent.intent.value == "knowledge_qa":
            self.inc("rag_empty_total")

    def render_prometheus(self) -> str:
        """导出 Prometheus 文本格式。"""
        lines: list[str] = []
        for name, value in sorted(self.counters.items()):
            lines.append(f"# TYPE {name} counter")
            lines.append(f"{name} {value}")
        for name, total in sorted(self.latency_sum.items()):
            count = self.latency_count[name]
            metric = name.replace(":", "_") + "_ms"
            lines.append(f"# TYPE {metric} summary")
            lines.append(f'{metric}{{quantile="avg"}} {total / max(count, 1):.2f}')
            lines.append(f"{metric}_count {count}")
        total_req = self.counters.get("agent_requests_total", 0)
        if total_req:
            lines.append(f"degraded_rate {self.counters.get('degraded_total', 0) / total_req:.4f}")
            lines.append(f"error_rate {self.counters.get('error_total', 0) / total_req:.4f}")
        return "\n".join(lines) + "\n"


_metrics: MetricsRegistry | None = None


def get_metrics() -> MetricsRegistry:
    """指标注册表单例。"""
    global _metrics
    if _metrics is None:
        _metrics = MetricsRegistry()
    return _metrics
