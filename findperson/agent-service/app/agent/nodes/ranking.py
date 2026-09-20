"""Merger/Ranker/Gate 三个 Node:把服务挂到编排主链上。"""
from __future__ import annotations

from app.agent.candidate_merger import CandidateMerger
from app.agent.orchestrator import AgentNode, ServiceRegistry
from app.agent.people_ranker import ConfidenceGate, PeopleRanker
from app.contracts.agent_state import AgentState, Intent, StateUpdate
from app.contracts.evidence import EvidenceType


class CandidateMergerNode(AgentNode):
    """候选融合节点(§12.2)。"""

    name = "CandidateMergerNode"
    timeout_ms = 5000
    on_error = "degrade"

    async def execute(self, state: AgentState, services: ServiceRegistry) -> StateUpdate:
        if state.intent.intent != Intent.FIND_PERSON:
            return StateUpdate()
        merger = services.get("candidate_merger") if "candidate_merger" in services.services else CandidateMerger()
        merged = merger.merge(
            state.retrieval.structured_candidates,
            state.retrieval.rag_person_evidence,
            state.retrieval.responsibility_evidence,
        )
        update = StateUpdate()
        update.ranking = state.ranking.model_copy(deep=True)
        update.ranking.merged_candidates = [c.to_dict() for c in merged]
        return update


class PeopleRankerNode(AgentNode):
    """人员排序节点(§12.3)。"""

    name = "PeopleRankerNode"
    timeout_ms = 5000
    on_error = "degrade"

    async def execute(self, state: AgentState, services: ServiceRegistry) -> StateUpdate:
        if state.intent.intent != Intent.FIND_PERSON:
            return StateUpdate()
        merger = services.get("candidate_merger") if "candidate_merger" in services.services else CandidateMerger()
        # 用户反馈回流:聚合反馈微调排序;反馈服务故障不阻断主链(降级为无调整)
        feedback_adjust: dict[str, float] = {}
        try:
            from app.feedback.service import FeedbackService
            fb = (services.get("feedback_service")
                  if "feedback_service" in services.services else FeedbackService())
            feedback_adjust = await fb.person_adjustments()
        except Exception:  # noqa: BLE001 —— 反馈不可用不影响排序主链
            feedback_adjust = {}
        # ranked 输入是 merge 结果的字典形式,还原为轻量对象排序
        candidates = []
        from app.agent.candidate_merger import MergedPersonCandidate
        from app.contracts.evidence import PersonEvidence
        for raw in state.ranking.merged_candidates:
            c = MergedPersonCandidate(raw["person_id"])
            c.evidences = [PersonEvidence.model_validate(e) for e in raw["evidences"]]
            c.responsibilities = raw.get("responsibilities", [])
            candidates.append(c)
        ranker = services.get("people_ranker") if "people_ranker" in services.services else PeopleRanker()
        ranked, policy, top1 = ranker.rank(
            candidates, state.intent.query_type,
            query=state.request.normalized_query or state.request.original_query,
            feedback_adjust=feedback_adjust,
        )
        update = StateUpdate()
        update.ranking = state.ranking.model_copy(deep=True)
        update.ranking.ranked_candidates = ranked
        update.ranking.rank_policy = policy
        update.ranking.confidence = top1
        return update


class RelatedPeopleFallbackNode(AgentNode):
    """双路召回无可用结果时，由 LLM 从真实人员库选择 1～3 位可能相关人员。"""

    name = "RelatedPeopleFallbackNode"
    timeout_ms = 35000
    on_error = "degrade"

    async def execute(self, state: AgentState, services: ServiceRegistry) -> StateUpdate:
        if state.intent.intent != Intent.FIND_PERSON:
            return StateUpdate()
        ranked = state.ranking.ranked_candidates
        if ranked and ranked[0].get("score", 0.0) >= 0.05:
            return StateUpdate()  # 主召回优先，绝不让 LLM 覆盖高匹配结果

        from app.agent.related_people_fallback import RelatedPeopleFallback

        recommender = (services.get("related_people_fallback")
                       if "related_people_fallback" in services.services
                       else RelatedPeopleFallback())
        recommendations = await recommender.recommend(
            state.request.normalized_query or state.request.original_query)
        if not recommendations:
            return StateUpdate()

        fallback_ranked = []
        for item in recommendations[:3]:
            person = item["person"]
            relevance = float(item.get("relevance") or 0.0)
            # 相关兜底分数只用于保持模型给出的顺序并让卡片展示，永远低于精确证据。
            score = round(0.05 + min(1.0, max(0.0, relevance)) * 0.4, 4)
            fallback_ranked.append({
                "person_id": str(person["id"]),
                "score": score,
                "feedback_adjust": 0.0,
                "has_formal": False,
                "evidence_count": 1,
                "evidences": [{
                    "person_id": str(person["id"]),
                    "concept_id": None,
                    "relation_type": "llm_related_fallback",
                    "evidence_type": EvidenceType.INFERRED_FROM_PROFILE.value,
                    "source_type": "public.people",
                    "source_id": str(person["id"]),
                    "confidence": relevance,
                    "verification_status": "active",
                    "freshness": None,
                    "relation_path": [],
                    "detail": {
                        "match_level": "related_fallback",
                        "reason": item.get("reason") or "具备相近岗位或领域经验",
                        "selection_source": item.get("selection_source", "llm_related_fallback"),
                        "no_exact_match": True,
                    },
                }],
                "responsibilities": [],
                "is_related_fallback": True,
            })

        update = StateUpdate()
        update.ranking = state.ranking.model_copy(deep=True)
        update.ranking.ranked_candidates = fallback_ranked
        update.ranking.rank_policy = "llm_related_fallback_policy"
        update.ranking.confidence = fallback_ranked[0]["score"]
        return update


class ConfidenceGateNode(AgentNode):
    """置信度闸门节点(§12.4)。"""

    name = "ConfidenceGateNode"
    timeout_ms = 3000
    on_error = "degrade"

    async def execute(self, state: AgentState, services: ServiceRegistry) -> StateUpdate:
        if state.intent.intent != Intent.FIND_PERSON:
            return StateUpdate()
        gate = services.get("confidence_gate") if "confidence_gate" in services.services else ConfidenceGate()
        decision = gate.decide(
            state.ranking.ranked_candidates,
            concept_ambiguous=state.concept.ambiguous,
            degraded=state.execution.degraded,
            resolved_concepts=state.concept.resolved_concepts,
        )
        update = StateUpdate()
        update.ranking = state.ranking.model_copy(deep=True)
        update.ranking.gate_decision = decision
        return update
