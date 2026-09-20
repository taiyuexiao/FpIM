# 模块 27:Trace 落库 + 指标监控

## 背景

对应 V1.2 §15(Trace、可观测与审计):§15.1 每个 Node 必须记录 span,一次请求可用同一 trace_id 完整观察「Intent→QueryType→Concept→Retrieval→Merge→Rank→Answer」;§15.2 Prometheus 指标(agent_requests_total / latency / llm_tokens / degraded_rate / error_rate 等)。这是阶段 7 评测体系的数据地基——评测的错误归因、性能分析都依赖落库的 trace 与推荐日志。

## 任务

- 输入:一次运行结束的 AgentState(含完整 trace/spans/ranked)
- 输出:persist_trace() 落库三表 + MetricsRegistry + /metrics 端点
- 验收:trace/spans/推荐日志可按 trace_id 回放;重复落库幂等;落库失败不阻断业务;Prometheus 文本导出

## 实现方式

- `app/core/observability.py`
  - **persist_trace(state)**:agent_traces(trace_id/run_id/session/user/原查询/总耗时/degraded,ON CONFLICT 幂等)+ agent_node_spans(逐 span:节点/耗时/状态/降级/错误码/llm_tokens/输入输出摘要)+ agent_recommendation_logs(query_type/rank_policy/ranked 全量/gate_decision);整体 try/except 只告警不阻断(可观测不能拖死业务)
  - **MetricsRegistry**:进程内计数器 + 耗时直方(avg/count),`record_request()` 按 §15.2 清单登记(requests/latency/node_latency/llm_tokens/degraded/error/rag_empty),`render_prometheus()` 文本导出(含 degraded_rate/error_rate 计算)
  - `get_metrics()` 单例
- 接入:`app/api_agent.py` 在 `orchestrator.run()` 后 `persist_trace + record_request`;`app/main.py` 挂 `/metrics`(Prometheus 文本);`/agent/metrics` 提供 JSON 快照
- 测试 `tests/test_observability.py`(3 用例):全链运行落库三表且字段正确(spans 数=trace.spans 数、rank_policy 正确)、重复落库幂等、注册表导出格式,全部通过(累计 133 passed)

## 遇到的问题报错及解决方法

无。设计决策:V1 用进程内 MetricsRegistry 而非引入 prometheus_client 依赖——指标注册表实现简单可控,真实联调(模块 30)可平替;落库设计为「尽力而为」,可观测性故障不进入业务错误链。

## 上下游接口及依赖

- 上游:模块 10 Orchestrator(node_spans 回填)、模块 26 全链输出、模块 05 DB
- 下游:
  - 模块 28 评测:agent_traces/spans/recommendation_logs 是错误归因与节点级指标的数据源
  - 模块 29 压测:/metrics 输出 degraded_rate/error_rate 做验收
  - 运维侧:Prometheus 抓 /metrics;排障按 trace_id 回放
- 对外接口:`persist_trace()`、`MetricsRegistry`、`get_metrics()`、`GET /metrics`、`GET /agent/metrics`
