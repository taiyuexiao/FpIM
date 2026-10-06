"""Directory Search(V1.2 §9.1)。

contact_lookup 专用:查人员基础表(姓名/部门/联系方式),不经过 ConceptLinker 和 RAG。
"""
from __future__ import annotations

from app.contracts.evidence import EvidenceType, PersonEvidence
from app.core import db


class DirectorySearch:
    """通讯录检索。"""

    async def search(
        self,
        *,
        names: list[str] | None = None,
        departments: list[str] | None = None,
        limit: int = 5,
    ) -> list[PersonEvidence]:
        """按姓名/部门查人员,返回 directory_match 证据(detail 携带联系信息)。"""
        conditions, args = ["status = 'active'"], []
        if names:
            args.append(names)
            conditions.append(f"name = ANY(${len(args)})")
        if departments:
            args.append(departments)
            conditions.append(f"department = ANY(${len(args)})")
        args.append(limit)
        rows = await db.fetch(
            f"SELECT id, name, department, role, contact, phone"
            f" FROM public.people WHERE {' AND '.join(conditions)}"
            f" ORDER BY completeness DESC LIMIT ${len(args)}",
            *args,
        )
        return [
            PersonEvidence(
                person_id=r["id"],
                relation_type="directory_match",
                evidence_type=EvidenceType.DIRECTORY_MATCH,
                source_type="directory",
                source_id=r["id"],
                confidence=1.0,
                detail={
                    "name": r["name"], "department": r["department"],
                    "role": r["role"], "contact": r["contact"] or r["phone"] or "",
                },
            )
            for r in rows
        ]
