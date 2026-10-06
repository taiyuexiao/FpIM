"""从旧库 shouwenzeren 迁移业务数据到 shouwenzeren_v2,并生成 Mock 正式责任数据。

迁移内容:
- public.departments      ← 旧 department_paths(20 个部门,带层级路径)
- public.people           ← 旧 people(300 人,保留 p-XXXX id)
- public.contents         ← 旧 content(30 篇)+ content_tags
- agent.raw_tags/person_tags ← 旧 domains + person_domains(1012 条"负责领域",即 RawTag 来源)

生成内容:
- public.responsibility_assignments —— Mock 正式责任(每个部门取其人员高频负责领域,
  责任人取该部门 completeness 最高者,确定性生成,可重复执行)

用法: .\\venv\\Scripts\\python.exe scripts\\migrate_legacy.py
"""
import asyncio
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402


async def migrate() -> None:
    s = get_settings()
    old = await asyncpg.connect(
        host=s.pghost, port=s.pgport, user=s.pguser, password=s.pgpassword,
        database=s.legacy_pgdatabase,
    )
    new = await asyncpg.connect(
        host=s.pghost, port=s.pgport, user=s.pguser, password=s.pgpassword,
        database=s.pgdatabase,
    )
    try:
        # ---------------- departments ----------------
        paths = await old.fetch("SELECT department, level1, level2, level3 FROM department_paths ORDER BY department")
        dept_id: dict[str, int] = {}
        async with new.transaction():
            for row in paths:
                path = "/".join(x for x in (row["level1"], row["level2"], row["level3"]) if x)
                did = await new.fetchval(
                    "INSERT INTO public.departments(name, path) VALUES($1,$2) "
                    "ON CONFLICT (name) DO UPDATE SET path=EXCLUDED.path RETURNING id",
                    row["department"], path,
                )
                dept_id[row["department"]] = did
        print(f"[migrate] departments: {len(dept_id)}")

        # ---------------- people ----------------
        people = await old.fetch(
            "SELECT id, account, phone, name, department, role, role_type, contact,"
            "       self_portrait, completeness, status FROM people ORDER BY id"
        )
        async with new.transaction():
            for p in people:
                await new.execute(
                    "INSERT INTO public.people(id, account, phone, name, department, department_id,"
                    " role, role_type, contact, self_portrait, completeness, status)"
                    " VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)"
                    " ON CONFLICT (id) DO UPDATE SET"
                    " name=EXCLUDED.name, department=EXCLUDED.department,"
                    " department_id=EXCLUDED.department_id, role=EXCLUDED.role,"
                    " self_portrait=EXCLUDED.self_portrait, completeness=EXCLUDED.completeness",
                    p["id"], p["account"], p["phone"], p["name"], p["department"],
                    dept_id.get(p["department"]), p["role"], p["role_type"] or "user",
                    p["contact"], p["self_portrait"] or "", p["completeness"] or 0,
                    p["status"] or "active",
                )
        print(f"[migrate] people: {len(people)}")

        # ---------------- contents + tags ----------------
        contents = await old.fetch(
            "SELECT id, owner_id, type, title, summary, body, status FROM content ORDER BY id"
        )
        tags_rows = await old.fetch("SELECT content_id, tag FROM content_tags ORDER BY content_id")
        tags_map: dict[str, list[str]] = {}
        for t in tags_rows:
            tags_map.setdefault(t["content_id"], []).append(t["tag"])
        async with new.transaction():
            for c in contents:
                body = ((c["summary"] or "") + "\n\n" + (c["body"] or "")).strip()
                await new.execute(
                    "INSERT INTO public.contents(id, title, body, owner_id, content_type, tags, status)"
                    " VALUES($1,$2,$3,$4,$5,$6,$7)"
                    " ON CONFLICT (id) DO UPDATE SET title=EXCLUDED.title, body=EXCLUDED.body,"
                    " tags=EXCLUDED.tags",
                    c["id"], c["title"], body, c["owner_id"], c["type"] or "article",
                    tags_map.get(c["id"], []),
                    "published" if (c["status"] or "已发布") == "已发布" else "draft",
                )
        print(f"[migrate] contents: {len(contents)}")

        # ---------------- raw_tags + person_tags(负责领域 → RawTag,§7.1)----------------
        domains = await old.fetch("SELECT name FROM domains ORDER BY name")
        person_domains = await old.fetch(
            "SELECT person_id, domain_name FROM person_domains ORDER BY person_id, domain_name"
        )
        tag_id_of: dict[str, str] = {}
        async with new.transaction():
            for i, d in enumerate(domains, 1):
                tid = f"tag-{i:04d}"
                norm = " ".join(d["name"].split()).lower()
                await new.execute(
                    "INSERT INTO agent.raw_tags(tag_id, text, normalized_text) VALUES($1,$2,$3)"
                    " ON CONFLICT (normalized_text) DO NOTHING",
                    tid, d["name"], norm,
                )
                tag_id_of[d["name"]] = await new.fetchval(
                    "SELECT tag_id FROM agent.raw_tags WHERE normalized_text=$1", norm,
                )
            n_pt = 0
            for pd in person_domains:
                tid = tag_id_of.get(pd["domain_name"])
                if not tid:
                    continue
                ptid = f"pt-{pd['person_id']}-{tid}"
                await new.execute(
                    "INSERT INTO agent.person_tags(person_tag_id, person_id, tag_id, source, created_by)"
                    " VALUES($1,$2,$3,'self',$4) ON CONFLICT (person_tag_id) DO NOTHING",
                    ptid, pd["person_id"], tid, pd["person_id"],
                )
                n_pt += 1
        print(f"[migrate] raw_tags: {len(tag_id_of)}, person_tags: {n_pt}")

        # ---------------- Mock responsibility_assignments ----------------
        # 每个部门:取该部门人员覆盖人数前 3 的负责领域生成责任事项,
        # 责任人为该部门内覆盖该领域且 completeness 最高者。确定性、可重复。
        await new.execute("DELETE FROM public.responsibility_assignments WHERE id LIKE 'ra-mock-%'")
        domain_stats = await new.fetch(
            "SELECT p.department, p.department_id, rt.text AS domain, count(*) AS cnt"
            " FROM agent.person_tags pt"
            " JOIN agent.raw_tags rt ON rt.tag_id = pt.tag_id"
            " JOIN public.people p ON p.id = pt.person_id"
            " WHERE pt.is_active"
            " GROUP BY p.department, p.department_id, rt.text"
            " ORDER BY p.department, cnt DESC, rt.text"
        )
        picked: dict[str, int] = {}   # 每部门取前 3 个领域
        n_ra = 0
        async with new.transaction():
            for r in domain_stats:
                if picked.get(r["department"], 0) >= 3:
                    continue
                picked[r["department"]] = picked.get(r["department"], 0) + 1
                owner = await new.fetchrow(
                    "SELECT p.id, p.name, p.role FROM public.people p"
                    " JOIN agent.person_tags pt ON pt.person_id = p.id AND pt.is_active"
                    " JOIN agent.raw_tags rt ON rt.tag_id = pt.tag_id"
                    " WHERE p.department=$1 AND rt.text=$2"
                    " ORDER BY p.completeness DESC, p.id LIMIT 1",
                    r["department"], r["domain"],
                )
                if not owner:
                    continue
                n_ra += 1
                ra_id = f"ra-mock-{n_ra:04d}"
                await new.execute(
                    "INSERT INTO public.responsibility_assignments("
                    " id, title, description, intake_department_id, owner_department_id,"
                    " owner_person_id, owner_role, time_limit, transfer_condition,"
                    " escalation_path, status, version)"
                    " VALUES($1,$2,$3,$4,$4,$5,$6,$7,$8,$9,'active',1)",
                    ra_id,
                    f"{r['domain']}相关事务",
                    f"{r['department']}负责{r['domain']}相关工作的受理、处理与升级响应。",
                    r["department_id"], owner["id"], owner["role"],
                    "一般问题2个工作日内响应",
                    "涉及跨部门系统的问题转交对应责任部门",
                    f"{r['department']}负责人 → 分管领导",
                )
        print(f"[migrate] responsibility_assignments(mock): {n_ra}")
    finally:
        await old.close()
        await new.close()


if __name__ == "__main__":
    asyncio.run(migrate())
