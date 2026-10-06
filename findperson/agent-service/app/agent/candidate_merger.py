"""CandidateMerger(V1.2 §12.2)。

按 person_id 去重,但保留每人的全部证据。
禁止 structured_score + rag_score 直接相加得到最终人员分数——
证据语义不同,融合只合并证据清单,打分是 PeopleRanker 的事。
"""
from __future__ import annotations

from app.contracts.evidence import EvidenceType, PersonEvidence


class MergedPersonCandidate:
    """融合后的候选人:一人一条,携带全部证据。"""

    def __init__(self, person_id: str) -> None:
        self.person_id = person_id
        self.evidences: list[PersonEvidence] = []
        self.responsibilities: list[dict] = []  # 正式责任记录(§9.4 输出)

    @property
    def has_formal(self) -> bool:
        """是否持有正式责任证据(ConfidenceGate 与 responsibility_policy 的关键输入)。"""
        return bool(self.responsibilities) or any(
            e.evidence_type == EvidenceType.FORMAL_ASSIGNMENT for e in self.evidences
        )

    def to_dict(self) -> dict:
        return {
            "person_id": self.person_id,
            "has_formal": self.has_formal,
            "evidences": [e.model_dump() for e in self.evidences],
            "responsibilities": self.responsibilities,
        }


class CandidateMerger:
    """候选融合器。"""

    def merge(
        self,
        structured_candidates: list[dict],
        rag_person_evidence: list[dict] | None = None,
        formal_responsibility: list[dict] | None = None,
    ) -> list[MergedPersonCandidate]:
        """三路输入按 person_id 融合,保留全部证据。"""
        merged: dict[str, MergedPersonCandidate] = {}

        def _candidate(pid: str) -> MergedPersonCandidate:
            if pid not in merged:
                merged[pid] = MergedPersonCandidate(pid)
            return merged[pid]

        for raw in structured_candidates:
            e = PersonEvidence.model_validate(raw)
            _candidate(e.person_id).evidences.append(e)

        for raw in rag_person_evidence or []:
            e = PersonEvidence.model_validate(raw)
            _candidate(e.person_id).evidences.append(e)

        # 正式责任记录挂到责任人头上;责任人不在候选池时也要带入(§8.1:正式责任证据始终最高)
        for rec in formal_responsibility or []:
            pid = rec.get("owner_person_id") or ""
            if pid:
                _candidate(pid).responsibilities.append(rec)
            else:
                # 无具体责任人(部门级责任):作为独立责任证据保留在特殊桶
                _candidate("__department_responsibility__").responsibilities.append(rec)

        # 排序稳定性:有正式责任者在前,其次按证据数
        return sorted(
            merged.values(),
            key=lambda c: (not c.has_formal, -len(c.evidences), c.person_id),
        )
