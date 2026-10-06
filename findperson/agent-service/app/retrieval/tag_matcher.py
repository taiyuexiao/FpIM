"""TagMatcher / Structured Concept Retriever(V1.2 §9.3)。

两级匹配:
  一级(细分层):叶子 Concept + 原始标签精确职责 → leaf_exact
  二级(概念层):父 Concept / 近义 Concept 经 concept_relations 有限泛化 → concept_generalized

细分标签优先解决职责区分,Concept 解决不同语言表达(§9.3)。
自填负责领域证据 relation_type=self_declared_scope,不得当作正式责任(§7.9)。
"""
from __future__ import annotations

from app.contracts.concept import RelationType
from app.contracts.evidence import EvidenceType, PersonEvidence
from app.core import db
from app.retrieval.person_concept_evidence import PersonConceptEvidenceRepository

# 泛化允许的关系与最大跳数(§7.7:默认限制一跳或两跳扩展)
EXPAND_RELATIONS = (
    RelationType.BROADER_THAN.value,
    RelationType.NARROWER_THAN.value,
    RelationType.RELATED_TO.value,
    RelationType.COMPONENT_OF.value,
)
MAX_EXPAND_HOPS = 1


class TagMatcher:
    """结构化概念检索器。"""

    def __init__(self, pce_repo: PersonConceptEvidenceRepository | None = None) -> None:
        self._pce = pce_repo or PersonConceptEvidenceRepository()

    async def match(
        self, resolved_concepts: list[dict], *, expand: bool = True,
    ) -> tuple[list[PersonEvidence], list[dict]]:
        """两级匹配。

        返回 (人员证据, 扩展概念列表)。扩展概念写入 ConceptState.expanded_concepts。
        """
        concept_ids = [c["concept_id"] for c in resolved_concepts if c.get("concept_id")]
        if not concept_ids:
            return [], []

        # ---- 一级:叶子概念精确匹配(细分层) ----
        evidences: list[PersonEvidence] = []
        for e in await self._pce.find_by_concepts(concept_ids):
            evidences.append(PersonEvidence(
                person_id=e.person_id, concept_id=e.concept_id,
                relation_type=e.relation_type,           # self_declared_scope,非 responsible_for
                evidence_type=EvidenceType.EXPLICIT_SELF_TAG,
                source_type=e.source_type, source_id=e.source_id,
                confidence=e.confidence,
                verification_status=e.verification_status,
                detail={"match_level": "leaf_exact", "source_raw_tag": e.source_raw_tag},
            ))

        # ---- 二级:概念关系泛化(概念层,默认一跳) ----
        expanded: list[dict] = []
        if expand:
            rows = await db.fetch(
                "SELECT src_concept_id, dst_concept_id, relation_type"
                " FROM agent.concept_relations"
                " WHERE relation_type = ANY($1) AND (src_concept_id = ANY($2) OR dst_concept_id = ANY($2))",
                list(EXPAND_RELATIONS), concept_ids,
            )
            expanded_ids: set[str] = set()
            for r in rows:
                neighbor = (r["dst_concept_id"] if r["src_concept_id"] in concept_ids
                            else r["src_concept_id"])
                if neighbor in concept_ids or neighbor in expanded_ids:
                    continue
                expanded_ids.add(neighbor)
                expanded.append({
                    "concept_id": neighbor,
                    "from_concept_id": (r["src_concept_id"] if r["src_concept_id"] in concept_ids
                                        else r["dst_concept_id"]),
                    "relation_type": r["relation_type"],
                })
            if expanded_ids:
                for e in await self._pce.find_by_concepts(list(expanded_ids)):
                    evidences.append(PersonEvidence(
                        person_id=e.person_id, concept_id=e.concept_id,
                        relation_type=e.relation_type,
                        evidence_type=EvidenceType.EXPLICIT_SELF_TAG,
                        source_type=e.source_type, source_id=e.source_id,
                        confidence=round(e.confidence * 0.8, 4),  # 泛化降权
                        verification_status=e.verification_status,
                        relation_path=[*concept_ids, e.concept_id],
                        detail={"match_level": "concept_generalized",
                                "source_raw_tag": e.source_raw_tag},
                    ))
        return evidences, expanded
