"""主召回无结果时的大模型相关人员推荐测试。"""
import pytest

from app.agent.answer_builder import AnswerBuilder
from app.agent.nodes.ranking import RelatedPeopleFallbackNode
from app.agent.orchestrator import ServiceRegistry
from app.agent.people_ranker import ConfidenceGate
from app.contracts.agent_state import (
    AgentState, ConfidenceDecision, Intent, IntentState, QueryType, RequestState, UserContext,
)


def _state() -> AgentState:
    state = AgentState(request=RequestState(
        trace_id="trace-related", run_id="run-related",
        user_context=UserContext(user_id="p-user"),
        original_query="谁负责Rust", normalized_query="谁负责Rust",
    ))
    state.intent = IntentState(
        intent=Intent.FIND_PERSON, query_type=QueryType.EXPERT_FINDING)
    return state


class StubRelatedPeopleFallback:
    def __init__(self) -> None:
        self.called = 0

    async def recommend(self, query: str) -> list[dict]:
        self.called += 1
        return [
            {"person": {"id": f"p-{i}"}, "relevance": 0.9 - i * 0.1,
             "reason": f"具备第{i}项相近技术经验",
             "selection_source": "llm_related_fallback"}
            for i in range(1, 5)
        ]


@pytest.mark.asyncio
async def test_empty_primary_result_returns_one_to_three_related_people() -> None:
    state = _state()
    fallback = StubRelatedPeopleFallback()
    node = RelatedPeopleFallbackNode()
    update = await node.execute(
        state, ServiceRegistry({"related_people_fallback": fallback}))

    ranked = update.ranking.ranked_candidates
    assert fallback.called == 1
    assert len(ranked) == 3
    assert [item["person_id"] for item in ranked] == ["p-1", "p-2", "p-3"]
    assert all(item["is_related_fallback"] for item in ranked)
    assert update.ranking.rank_policy == "llm_related_fallback_policy"
    assert ConfidenceGate().decide(ranked) == ConfidenceDecision.ANSWER


@pytest.mark.asyncio
async def test_primary_high_match_always_wins() -> None:
    state = _state()
    state.ranking.ranked_candidates = [{
        "person_id": "p-exact", "score": 0.8, "has_formal": False,
        "evidence_count": 1, "evidences": [], "responsibilities": [],
    }]
    fallback = StubRelatedPeopleFallback()
    update = await RelatedPeopleFallbackNode().execute(
        state, ServiceRegistry({"related_people_fallback": fallback}))

    assert fallback.called == 0
    assert update.ranking is None


@pytest.mark.asyncio
async def test_answer_marks_related_people_as_not_exact(monkeypatch) -> None:
    state = _state()
    state.ranking.gate_decision = ConfidenceDecision.ANSWER
    state.ranking.ranked_candidates = [{
        "person_id": "p-1", "score": 0.35, "feedback_adjust": 0.0,
        "has_formal": False, "evidence_count": 1, "responsibilities": [],
        "is_related_fallback": True,
        "evidences": [{"evidence_type": "inferred_from_profile", "detail": {
            "no_exact_match": True, "reason": "熟悉相近的后端开发技术栈"}}],
    }]

    async def fake_fetch(*args, **kwargs):
        return [{"id": "p-1", "name": "张老师"}]

    monkeypatch.setattr("app.agent.answer_builder.db.fetch", fake_fetch)
    response = await AnswerBuilder().build(state)

    assert "未找到与问题完全匹配" in response.final_answer
    assert "张老师：熟悉相近的后端开发技术栈" not in response.final_answer
    assert "并非正式责任或完全匹配结果" not in response.final_answer
    assert "降级路径结果" not in response.final_answer
    assert response.final_answer == "未找到与问题完全匹配的正式责任人或专家，以下是可能相关的老师。"
    assert len(response.recommendation_cards) == 1
