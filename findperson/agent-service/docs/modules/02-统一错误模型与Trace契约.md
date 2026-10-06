# 模块 02:统一错误模型 + Trace 契约

## 背景

对应 V1.2 §14.5(统一错误模型)与 §15.1(Agent Trace),属于阶段 0「公共契约冻结」清单(`统一错误模型`、`Trace Schema`)。V1.2 §18 共同责任要求「Error:明确正常、空结果、降级、失败、超时」「Trace:所有重要步骤具有同一 trace_id」;§4.1 验收要求 AgentState/Trace「可序列化用于 Trace 和评测」。这两个契约是所有后续 Node、Orchestrator、评测体系的地基,必须先冻结。

## 任务

- 输入:各模块执行过程中的成功/空结果/降级/失败/超时情况
- 输出:12 类统一错误码 + 统一异常/错误体;NodeSpan/AgentTrace 模型
- 验收:错误体与 Trace 可 JSON 序列化往返;降级结果显式标记 `degraded=true`(V1.2 §5.3 验收)

## 实现方式

- `app/contracts/errors.py`
  - `ErrorCode` 枚举:严格按 V1.2 §14.5 的 12 类(INPUT_ERROR/AUTH_ERROR/INTENT_ERROR/CONCEPT_ERROR/RETRIEVAL_ERROR/MCP_ERROR/RAG_ERROR/LLM_ERROR/RANK_ERROR/TIMEOUT/DEGRADED/INTERNAL_ERROR)
  - `AgentError` 统一异常:携带 code/message/detail/degraded;`to_payload(trace_id)` 转对外 `ErrorPayload`
  - 便捷构造函数(`input_error`/`auth_error`/`llm_error`/`timeout_error`/`degraded_error`)保证各模块错误格式一致;`degraded_error` 自动置 `degraded=True`
- `app/contracts/trace.py`
  - `NodeSpan`:字段严格对齐 V1.2 §15.1(node_name/start_time/end_time/latency/input_summary/output_summary/status/degraded/error_code/llm_tokens/tool_calls);`finish()` 自动算耗时
  - `SpanStatus`:ok/empty/degraded/failed/timeout 五态,对应「正常、空结果、降级、失败、超时」
  - `AgentTrace`:trace_id/run_id/session_id + spans 列表;`new_span()` 登记节点、`finish()` 汇总总耗时;Pydantic 可序列化回放
  - `new_trace_id()`:请求接入层(模块 11 的 §5.1)使用,保证每次请求唯一 trace
- 测试 `tests/test_contracts_errors_trace.py`:4 个用例(错误体往返、degraded 标记、异常抛捕、span 生命周期+trace 序列化回放),全部通过

## 遇到的问题报错及解决方法

无。本模块为纯 Pydantic 契约,一次通过(4 passed)。

## 上下游接口及依赖

- 上游:无(只依赖 pydantic)
- 下游:
  - `AgentOrchestrator`(模块 10)将为每个 Node 执行创建 NodeSpan,异常统一捕获为 AgentError
  - LLM Client(模块 06)用 `llm_error`/`timeout_error` 做错误映射
  - 请求接入(模块 16,§5.1)用 `new_trace_id()`,并按「HTTP 建流前错误与 SSE 建流后错误分别处理」把 ErrorPayload 转成 4xx/5xx 或 `run_error` 事件
  - 评测体系(模块 28)按 trace_id 回放、按 error_code 做错误归因
- 对外接口:`ErrorCode`、`AgentError`、`ErrorPayload`、`NodeSpan`、`AgentTrace`、`SpanStatus`、`new_trace_id()`
