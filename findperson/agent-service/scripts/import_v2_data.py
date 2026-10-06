"""V2 Excel 数据导入 PostgreSQL。

步骤:
1. 清空现有业务数据(保留 schema)
2. 导入 departments / concepts / aliases / relations
3. 导入 people / contents / responsibility_assignments
4. 导入 raw_tags / person_tags / tag_concept_map
5. 重建 concept embeddings

用法: .\\venv\\Scripts\\python.exe scripts\\import_v2_data.py
"""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg

from app.config import get_settings

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "v2_import"


def load_json(name: str) -> list[dict]:
    with open(DATA_DIR / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


def norm_id(pid: str) -> str:
    """P0001 -> p-0001"""
    if pid.startswith("P") and len(pid) == 5:
        return f"p-{pid[1:]}"
    return pid


def norm_content_id(aid: str) -> str:
    """A00001 -> content-A00001"""
    if aid.startswith("A") and len(aid) == 6:
        return f"content-{aid[1:]}"
    return aid


async def main() -> None:
    s = get_settings()
    conn = await asyncpg.connect(
        host=s.pghost, port=s.pgport, user=s.pguser,
        password=s.pgpassword, database=s.pgdatabase,
    )

    try:
        # ========== 1. 清空现有数据 ==========
        print("[1/6] 清空现有数据...")
        await conn.execute("DELETE FROM agent.person_tags")
        await conn.execute("DELETE FROM agent.tag_concept_map")
        await conn.execute("DELETE FROM agent.raw_tags")
        await conn.execute("DELETE FROM agent.concept_relations")
        await conn.execute("DELETE FROM agent.concept_aliases")
        await conn.execute("DELETE FROM agent.concepts")
        await conn.execute("DELETE FROM agent.query_concept_logs")
        await conn.execute("DELETE FROM rag.rag_chunks")
        await conn.execute("DELETE FROM rag.rag_documents")
        await conn.execute("DELETE FROM rag.rag_index_jobs")
        await conn.execute("UPDATE rag.rag_index_pointer SET active_version=0 WHERE id=1")
        await conn.execute("DELETE FROM public.responsibility_assignments")
        await conn.execute("DELETE FROM public.peer_reviews")
        await conn.execute("DELETE FROM public.contents")
        await conn.execute("DELETE FROM public.people")
        await conn.execute("DELETE FROM public.departments")
        print("  清空完成")

        # ========== 2. 导入 Departments ==========
        print("[2/6] 导入 departments...")
        people_data = load_json("people")
        dept_names = sorted({p["department"] for p in people_data if p["department"]})
        dept_map: dict[str, int] = {}
        for i, name in enumerate(dept_names, 1):
            await conn.execute(
                "INSERT INTO public.departments(id, name, path) VALUES($1, $2, $3)",
                i, name, name,
            )
            dept_map[name] = i
        print(f"  {len(dept_map)} departments")

        # ========== 3. 导入 Concepts + Aliases + Relations ==========
        print("[3/6] 导入 concepts / aliases / relations...")
        concepts = load_json("concepts")
        for c in concepts:
            await conn.execute(
                "INSERT INTO agent.concepts(concept_id, canonical_name, concept_type, description, status)"
                " VALUES($1, $2, $3, $4, 'active')",
                c["concept_id"], c["name"], "domain",
                f"parent={c.get('parent') or ''}; keywords={c.get('keywords') or ''}",
            )
            # aliases
            aliases = json.loads(c["aliases"]) if isinstance(c["aliases"], str) else (c["aliases"] or [])
            for j, alias in enumerate(aliases):
                await conn.execute(
                    "INSERT INTO agent.concept_aliases(alias_id, concept_id, alias)"
                    " VALUES($1, $2, $3)",
                    f"alias-{c['concept_id']}-{j}", c["concept_id"], alias.lower().strip(),
                )
        print(f"  {len(concepts)} concepts")

        relations = load_json("relations")
        for r in relations:
            await conn.execute(
                "INSERT INTO agent.concept_relations(relation_id, src_concept_id, dst_concept_id, relation_type)"
                " VALUES($1, $2, $3, $4) ON CONFLICT DO NOTHING",
                f"rel-{r['source_concept_id']}-{r['relation_type']}-{r['target_concept_id']}",
                r["source_concept_id"], r["target_concept_id"], r["relation_type"],
            )
        print(f"  {len(relations)} relations")

        # ========== 4. 导入 People ==========
        print("[4/6] 导入 people...")
        for p in people_data:
            pid = norm_id(p["person_id"])
            dept_id = dept_map.get(p["department"])
            await conn.execute(
                "INSERT INTO public.people(id, account, phone, name, department, department_id,"
                " role, role_type, contact, self_portrait, completeness, status)"
                " VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)",
                pid, p["person_id"], str(p.get("phone") or ""), p["name"],
                p["department"], dept_id, p.get("job_title") or "", "user",
                str(p.get("phone") or ""), p.get("self_intro") or "", 80, "active",
            )
        print(f"  {len(people_data)} people")

        # ========== 5. 导入 Tags (raw_tags / person_tags / tag_concept_map) ==========
        print("[5/6] 导入 tags...")
        tag_counter = 0
        pt_counter = 0
        tcm_counter = 0
        concept_name_to_id = {c["name"]: c["concept_id"] for c in concepts}

        for p in people_data:
            pid = norm_id(p["person_id"])
            primary_cid = p["primary_concept_id"]
            primary_cname = p["primary_concept_name"]
            duty = p.get("duty_name") or ""

            # self_tags
            self_tags = json.loads(p["self_tags"]) if isinstance(p["self_tags"], str) else (p["self_tags"] or [])
            for tag_text in self_tags:
                tag_id = f"tag-{tag_counter:06d}"
                tag_counter += 1
                normalized = " ".join(tag_text.split()).lower()
                await conn.execute(
                    "INSERT INTO agent.raw_tags(tag_id, text, normalized_text)"
                    " VALUES($1, $2, $3) ON CONFLICT (normalized_text) DO NOTHING",
                    tag_id, tag_text, normalized,
                )
                # 获取实际 tag_id(可能已存在)
                actual_tag_id = await conn.fetchval(
                    "SELECT tag_id FROM agent.raw_tags WHERE normalized_text=$1", normalized
                )
                pt_id = f"pt-{pt_counter:06d}"
                pt_counter += 1
                await conn.execute(
                    "INSERT INTO agent.person_tags(person_tag_id, person_id, tag_id, source, created_by, is_active)"
                    " VALUES($1, $2, $3, 'self', $4, TRUE)",
                    pt_id, pid, actual_tag_id, pid,
                )
                # 建立 tag_concept_map:如果标签包含概念名或职责名,映射到 primary concept
                if primary_cname in tag_text or (duty and duty in tag_text):
                    map_id = f"map-{tcm_counter:06d}"
                    tcm_counter += 1
                    await conn.execute(
                        "INSERT INTO agent.tag_concept_map(map_id, tag_id, concept_id, mapping_type, confidence, generated_by, review_status)"
                        " VALUES($1, $2, $3, 'exact_alias', 1.0, 'rule', 'auto_approved') ON CONFLICT DO NOTHING",
                        map_id, actual_tag_id, primary_cid,
                    )

            # peer_tags
            peer_tags = json.loads(p["peer_tags"]) if isinstance(p["peer_tags"], str) else (p["peer_tags"] or [])
            for tag_text in peer_tags:
                normalized = " ".join(tag_text.split()).lower()
                await conn.execute(
                    "INSERT INTO agent.raw_tags(tag_id, text, normalized_text)"
                    " VALUES($1, $2, $3) ON CONFLICT (normalized_text) DO NOTHING",
                    f"tag-{tag_counter:06d}", tag_text, normalized,
                )
                tag_counter += 1
                actual_tag_id = await conn.fetchval(
                    "SELECT tag_id FROM agent.raw_tags WHERE normalized_text=$1", normalized
                )
                pt_id = f"pt-{pt_counter:06d}"
                pt_counter += 1
                await conn.execute(
                    "INSERT INTO agent.person_tags(person_tag_id, person_id, tag_id, source, created_by, is_active)"
                    " VALUES($1, $2, $3, 'peer_review', 'system', TRUE)",
                    pt_id, pid, actual_tag_id,
                )
                if primary_cname in tag_text:
                    map_id = f"map-{tcm_counter:06d}"
                    tcm_counter += 1
                    await conn.execute(
                        "INSERT INTO agent.tag_concept_map(map_id, tag_id, concept_id, mapping_type, confidence, generated_by, review_status)"
                        " VALUES($1, $2, $3, 'near_alias', 0.9, 'rule', 'auto_approved') ON CONFLICT DO NOTHING",
                        map_id, actual_tag_id, primary_cid,
                    )
        print(f"  {tag_counter} raw_tags, {pt_counter} person_tags, {tcm_counter} tag_concept_map")

        # ========== 6. 导入 Contents + ResponsibilityAssignments ==========
        print("[6/6] 导入 contents / responsibility_assignments...")
        articles = load_json("articles")
        for a in articles:
            cid = norm_content_id(a["article_id"])
            author_pid = norm_id(a["author_id"])
            tags = json.loads(a["hidden_tags"]) if isinstance(a["hidden_tags"], str) else (a["hidden_tags"] or [])
            tags = [str(t) for t in tags]
            body = a.get("body")
            if not isinstance(body, str):
                body = str(body) if body is not None else ""
            title = a.get("title")
            if not isinstance(title, str):
                title = str(title) if title is not None else ""
            await conn.execute(
                "INSERT INTO public.contents(id, title, body, owner_id, content_type, tags, status)"
                " VALUES($1, $2, $3, $4, 'article', $5, 'published')",
                cid, title, body, author_pid, tags,
            )
        print(f"  {len(articles)} contents")

        ras = load_json("responsibilityassignments")
        for ra in ras:
            pid = norm_id(ra["person_id"])
            dept_id = dept_map.get(ra.get("department") or "")
            await conn.execute(
                "INSERT INTO public.responsibility_assignments"
                "(id, title, description, intake_department_id, owner_department_id,"
                " owner_person_id, owner_role, time_limit, transfer_condition,"
                " escalation_path, status, version)"
                " VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'active',1)",
                ra["assignment_id"], ra["concept_name"] or ra.get("service_id") or "",
                ra.get("scope") or "", dept_id, dept_id,
                pid, ra.get("duty_name") or "", "24小时", "职责不符", "部门负责人",
            )
        print(f"  {len(ras)} responsibility_assignments")

        # 统计
        print("\n=== 导入完成 ===")
        for table in ["public.departments", "public.people", "public.contents",
                      "public.responsibility_assignments", "agent.concepts",
                      "agent.raw_tags", "agent.person_tags", "agent.tag_concept_map"]:
            count = await conn.fetchval(f"SELECT count(*) FROM {table}")
            print(f"  {table}: {count}")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
