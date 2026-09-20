# 模块 10:AgentOrchestrator + Node 接口

## 背景

对应 V1.2 §3.1(Agent 编排方式:不引入完整 StateGraph Runtime,采用 AgentOrchestrator + AgentState + Node/Service 轻量有状态工作流,Graph-ready)和 §4.2(Orchestrator 只负责「执行顺序/条件分流/并行调度/超时/异常收敛/状态传递/降级/终态」,不实现概念算法、SQL、RAG、Ranking、Prompt 业务逻辑;Node = 读 State + 调 Service + 写回 State)。这是整个 Agent 主链的骨架,模块 11-16 的全部 Node 都挂在它上面。

## 任务

- 输入:AgentState(模块 03 契约)
- 输出:AgentNode 基类、ServiceRegistry、AgentOrchestrator(串行/条件/并行/超时/降级/终止/Trace)
- 验收:Node 标准接口;节点超时机制;并行 RetrievalCoordinator;节点失败不导致 State 不可解释;可完整回放一次运行轨迹

## 实现方式

- `app/agent/orchestrator.py`
  - `AgentNode` ABC:`name`/`timeout_ms`/`on_error`(terminate|degrade)+ `execute(state, services) -> StateUpdate`;与 §4.2 的 Python 约定一致(多一个 services 注入)
  - `ServiceRegistry`:宽松 dict 容器 + `get()/register()`,新增 Service 不改 Orchestrator(§4.1「新增 Node 不需要修改已有结构」)
  - `AgentOrchestrator`:
    - `add(node, condition=...)` 串行 + 显式条件分流;`add_parallel(nodes, label=...)` 并行组(对应 RetrievalCoordinator 双路检索)
    - `run(state)`:逐 _Step 执行,`asyncio.gather` 并行;结束后汇总 trace 总耗时、node_spans 回填 ExecutionState
    - `_run_node`:`asyncio.wait_for` 节点级超时;异常收敛三类——`TimeoutError`→span TIMEOUT、`AgentError`(degraded 则降级继续,否则按 on_error)、未知异常→INTERNAL_ERROR 收敛,**不让单节点炸掉整条链**
    - 失败策略:`degrade` = 记 error + `degraded=true` 继续;`terminate` = 记 error + 终止主链(`__terminated__`)
    - 每个节点自动开/关 NodeSpan(模块 02 Trace 契约),输入输出摘要入 span
- 测试 `tests/test_orchestrator.py`(6 用例,假 Node 验证编排语义):串行顺序+条件跳过、并行组真实并发(2×50ms 总耗时 <95ms)、超时降级继续、关键节点失败终止、ServiceRegistry 注入与未注册报错、trace JSON 回放,全部通过(累计 51 passed)

## 遇到的问题报错及解决方法

无。一处设计决策:`StateUpdate` 增加 `terminate` 字段用于「chat 直答/澄清」等提前终态(V1.2 §5.2 chat 简单实现、unclear 返回澄清),终止语义由 Orchestrator 统一执行而不是 Node 自己中断循环。

## 上下游接口及依赖

- 上游:模块 03 AgentState/StateUpdate/apply_update、模块 02 Trace/错误模型
- 下游:
  - 模块 11-16 的全部 Node(Intent/QueryStructurer/ConceptLinker/Retrieval/Merger/Ranker/Gate/AnswerBuilder)继承 AgentNode 注册进来
  - 模块 16 的 /agent/chat 装配主链:串行意图→结构化→概念链接,`add_parallel` 双路检索,再串行融合排序回答
  - 模块 27 Trace 落库直接消费 ExecutionState.node_spans
  - 模块 29 稳定性在此层加全链超时/熔断统计
- 对外接口:`AgentNode`、`ServiceRegistry`、`AgentOrchestrator`、`ON_ERROR_TERMINATE/DEGRADE`
