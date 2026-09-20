# 模块 03:AgentState 契约

## 背景

对应 V1.2 §4.1(AgentState 统一状态模型),阶段 0 公共契约之首。文档要求:「设计整个 Agent 主链唯一的运行状态」「模块不得通过隐式全局变量互相传递业务数据」「可序列化用于 Trace 和评测」「新增 Node 不需要修改已有 Node 的私有数据结构」。所有后续 Node(意图/结构化/概念链接/检索/排序/回答)都围绕这份状态读写。

## 任务

- 输入:/agent/chat 请求、可信 user_context、各下游模块的输入输出需求
- 输出:Pydantic AgentState 模型、StateUpdate 合并机制、Node 读写字段矩阵
- 验收:JSON 序列化往返;StateUpdate 部分合并不越权;意图/查询类型枚举与 §5.2 一致

## 实现方式

- `app/contracts/agent_state.py`
  - 枚举:`Intent`(5 个一级意图)、`QueryType`(4 个找人二级类型)、`ConfidenceDecision`(§12.4 四态)
  - `UserContext`:可信用户上下文,含 `sensitivity_level`(权限预过滤用,§5.1:客户端自报角色不作数)
  - 8 个子状态严格按 §4.1:RequestState / IntentState / UnderstandingState / ConceptState / RetrievalState / RankingState / ResponseState / ExecutionState
    - UnderstandingState 增加 `objects`(§6.1 QueryStructurer JSON 中有 objects)与 `field_sources`(§6.1 验收:区分显式出现与模型推断)
    - ConceptState 按 §7.6 输出结构(candidate/resolved/expanded/ambiguous/link_trace)
  - `StateUpdate`:Node 只携带自己负责的子状态变更;`apply_update()` 由 Orchestrator 合并,degraded/error 汇入 ExecutionState
  - `NODE_FIELD_MATRIX`:9 个主链节点的读写字段矩阵(§4.1 验收项),新增 Node 必须在此登记
- 测试 `tests/test_contracts_agent_state.py`:4 个用例(JSON 往返、部分合并不越权、矩阵覆盖主链节点、枚举与文档一致),全部通过(累计 8 passed)

## 遇到的问题报错及解决方法

无。一次通过。

## 上下游接口及依赖

- 上游:模块 02 的 `AgentTrace/NodeSpan`(ExecutionState.node_spans)
- 下游:
  - `AgentOrchestrator`(模块 10)驱动 AgentState 流转,按 NODE_FIELD_MATRIX 约束 Node 读写
  - 意图(模块 11)写 IntentState;QueryStructurer(模块 12)写 UnderstandingState;ConceptLinker(模块 13/17/18)写 ConceptState;检索(模块 14/24/26)写 RetrievalState;排序(模块 15)写 RankingState;AnswerBuilder(模块 16)写 ResponseState
  - 评测(模块 28)序列化 AgentState 做回放与归因
- 对外接口:`AgentState`、`StateUpdate`、`apply_update`、`Intent`、`QueryType`、`ConfidenceDecision`、`UserContext`、`NODE_FIELD_MATRIX`
