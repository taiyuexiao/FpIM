"""Formal Responsibility Retriever 的 Mock 实现(V1.2 §9.4 / §18)。

正式路径应该是 Agent → Knowledge MCP → get_responsibility → Published OKF(模块 21/25/26
建成后替换)。在 OKF/MCP 建成前,按 §18 的规定使用「显式标记的 Mock/Degraded Adapter」
直读业务表,所有产出 degraded=True,真实联调阶段(模块 30)移除。

注意:责任业务表(public.responsibility_assignments)是唯一事实源;此 Mock 只读、
不修改任何事实。
"""
from __future__ import annotations

from app.contracts.mcp import ResponsibilityRecord
from app.core import db


class MockResponsibilityRetriever:
    """[Mock/Degraded Adapter] 直读业务责任表。模块 26 将替换为 MCP get_responsibility。"""

    degraded = True  # 显式标记(§18:临时直连必须显式标记 Mock/Degraded)

    async def get_responsibility(
        self, concept_names: list[str], *, limit: int = 5,
    ) -> list[ResponsibilityRecord]:
        """按概念名模糊匹配责任事项标题/描述。"""
        if not concept_names:
            return []
        patterns = [f"%{n}%" for n in concept_names]
        rows = await db.fetch(
            "SELECT ra.id, ra.title, ra.owner_role, ra.time_limit, ra.transfer_condition,"
            "       ra.escalation_path, ra.version, ra.owner_person_id,"
            "       d1.name AS intake_department, d2.name AS owner_department"
            " FROM public.responsibility_assignments ra"
            " LEFT JOIN public.departments d1 ON d1.id = ra.intake_department_id"
            " LEFT JOIN public.departments d2 ON d2.id = ra.owner_department_id"
            " WHERE ra.status='active'"
            "   AND (ra.title ILIKE ANY($1) OR ra.description ILIKE ANY($1))"
            " LIMIT $2",
            patterns, limit,
        )
        return [
            ResponsibilityRecord(
                responsibility_id=r["id"], title=r["title"],
                intake_department=r["intake_department"] or "",
                owner_department=r["owner_department"] or "",
                owner_person_id=r["owner_person_id"] or "",
                owner_role=r["owner_role"], time_limit=r["time_limit"],
                transfer_condition=r["transfer_condition"],
                escalation_path=r["escalation_path"],
                source_uri=f"public.responsibility_assignments/{r['id']}",
                version=r["version"],
            )
            for r in rows
        ]
