"""全量 OKF 发布(V1.2 §19 阶段 3 验收)。

从 Mock 业务数据(shouwenzeren_v2 public schema)稳定生成可发布、可版本化、可追溯的 OKF:
- 24 份 ResponsibilityItem(§10.5 责任发布链)
- 300 份 PersonProfile(§10.4 白名单)
- 30 份 Content
- 20 份 Department

幂等:内容未变的文档自动跳过(Publisher 增量判断)。
用法: .\\venv\\Scripts\\python.exe scripts\\publish_okf.py
"""
import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.okf.builders import (  # noqa: E402
    build_content_doc, build_department_doc, build_faq_doc, build_person_profile_doc,
    build_responsibility_doc,
)
from app.okf.publisher import OkfPublisher  # noqa: E402
from app.okf.repository import OkfRepository  # noqa: E402


async def main() -> None:
    s = get_settings()
    conn = await asyncpg.connect(
        host=s.pghost, port=s.pgport, user=s.pguser, password=s.pgpassword, database=s.pgdatabase,
    )
    repo = OkfRepository()
    await repo.ensure_git_initialized()
    pub = OkfPublisher(repo)
    stats: Counter = Counter()
    failures: list = []
    current_ids: set[str] = set()   # 本次由当前库发布出来的文档 id(用于清理孤儿文档)

    async def _publish(doc) -> None:
        result = await pub.publish(doc)
        stats["published" if result.published else "failed"] += 1
        if result.published and result.changed:
            stats["changed"] += 1
        if result.published:
            current_ids.add(doc.metadata.id)
        else:
            failures.append((doc.metadata.id, result.errors))

    try:
        # ---- 责任发布链(§10.5)----
        ras = await conn.fetch(
            "SELECT ra.*, d1.name AS intake_name, d2.name AS owner_name_dept, p.name AS owner_person_name"
            " FROM public.responsibility_assignments ra"
            " LEFT JOIN public.departments d1 ON d1.id = ra.intake_department_id"
            " LEFT JOIN public.departments d2 ON d2.id = ra.owner_department_id"
            " LEFT JOIN public.people p ON p.id = ra.owner_person_id"
            " WHERE ra.status='active'"
        )
        for ra in ras:
            await _publish(build_responsibility_doc(
                dict(ra), intake_department=ra["intake_name"] or "",
                owner_department=ra["owner_name_dept"] or "",
                owner_name=ra["owner_person_name"] or ""))
        print(f"[publish] responsibilities: {len(ras)}")

        # ---- PersonProfile(§10.4)----
        people = await conn.fetch("SELECT * FROM public.people WHERE status='active' ORDER BY id")
        # 同事评价聚合正文(§10.4 白名单允许,低权重)
        review_rows = await conn.fetch(
            "SELECT person_id, tag_name FROM public.peer_reviews")
        reviews_by_person: dict = {}
        for r in review_rows:
            reviews_by_person.setdefault(r["person_id"], set()).add(r["tag_name"])
        for p in people:
            tags = reviews_by_person.get(p["id"], set())
            await _publish(build_person_profile_doc(
                dict(p), reviews_text="、".join(sorted(tags))))
        print(f"[publish] people: {len(people)}")

        # ---- Contents(仅已发布,与增量链路"审核通过才可检索"语义一致) ----
        contents = await conn.fetch(
            "SELECT c.*, p.name AS owner_name, p.department_id AS owner_dept_id FROM public.contents c"
            " LEFT JOIN public.people p ON p.id = c.owner_id"
            " WHERE c.status='published' AND COALESCE(c.is_deleted, false)=false ORDER BY c.id"
        )
        for c in contents:
            await _publish(build_content_doc(dict(c), owner_name=c["owner_name"] or "",
                                             owner_department_id=c["owner_dept_id"]))
        print(f"[publish] contents: {len(contents)}")

        # ---- FAQs(用户提问沉淀;仅已发布,模板必备字段 question/answer/owner/tags/source) ----
        faqs = await conn.fetch(
            "SELECT f.*, u.name AS owner_name, u.department_id AS owner_dept_id"
            " FROM public.faqs f LEFT JOIN public.user2 u ON u.id = f.owner_person_id"
            " WHERE f.status='published' ORDER BY f.id"
        )
        for f in faqs:
            await _publish(build_faq_doc(dict(f), owner_name=f["owner_name"] or "",
                                         owner_department_id=f["owner_dept_id"]))
        print(f"[publish] faqs: {len(faqs)}")

        # ---- Departments ----
        depts = await conn.fetch(
            "SELECT d.*, (SELECT count(*) FROM public.people p WHERE p.department_id = d.id)"
            " AS member_count FROM public.departments d ORDER BY d.id"
        )
        for d in depts:
            await _publish(build_department_doc(dict(d), member_count=d["member_count"]))
        print(f"[publish] departments: {len(depts)}")

        # ---- 清理孤儿文档:OKF 是业务表的投影,库里已不存在的旧文档必须删除 ----
        # (否则检索会捞出"幽灵"人员/内容——旧 ID 指向的人根本不在 people 表里)
        removed = 0
        for doc_type in ("responsibilities", "people", "departments", "contents", "faqs"):
            for path in (repo.root / doc_type).glob("*.md"):
                if path.stem not in current_ids:
                    path.unlink()
                    removed += 1
        print(f"[publish] 清理孤儿文档: {removed}")
    finally:
        await conn.close()

    print(f"[publish] 结果: published={stats['published']} (changed={stats['changed']}),"
          f" failed={stats['failed']}")
    for doc_id, errors in failures[:10]:
        print(f"  [FAIL] {doc_id}: {errors}")


if __name__ == "__main__":
    asyncio.run(main())
