"""新库结构迁移:数据库团队 schema → 我方 schema(数据翻译保留)。
在 shouwenzeren_newdb 上执行,幂等。输出 UTF-8 报告。
步骤:
 1. v2 版 agent 表挪到 public.v2bak_*(保数据)
 2. 重建 agent/rag schema,跑我方 DDL 01-06
 3. 补后加列:person_tags.approval / peer_reviews.status
 4. v2 数据翻译进我方表(raw_tags/concepts/tag_concept_map/person_tags)
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, r"C:\python\pycharm\shouwenzeren\agent-service")
import asyncpg

DDL_DIR = Path(r"C:\python\pycharm\shouwenzeren\_repo_push\agent-service\scripts\ddl")
DB = "shouwenzeren_newdb"
OUT = []


async def main():
    conn = await asyncpg.connect(host="localhost", port=5432, user="postgres",
                                 password=os.environ["PGPASSWORD"], database=DB)
    # 1. v2 表挪到 public.v2bak_*(幂等:以 public.v2bak_* 是否存在为准)
    for t in ("person_tags", "raw_tags", "concepts", "tag_concept_map"):
        await conn.execute(f"""
            DO $$ BEGIN
              IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                             WHERE table_schema='public' AND table_name='v2bak_{t}')
                 AND EXISTS (SELECT 1 FROM information_schema.tables
                             WHERE table_schema='agent' AND table_name='{t}') THEN
                ALTER TABLE agent.{t} SET SCHEMA public;
                EXECUTE 'ALTER TABLE public.{t} RENAME TO v2bak_{t}';
              END IF;
            END $$;""")
        OUT.append(f"v2bak_{t} 已就位")
    # 2. 重建 agent/rag schema;people 视图换成我方表设计(触发器同步,见 DDL 05)
    for s in ("agent", "rag"):
        await conn.execute(f"DROP SCHEMA IF EXISTS {s} CASCADE")
        await conn.execute(f"CREATE SCHEMA {s}")
        OUT.append(f"schema {s} 重建")
    await conn.execute("DROP VIEW IF EXISTS public.people CASCADE")
    OUT.append("public.people 视图已删(DDL 01 会建同名表)")
    # 3. 跑 DDL 01-03;04 建视图引用 approval,需先补列再跑 04-06
    for f in sorted(DDL_DIR.glob("*.sql")):
        if f.name >= "04":
            continue
        await conn.execute(f.read_text(encoding="utf-8"))
        OUT.append(f"DDL {f.name} 执行完成")
    # 3.5 后加列(历史欠账,已同步补进 DDL)
    await conn.execute("ALTER TABLE agent.person_tags ADD COLUMN IF NOT EXISTS approval TEXT NOT NULL DEFAULT 'approved'")
    await conn.execute("ALTER TABLE public.peer_reviews ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'approved'")
    OUT.append("approval/status 列已补")
    for f in sorted(DDL_DIR.glob("*.sql")):
        if f.name < "04":
            continue
        await conn.execute(f.read_text(encoding="utf-8"))
        OUT.append(f"DDL {f.name} 执行完成")
    # 3.1 people 表回填(触发器只对变更生效,存量用户手动触发一次)
    await conn.execute("UPDATE public.users SET id = id")
    n = await conn.fetchval("SELECT count(*) FROM public.people")
    OUT.append(f"people 表回填: {n} 人")
    # 4. 数据翻译
    r = await conn.execute("""
        INSERT INTO agent.raw_tags(tag_id, text, normalized_text)
        SELECT 'tag-v2-' || id, tag_text, normalized_text FROM public.v2bak_raw_tags
        ON CONFLICT (normalized_text) DO NOTHING""")
    OUT.append(f"raw_tags: {r}")
    r = await conn.execute("""
        INSERT INTO agent.concepts(concept_id, canonical_name, status)
        SELECT 'concept-v2-' || id, name, 'seed' FROM public.v2bak_concepts
        ON CONFLICT (concept_id) DO NOTHING""")
    OUT.append(f"concepts: {r}")
    r = await conn.execute("""
        INSERT INTO agent.tag_concept_map(map_id, tag_id, concept_id, mapping_type, confidence, generated_by)
        SELECT 'map-v2-' || m.id, 'tag-v2-' || m.tag_id, 'concept-v2-' || m.concept_id,
               COALESCE(m.map_source, 'exact_alias'), m.confidence, 'rule'
        FROM public.v2bak_tag_concept_map m
        ON CONFLICT (tag_id, concept_id) DO NOTHING""")
    OUT.append(f"tag_concept_map: {r}")
    r = await conn.execute("""
        INSERT INTO agent.person_tags(person_tag_id, person_id, tag_id, source, approval, is_active)
        SELECT 'pt-v2-' || id, person_id, 'tag-v2-' || tag_id,
               CASE WHEN tag_kind = 'self_tag' THEN 'self' ELSE 'peer_review' END,
               'approved', (status = 'active')
        FROM public.v2bak_person_tags
        ON CONFLICT (person_tag_id) DO NOTHING""")
    OUT.append(f"person_tags: {r}")
    # 汇总
    for t in ("raw_tags", "person_tags", "concepts", "tag_concept_map"):
        n = await conn.fetchval(f"SELECT count(*) FROM agent.{t}")
        OUT.append(f"agent.{t} = {n}")
    with open(r"C:\python\pycharm\shouwenzeren\_newdb\migrate_report.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))
    await conn.close()

asyncio.run(main())
