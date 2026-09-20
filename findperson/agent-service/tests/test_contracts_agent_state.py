"""模块 03:AgentState 契约测试。"""
from app.contracts.agent_state import (
    NODE_FIELD_MATRIX,
    AgentState,
    Intent,
    IntentState,
    QueryType,
    RequestState,
    StateUpdate,
    UserContext,
    apply_update,
)


def _make_state() -> AgentState:
    return AgentState(
        request=RequestState(
            trace_id="t-1",
            run_id="r-1",
            session_id="s-1",
            user_context=UserContext(user_id="p-0001", name="王丹"),
            original_query="谁负责智能体平台?",
            normalized_query="谁负责智能体平台",
        )
    )


def test_state_json_roundtrip() -> None:
    """AgentState 可 JSON 序列化往返(V1.2 §4.1 验收:可序列化用于 Trace 和评测)。"""
    state = _make_state()
    state.intent = IntentState(intent=Intent.FIND_PERSON, query_type=QueryType.EXPLICIT_RESPONSIBILITY, confidence=0.98)
    restored = AgentState.model_validate_json(state.model_dump_json())
    assert restored.request.user_context.user_id == "p-0001"
    assert restored.intent.intent == Intent.FIND_PERSON
    assert restored.intent.query_type == QueryType.EXPLICIT_RESPONSIBILITY


def test_apply_update_partial() -> None:
    """StateUpdate 只合并携带的子状态,不影响其他子状态。"""
    state = _make_state()
    update = StateUpdate(
        intent=IntentState(intent=Intent.FIND_PERSON, confidence=0.9),
        degraded=True,
        error={"code": "LLM_ERROR", "message": "x"},
    )
    apply_update(state, update)
    assert state.intent.intent == Intent.FIND_PERSON
    assert state.execution.degraded is True
    assert len(state.execution.errors) == 1
    assert state.understanding.mentioned_systems == []  # 未被触碰


def test_node_field_matrix_covers_main_chain() -> None:
    """Node 读写字段矩阵覆盖主链全部节点(V1.2 §4.1 验收:矩阵冻结)。"""
    expected_nodes = {
        "IntentNode", "QueryStructurerNode", "ConceptLinkerNode",
        "StructuredRetrievalNode", "KnowledgeRetrievalNode",
        "CandidateMergerNode", "PeopleRankerNode", "ConfidenceGateNode",
        "AnswerBuilderNode",
    }
    assert expected_nodes <= set(NODE_FIELD_MATRIX.keys())
    for node, rw in NODE_FIELD_MATRIX.items():
        assert rw["reads"], f"{node} 必须声明读字段"
        assert rw["writes"], f"{node} 必须声明写字段"


def test_enums_match_spec() -> None:
    """意图与查询类型枚举与 V1.2 §5.2 完全一致。"""
    assert {i.value for i in Intent} == {"find_person", "knowledge_qa", "edit", "chat", "unclear"}
    assert {q.value for q in QueryType} == {
        "contact_lookup", "explicit_responsibility", "diagnostic", "expert_finding",
    }
