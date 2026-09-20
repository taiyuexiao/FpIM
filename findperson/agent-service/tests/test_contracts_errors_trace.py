"""模块 02 契约的单元测试:错误模型与 Trace 序列化。"""
import time

from app.contracts.errors import AgentError, ErrorCode, ErrorPayload, degraded_error, llm_error
from app.contracts.trace import AgentTrace, SpanStatus


def test_error_payload_roundtrip() -> None:
    """错误体可 JSON 往返且保留错误码。"""
    err = llm_error("LLM 调用失败", provider="deepseek")
    payload = err.to_payload(trace_id="t-1")
    data = payload.model_dump_json()
    restored = ErrorPayload.model_validate_json(data)
    assert restored.code == ErrorCode.LLM_ERROR
    assert restored.trace_id == "t-1"
    assert restored.degraded is False


def test_degraded_flag() -> None:
    """降级错误显式标记 degraded。"""
    err = degraded_error("MCP 不可用,降级为业务表直读")
    payload = err.to_payload()
    assert payload.code == ErrorCode.DEGRADED
    assert payload.degraded is True


def test_agent_error_is_exception() -> None:
    """AgentError 可作为异常抛出并捕获。"""
    try:
        raise AgentError(ErrorCode.INTENT_ERROR, "意图识别失败")
    except AgentError as e:
        assert e.code == ErrorCode.INTENT_ERROR
        assert e.message == "意图识别失败"


def test_trace_span_lifecycle() -> None:
    """trace → span 开启/结束,耗时被正确计算。"""
    trace = AgentTrace(session_id="s-1")
    span = trace.new_span("IntentNode", input_summary="query=谁负责Agent平台")
    time.sleep(0.01)
    span.finish(status=SpanStatus.OK, output_summary="intent=find_person")
    trace.finish()

    assert span.latency_ms is not None and span.latency_ms >= 10
    assert trace.total_latency_ms is not None
    # 可序列化用于回放(V1.2 §4.1 验收)
    restored = AgentTrace.model_validate_json(trace.model_dump_json())
    assert restored.spans[0].node_name == "IntentNode"
    assert restored.spans[0].status == SpanStatus.OK
