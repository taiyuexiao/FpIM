"""外部评测数据导入:首问责任平台模拟数据评测集 → shouwenzeren_ext 库。

映射:
- synthetic_people_200.jsonl   → public.people + departments + agent.raw_tags/person_tags
- synthetic_articles.jsonl     → public.contents
- concepts_and_relations.json  → agent.concepts/active + aliases + narrower_than 关系
- tag→concept 映射             → 按「别名精确/名称包含/主概念兜底」确定性规则建 tag_concept_map
                                 (相当于人工审核后的存量映射,与查询侧评测解耦)

用法:
  .\\venv\\Scripts\\python.exe scripts\\ext_eval\\import_ext.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import asyncpg  # noqa: E402

from app.config import get_settings  # noqa: E402

DATA_DIR = Path(r"C:\Users\12115\Downloads\首问责任平台模拟数据评测与技术方案")
EXT_DB = "shouwenzeren_ext"


def _norm(text: str) -> str:
    return " ".join(text.split()).lower()


async def create_db(s) -> None:
    admin = await asyncpg.connect(host=s.pghost, port=s.pgport, user=s.pguser,
                                  password=s.pgpassword, database="postgres")
    try:
        exists = await admin.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", EXT_DB)
        if not exists:
            await admin.execute(f'CREATE DATABASE "{EXT_DB}"')
            print(f"[ext] 创建数据库 {EXT_DB}")
    finally:
        await admin.close()
    conn = await asyncpg.connect(host=s.pghost, port=s.pgport, user=s.pguser,
                                 password=s.pgpassword, database=EXT_DB)
    try:
        for ext in ("vector", "pg_trgm"):
            await conn.execute(f"CREATE EXTENSION IF NOT EXISTS {ext}")
        for schema in ("agent", "rag"):
            await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        ddl_dir = Path(__file__).resolve().parent.parent / "ddl"
        for name in ("01_public.sql", "02_agent.sql", "03_rag.sql", "04_agent_views.sql"):
            await conn.execute((ddl_dir / name).read_text(encoding="utf-8"))
        print("[ext] DDL 完成")
    finally:
        await conn.close()


async def main() -> None:
    s = get_settings()
    await create_db(s)
    conn = await asyncpg.connect(host=s.pghost, port=s.pgport, user=s.pguser,
                                 password=s.pgpassword, database=EXT_DB)
    try:
        people = [json.loads(l) for l in open(DATA_DIR / "synthetic_people_200.jsonl", encoding="utf-8")]
        articles = [json.loads(l) for l in open(DATA_DIR / "synthetic_articles.jsonl", encoding="utf-8")]
        concepts_doc = json.load(open(DATA_DIR / "concepts_and_relations.json", encoding="utf-8"))
        concepts = concepts_doc["concepts"]

        # ---------- departments ----------
        dept_id: dict[str, int] = {}
        async with conn.transaction():
            for name in sorted({p["department"] for p in people}):
                dept_id[name] = await conn.fetchval(
                    "INSERT INTO public.departments(name, path) VALUES($1,$1)"
                    " ON CONFLICT (name) DO UPDATE SET name=EXCLUDED.name RETURNING id", name)
        print(f"[ext] departments: {len(dept_id)}")

        # ---------- people ----------
        async with conn.transaction():
            for p in people:
                await conn.execute(
                    "INSERT INTO public.people(id, account, phone, name, department, department_id,"
                    " role, role_type, contact, self_portrait, completeness, status)"
                    " VALUES($1,$2,$3,$4,$5,$6,$7,'user',$8,$9,90,'active')"
                    " ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name",
                    p["person_id"], p["person_id"].lower(), p["phone"], p["name"],
                    p["department"], dept_id[p["department"]],
                    f"{p['job_title']}/{p['duty_name']}", p["phone"], p["self_intro"])
        print(f"[ext] people: {len(people)}")

        # ---------- concepts(含 parent 概念) ----------
        async with conn.transaction():
            parents = {c["parent"] for c in concepts if c.get("parent")}
            for pname in parents:
                pid = f"concept-parent-{_norm(pname)}"
                await conn.execute(
                    "INSERT INTO agent.concepts(concept_id, canonical_name, concept_type,"
                    " status, description) VALUES($1,$2,'domain','active','父概念')"
                    " ON CONFLICT (concept_id) DO NOTHING", pid, pname)
            for c in concepts:
                await conn.execute(
                    "INSERT INTO agent.concepts(concept_id, canonical_name, concept_type,"
                    " status, description) VALUES($1,$2,'domain','active',$3)"
                    " ON CONFLICT (concept_id) DO NOTHING",
                    c["id"], c["name"],
                    f"关键词:{'、'.join(c.get('keywords', []))}")
            for c in concepts:
                if c.get("parent"):
                    await conn.execute(
                        "INSERT INTO agent.concept_relations(relation_id, src_concept_id,"
                        " dst_concept_id, relation_type) VALUES($1,$2,$3,'narrower_than')"
                        " ON CONFLICT DO NOTHING",
                        f"rel-{c['id']}", c["id"], f"concept-parent-{_norm(c['parent'])}")
            n_alias = 0
            for c in concepts:
                for alias in c.get("aliases", []):
                    await conn.execute(
                        "INSERT INTO agent.concept_aliases(alias_id, concept_id, alias)"
                        " VALUES($1,$2,$3) ON CONFLICT DO NOTHING",
                        f"alias-{c['id']}-{_norm(alias)[:40]}", c["id"], _norm(alias))
                    n_alias += 1
        print(f"[ext] concepts: {len(concepts)} (+{len(parents)} parents), aliases: {n_alias}")

        # ---------- raw_tags + person_tags + tag_concept_map ----------
        alias_to_cid: dict[str, str] = {}
        for c in concepts:
            alias_to_cid[_norm(c["name"])] = c["id"]
            for a in c.get("aliases", []):
                alias_to_cid[_norm(a)] = c["id"]

        def map_tag(tag_text: str, primary_cid: str) -> tuple[str, float, str]:
            """tag → concept 确定性映射。返回 (concept_id, confidence, mapping_type)。"""
            norm = _norm(tag_text)
            if norm in alias_to_cid:
                return alias_to_cid[norm], 1.0, "exact_alias"
            for anorm, cid in alias_to_cid.items():
                if anorm and (anorm in norm or norm in anorm):
                    return cid, 0.9, "near_alias"
            return primary_cid, 0.75, "near_alias"  # 主概念兜底

        all_tags: dict[str, str] = {}
        for p in people:
            for t in p.get("self_tags", []) + p.get("peer_tags", []):
                all_tags.setdefault(_norm(t), t)
        tag_id_of: dict[str, str] = {}
        async with conn.transaction():
            for i, (norm, text) in enumerate(sorted(all_tags.items()), 1):
                tid = f"tag-ext-{i:05d}"
                await conn.execute(
                    "INSERT INTO agent.raw_tags(tag_id, text, normalized_text)"
                    " VALUES($1,$2,$3) ON CONFLICT (normalized_text) DO NOTHING", tid, text, norm)
                tag_id_of[norm] = await conn.fetchval(
                    "SELECT tag_id FROM agent.raw_tags WHERE normalized_text=$1", norm)
        print(f"[ext] raw_tags: {len(tag_id_of)}")

        n_pt = n_map = 0
        async with conn.transaction():
            for p in people:
                for t in p.get("self_tags", []):
                    tid = tag_id_of[_norm(t)]
                    await conn.execute(
                        "INSERT INTO agent.person_tags(person_tag_id, person_id, tag_id,"
                        " source, created_by) VALUES($1,$2,$3,'self',$2)"
                        " ON CONFLICT (person_tag_id) DO NOTHING",
                        f"pt-{p['person_id']}-{tid}", p["person_id"], tid)
                    n_pt += 1
                    cid, conf, mtype = map_tag(t, p["primary_concept_id"])
                    res = await conn.execute(
                        "INSERT INTO agent.tag_concept_map(map_id, tag_id, concept_id,"
                        " mapping_type, confidence, generated_by, review_status, reason)"
                        " VALUES($1,$2,$3,$4,$5,'rule','auto_approved','外部评测集导入映射')"
                        " ON CONFLICT (tag_id, concept_id) DO NOTHING",
                        f"map-ext-{tid}-{cid[-12:]}", tid, cid, mtype, conf)
                    if res.endswith("1"):
                        n_map += 1
                for t in p.get("peer_tags", []):
                    tid = tag_id_of[_norm(t)]
                    await conn.execute(
                        "INSERT INTO agent.person_tags(person_tag_id, person_id, tag_id,"
                        " source, created_by) VALUES($1,$2,$3,'peer_review',$2)"
                        " ON CONFLICT (person_tag_id) DO NOTHING",
                        f"pt-pr-{p['person_id']}-{tid}", p["person_id"], tid)
                    n_pt += 1
                    cid, conf, mtype = map_tag(t, p["primary_concept_id"])
                    await conn.execute(
                        "INSERT INTO agent.tag_concept_map(map_id, tag_id, concept_id,"
                        " mapping_type, confidence, generated_by, review_status, reason)"
                        " VALUES($1,$2,$3,$4,$5,'rule','auto_approved','外部评测集导入映射')"
                        " ON CONFLICT (tag_id, concept_id) DO NOTHING",
                        f"map-ext-{tid}-{cid[-12:]}", tid, cid, mtype, conf)
        print(f"[ext] person_tags: {n_pt}, tag_concept_map新增: {n_map}")

        # ---------- contents(文章) ----------
        async with conn.transaction():
            for a in articles:
                await conn.execute(
                    "INSERT INTO public.contents(id, title, body, owner_id, content_type,"
                    " tags, status) VALUES($1,$2,$3,$4,'article',$5,'published')"
                    " ON CONFLICT (id) DO UPDATE SET body=EXCLUDED.body",
                    a["article_id"], a["title"], a["body"], a["author_id"],
                    a.get("hidden_tags", []))
        print(f"[ext] contents: {len(articles)}")
    finally:
        await conn.close()
    print("[ext] 导入完成")


if __name__ == "__main__":
    asyncio.run(main())
