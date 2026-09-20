"""Find Person RAG Evidence Adapter(V1.2 §10.11)。

把知识证据转换成人员证据:
  article author        → article_expertise(inferred_from_article)
  PersonProfile         → inferred_from_profile / inferred_from_review(评价段)
  ResponsibilityItem    → formal_assignment

红线:RAG 相似度本身不得直接等价为"责任人分数"(§10.11);
文章作者不得自动标记为正式负责人(§13.1)。
"""
from __future__ import annotations

from app.contracts.evidence import EvidenceType, PersonEvidence
from app.contracts.mcp import RagHit


class RagEvidenceAdapter:
    """知识证据 → 人员证据 适配器。"""

    def to_person_evidence(self, hits: list[RagHit]) -> list[PersonEvidence]:
        """逐条转换;无法关联到具体人的 chunk(如部门文档)跳过。"""
        evidences: list[PersonEvidence] = []
        for hit in hits:
            evidences.extend(self._convert(hit))
        return evidences

    def _convert(self, hit: RagHit) -> list[PersonEvidence]:
        doc_type = hit.document_type
        doc_id = hit.document_id
        meta = hit.metadata or {}
        results: list[PersonEvidence] = []

        if doc_type == "responsibilities":
            owner = meta.get("owner_person_id", "")
            if owner:
                results.append(PersonEvidence(
                    person_id=owner, concept_id=None,
                    relation_type="formal_assignment",
                    evidence_type=EvidenceType.FORMAL_ASSIGNMENT,
                    source_type="okf_responsibility", source_id=doc_id,
                    confidence=1.0,  # 正式责任证据,与相似度无关(§10.11 红线)
                    detail={"document_id": doc_id, "chunk_id": hit.chunk_id},
                ))
        elif doc_type == "contents":
            author = meta.get("author_person_id", "")
            if author:
                results.append(PersonEvidence(
                    person_id=author, concept_id=None,
                    relation_type="article_expertise",
                    evidence_type=EvidenceType.INFERRED_FROM_ARTICLE,
                    source_type="okf_content", source_id=doc_id,
                    # RAG 相似度只作弱参考,上限压低(§10.11:相似度≠责任人分数)
                    confidence=min(0.6, 0.3 + hit.score),
                    detail={"document_id": doc_id, "title_hint": hit.content[:30]},
                ))
        elif doc_type == "people":
            person_id = doc_id.removeprefix("person-")
            is_review = "评价" in (meta.get("section") or "")
            results.append(PersonEvidence(
                person_id=person_id, concept_id=None,
                relation_type="review_inferred" if is_review else "profile_inferred",
                evidence_type=(EvidenceType.INFERRED_FROM_REVIEW if is_review
                               else EvidenceType.INFERRED_FROM_PROFILE),
                source_type="okf_profile", source_id=doc_id,
                confidence=min(0.55, 0.3 + hit.score),
                detail={"document_id": doc_id, "chunk_id": hit.chunk_id},
            ))
        return results
