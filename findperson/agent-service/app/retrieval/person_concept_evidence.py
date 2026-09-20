"""PersonConceptEvidence Repository(V1.2 §9.2)。

基于 agent.person_concept_evidence 视图(person_tags × tag_concept_map 实时连接),
支持按 concept_id 低成本、确定性召回人员;每条证据保留 source_raw_tag 用于解释。
"""
from __future__ import annotations

from app.contracts.concept import PersonConceptEvidence
from app.core import db


class PersonConceptEvidenceRepository:
    """人员—概念证据查询。"""

    async def find_by_concepts(
        self, concept_ids: list[str], *, active_only: bool = True,
    ) -> list[PersonConceptEvidence]:
        """按 concept_id 集合召回人员证据(§9.2 验收:可通过 concept_id 直接召回人员)。"""
        if not concept_ids:
            return []
        sql = (
            "SELECT person_id, concept_id, relation_type, evidence_type, source_type,"
            "       source_id, source_raw_tag, confidence, verification_status"
            " FROM agent.person_concept_evidence WHERE concept_id = ANY($1)"
        )
        if active_only:
            sql += " AND verification_status = 'active'"
        rows = await db.fetch(sql, concept_ids)
        return [
            PersonConceptEvidence(
                person_id=r["person_id"], concept_id=r["concept_id"],
                relation_type=r["relation_type"], evidence_type=r["evidence_type"],
                source_type=r["source_type"], source_id=r["source_id"],
                source_raw_tag=r["source_raw_tag"], confidence=r["confidence"],
                verification_status=r["verification_status"],
            )
            for r in rows
        ]

    async def find_by_person(self, person_id: str) -> list[PersonConceptEvidence]:
        """查某人的全部概念证据(详情展示用)。"""
        rows = await db.fetch(
            "SELECT person_id, concept_id, relation_type, evidence_type, source_type,"
            "       source_id, source_raw_tag, confidence, verification_status"
            " FROM agent.person_concept_evidence WHERE person_id = $1",
            person_id,
        )
        return [
            PersonConceptEvidence(
                person_id=r["person_id"], concept_id=r["concept_id"],
                relation_type=r["relation_type"], evidence_type=r["evidence_type"],
                source_type=r["source_type"], source_id=r["source_id"],
                source_raw_tag=r["source_raw_tag"], confidence=r["confidence"],
                verification_status=r["verification_status"],
            )
            for r in rows
        ]
