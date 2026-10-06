"""模块 15:CandidateMerger / PeopleRanker / ConfidenceGate 测试。"""
from app.agent.candidate_merger import CandidateMerger, MergedPersonCandidate
from app.agent.people_ranker import ConfidenceGate, PeopleRanker
from app.contracts.agent_state import ConfidenceDecision, QueryType
from app.contracts.evidence import EvidenceType, PersonEvidence


def _ev(pid: str, etype: EvidenceType, conf: float = 1.0, level: str = "leaf_exact") -> dict:
    return PersonEvidence(
        person_id=pid, relation_type="self_declared_scope", evidence_type=etype,
        source_type="raw_tag", confidence=conf,
        detail={"match_level": level},
    ).model_dump()


def test_merger_dedup_keeps_all_evidence() -> None:
    """按 person_id 去重但保留全部证据(§12.2)。"""
    merger = CandidateMerger()
    merged = merger.merge([
        _ev("p-1", EvidenceType.EXPLICIT_SELF_TAG),
        _ev("p-1", EvidenceType.INFERRED_FROM_PROFILE, conf=0.6),
        _ev("p-2", EvidenceType.EXPLICIT_SELF_TAG),
    ])
    assert len(merged) == 2
    p1 = next(c for c in merged if c.person_id == "p-1")
    assert len(p1.evidences) == 2
    assert {e.evidence_type for e in p1.evidences} == {
        EvidenceType.EXPLICIT_SELF_TAG, EvidenceType.INFERRED_FROM_PROFILE}


def test_merger_formal_first() -> None:
    """正式责任记录挂到责任人,且排最前(§8.1:正式责任证据始终最高)。"""
    merger = CandidateMerger()
    merged = merger.merge(
        [_ev("p-2", EvidenceType.EXPLICIT_SELF_TAG)],
        formal_responsibility=[{"responsibility_id": "ra-1", "owner_person_id": "p-1",
                                "title": "Dify平台运维"}],
    )
    assert merged[0].person_id == "p-1"
    assert merged[0].has_formal is True


def test_ranker_responsibility_policy() -> None:
    """responsibility_policy:正式责任 > 精确自填 > 泛化自填(§12.3)。"""
    merger = CandidateMerger()
    merged = merger.merge([
        _ev("p-generalized", EvidenceType.EXPLICIT_SELF_TAG, conf=1.0, level="concept_generalized"),
        _ev("p-exact", EvidenceType.EXPLICIT_SELF_TAG, conf=0.9, level="leaf_exact"),
    ])
    ranked, policy, _ = PeopleRanker().rank(merged, QueryType.EXPLICIT_RESPONSIBILITY)
    assert policy == "responsibility_policy"
    assert ranked[0]["person_id"] == "p-exact"  # 泛化降权,精确在前


def test_ranker_expert_policy_not_equal_formal() -> None:
    """expert_policy:正式负责人不天然等于最佳专家(§12.3)。"""
    merger = CandidateMerger()
    m1 = merger.merge([_ev("p-expert", EvidenceType.INFERRED_FROM_ARTICLE, conf=0.95)])
    merged = merger.merge(
        [_ev("p-expert", EvidenceType.INFERRED_FROM_ARTICLE, conf=0.95)],
        formal_responsibility=[{"responsibility_id": "ra-1",
                                "owner_person_id": "p-formal", "title": "X"}],
    )
    ranked, policy, _ = PeopleRanker().rank(merged, QueryType.EXPERT_FINDING)
    assert policy == "expert_policy"
    # formal 权重仅 0.3,强文章证据的专家应排前
    assert ranked[0]["person_id"] == "p-expert"


def test_gate_decisions() -> None:
    """ConfidenceGate 五态判定(§12.4)+ 同概念并列人选不澄清。"""
    gate = ConfidenceGate()
    assert gate.decide([]) == ConfidenceDecision.NO_RESULT
    weak = [{"person_id": "p", "score": 0.1, "has_formal": False}]
    assert gate.decide(weak) == ConfidenceDecision.NO_RESULT
    close = [{"person_id": "a", "score": 0.5, "has_formal": False,
              "evidences": [{"concept_id": "c-1"}]},
             {"person_id": "b", "score": 0.49, "has_formal": False,
              "evidences": [{"concept_id": "c-2"}]}]
    assert gate.decide(close) == ConfidenceDecision.CLARIFY  # 不同概念 → 歧义澄清
    tied = [{"person_id": "a", "score": 0.5, "has_formal": False,
             "evidences": [{"concept_id": "c-1"}]},
            {"person_id": "b", "score": 0.5, "has_formal": False,
             "evidences": [{"concept_id": "c-1"}]}]
    assert gate.decide(tied) == ConfidenceDecision.ANSWER    # 同概念并列 → 并列返回
    strong = [{"person_id": "a", "score": 0.9, "has_formal": True}]
    assert gate.decide(strong) == ConfidenceDecision.ANSWER
    assert gate.decide(strong, degraded=True) == ConfidenceDecision.DEGRADED_ANSWER
    assert gate.decide(strong, concept_ambiguous=True) == ConfidenceDecision.CLARIFY
