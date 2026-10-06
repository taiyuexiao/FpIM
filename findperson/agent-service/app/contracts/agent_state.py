"""AgentState 统一状态模型(V1.2 §4.1)。

整个 Agent 主链唯一的运行状态。模块之间不得通过隐式全局变量传递业务数据,
一切数据经 AgentState 显式流转;Node 通过 StateUpdate 部分更新状态。
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.contracts.errors import ErrorCode
from app.contracts.trace import AgentTrace, NodeSpan


# ---------------------------------------------------------------- 枚举

class Intent(str, Enum):
    """一级意图(V1.2 §5.2)。

    架构收敛(查/写双轨)后:LLM 只产出 find_person / edit / unclear。
    KNOWLEDGE_QA、CHAT 已废弃(知识问答并入查人链、闲聊不再响应),
    枚举值保留仅为兼容历史 trace/日志/评测数据的反序列化。
    """

    FIND_PERSON = "find_person"
    KNOWLEDGE_QA = "knowledge_qa"  # 废弃:知识问答并入 find_person(expert_finding)
    EDIT = "edit"
    CHAT = "chat"                  # 废弃:闲聊不再单独响应,默认走查人链
    UNCLEAR = "unclear"


class QueryType(str, Enum):
    """find_person 的二级查询类型(V1.2 §5.2)。"""

    CONTACT_LOOKUP = "contact_lookup"
    EXPLICIT_RESPONSIBILITY = "explicit_responsibility"
    DIAGNOSTIC = "diagnostic"
    EXPERT_FINDING = "expert_finding"


class ConfidenceDecision(str, Enum):
    """ConfidenceGate 的判定结果(V1.2 §12.4)。"""

    ANSWER = "answer"
    CLARIFY = "clarify"
    NO_RESULT = "no_result"
    DEGRADED_ANSWER = "degraded_answer"


# ---------------------------------------------------------------- 子状态

class UserContext(BaseModel):
    """可信用户上下文(由接入层从 JWT/网关构建,客户端自报角色不作数)。"""

    user_id: str
    name: str = ""
    department_id: int | None = None
    department: str = ""
    roles: list[str] = Field(default_factory=list)
    sensitivity_level: int = 0  # 可见敏感级别上限,权限预过滤用


class RequestState(BaseModel):
    """请求态(V1.2 §4.1 RequestState)。"""

    trace_id: str
    run_id: str
    session_id: str | None = None
    user_context: UserContext
    original_query: str
    normalized_query: str = ""
    # 会话记忆:同会话最近 N 轮消息 [{role, text}],由接入层注入(agui/service.py、api_agent.py)
    history: list[dict[str, str]] = Field(default_factory=list)


class IntentState(BaseModel):
    """意图态(V1.2 §4.1 IntentState)。"""

    intent: Intent | None = None
    query_type: QueryType | None = None
    confidence: float = 0.0
    needs_clarification: bool = False
    clarify_question: str = ""


class UnderstandingState(BaseModel):
    """问题理解态(V1.2 §4.1 UnderstandingState + §6.1 QueryStructurer 输出)。"""

    mentioned_people: list[str] = Field(default_factory=list)
    mentioned_departments: list[str] = Field(default_factory=list)
    mentioned_systems: list[str] = Field(default_factory=list)
    objects: list[str] = Field(default_factory=list)
    symptoms: list[str] = Field(default_factory=list)
    explicit_terms: list[str] = Field(default_factory=list)
    duty_clues: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    # 字段来源:显式出现 explicit vs 模型推断 inferred(V1.2 §6.1 验收)
    field_sources: dict[str, str] = Field(default_factory=dict)


class ConceptState(BaseModel):
    """概念态(V1.2 §4.1 ConceptState + §7.6 Query ConceptLinker 输出)。"""

    candidate_concepts: list[dict[str, Any]] = Field(default_factory=list)
    resolved_concepts: list[dict[str, Any]] = Field(default_factory=list)
    expanded_concepts: list[dict[str, Any]] = Field(default_factory=list)
    ambiguous: bool = False
    concept_link_trace: list[dict[str, Any]] = Field(default_factory=list)


class RetrievalState(BaseModel):
    """检索态(V1.2 §4.1 RetrievalState)。"""

    structured_candidates: list[dict[str, Any]] = Field(default_factory=list)
    responsibility_evidence: list[dict[str, Any]] = Field(default_factory=list)
    rag_documents: list[dict[str, Any]] = Field(default_factory=list)
    rag_person_evidence: list[dict[str, Any]] = Field(default_factory=list)
    degraded_sources: list[str] = Field(default_factory=list)


class RankingState(BaseModel):
    """排序态(V1.2 §4.1 RankingState)。"""

    merged_candidates: list[dict[str, Any]] = Field(default_factory=list)
    rank_policy: str = ""
    ranked_candidates: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = 0.0
    gate_decision: ConfidenceDecision | None = None


class ResponseState(BaseModel):
    """响应态(V1.2 §4.1 ResponseState;§13.1 回答强制分事实/建议)。"""

    facts: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    recommendation_cards: list[dict[str, Any]] = Field(default_factory=list)
    # 写操作确认卡片(实施方案v3 §3.3:资料维护/内容发布/他人画像三类写操作;
    # 含卡片标识/动作类型/待写入字段/状态/提交目标;确认后禁止重复提交)
    confirmation_card: dict[str, Any] | None = None
    final_answer: str = ""
    clarification: str = ""


class ExecutionState(BaseModel):
    """执行态(V1.2 §4.1 ExecutionState)。"""

    current_stage: str = ""
    degraded: bool = False
    errors: list[dict[str, Any]] = Field(default_factory=list)
    node_spans: list[NodeSpan] = Field(default_factory=list)
    total_latency_ms: float | None = None


# ---------------------------------------------------------------- 总状态

class AgentState(BaseModel):
    """Agent 主链唯一运行状态。可 JSON 序列化,用于 Trace 回放与评测。"""

    request: RequestState
    intent: IntentState = Field(default_factory=IntentState)
    understanding: UnderstandingState = Field(default_factory=UnderstandingState)
    concept: ConceptState = Field(default_factory=ConceptState)
    retrieval: RetrievalState = Field(default_factory=RetrievalState)
    ranking: RankingState = Field(default_factory=RankingState)
    response: ResponseState = Field(default_factory=ResponseState)
    execution: ExecutionState = Field(default_factory=ExecutionState)
    trace: AgentTrace = Field(default_factory=AgentTrace)


class StateUpdate(BaseModel):
    """Node 执行结果:只携带本子状态的变更,由 Orchestrator 合并回 AgentState。

    Node 不允许直接改写其他子状态(V1.2 §4.2:Node = 读 State + 调 Service + 写回 State)。
    """

    intent: IntentState | None = None
    understanding: UnderstandingState | None = None
    concept: ConceptState | None = None
    retrieval: RetrievalState | None = None
    ranking: RankingState | None = None
    response: ResponseState | None = None
    # 执行层信息
    degraded: bool = False
    error: dict[str, Any] | None = None
    terminate: bool = False  # 请求提前终态(如澄清、chat 直答)


def apply_update(state: AgentState, update: StateUpdate) -> AgentState:
    """把 StateUpdate 合并进 AgentState(Orchestrator 使用)。

    RetrievalState 的列表字段采用「去重追加」语义而非整体替换:
    并行检索节点(§3.1 RetrievalCoordinator)各自从同一 base 拷贝后写自己的字段,
    追加合并保证双路证据不会互相覆盖;串行节点因 model_copy 已含旧值,
    去重追加与替换等价。
    """
    for field in ("intent", "understanding", "concept", "retrieval", "ranking", "response"):
        value = getattr(update, field)
        if value is None:
            continue
        if field == "retrieval":
            _merge_retrieval(state.retrieval, value)
        else:
            setattr(state, field, value)
    if update.degraded:
        state.execution.degraded = True
    if update.error:
        state.execution.errors.append(update.error)
    return state


def _merge_retrieval(current, incoming) -> None:
    """RetrievalState 列表字段去重追加合并。"""
    import json
    for field in ("structured_candidates", "responsibility_evidence",
                  "rag_documents", "rag_person_evidence", "degraded_sources"):
        existing = getattr(current, field)
        seen = {json.dumps(x, sort_keys=True, ensure_ascii=False, default=str) for x in existing}
        for item in getattr(incoming, field):
            key = json.dumps(item, sort_keys=True, ensure_ascii=False, default=str)
            if key not in seen:
                existing.append(item)
                seen.add(key)


# ---------------------------------------------------------------- Node 读写字段矩阵
# V1.2 §4.1 验收:各 Node 读写字段矩阵。新增 Node 时在此登记,不得越权读写。

NODE_FIELD_MATRIX: dict[str, dict[str, list[str]]] = {
    "IntentNode": {
        "reads": ["request.normalized_query", "request.session_id", "request.history"],
        "writes": ["intent"],
    },
    "QueryStructurerNode": {
        "reads": ["request.normalized_query", "intent", "request.history"],
        "writes": ["understanding"],
    },
    "ConceptLinkerNode": {
        "reads": ["understanding", "intent"],
        "writes": ["concept"],
    },
    "StructuredRetrievalNode": {
        "reads": ["concept", "intent", "request.user_context"],
        "writes": ["retrieval.structured_candidates", "retrieval.responsibility_evidence"],
    },
    "KnowledgeRetrievalNode": {
        "reads": ["concept", "intent", "request.user_context", "request.original_query"],
        "writes": ["retrieval.rag_documents", "retrieval.rag_person_evidence"],
    },
    "CandidateMergerNode": {
        "reads": ["retrieval"],
        "writes": ["ranking.merged_candidates"],
    },
    "PeopleRankerNode": {
        "reads": ["ranking.merged_candidates", "intent.query_type"],
        "writes": ["ranking.ranked_candidates", "ranking.rank_policy", "ranking.confidence"],
    },
    "RelatedPeopleFallbackNode": {
        "reads": ["ranking.ranked_candidates", "ranking.confidence", "request.normalized_query"],
        "writes": ["ranking.ranked_candidates", "ranking.rank_policy", "ranking.confidence"],
    },
    "ConfidenceGateNode": {
        "reads": ["ranking", "concept"],
        "writes": ["ranking.gate_decision"],
    },
    "AnswerBuilderNode": {
        "reads": ["ranking", "retrieval", "response", "intent"],
        "writes": ["response"],
    },
}
