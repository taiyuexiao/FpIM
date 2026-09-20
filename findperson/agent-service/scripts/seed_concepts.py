"""Seed Concept 冷启动(V1.2 §7.2 / §19 阶段 1)。

从企业已有真实资产抽取第一批 Concept(不由 LLM 凭空生成):
1. agent.raw_tags(61 个"负责领域"表达)→ domain 类 Seed Concept
2. public.contents.tags(文章主题)→ 按命名启发式归类 platform/system/domain
3. public.responsibility_assignments(正式责任事项的领域)→ domain 类(去重)

随后执行第一级自动映射(Canonical Name Exact,§7.3):
raw_tag 规范化文本 == concept 标准名规范化 → exact_alias,confidence=1.0,rule 自动生效。

幂等可重跑。
用法: .\\venv\\Scripts\\python.exe scripts\\seed_concepts.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402

from app.config import get_settings  # noqa: E402


def _norm(text: str) -> str:
    return " ".join(text.split()).lower()


def _guess_type(name: str) -> str:
    """按命名启发式推断 concept_type。"""
    if "平台" in name:
        return "platform"
    if "系统" in name:
        return "system"
    if any(k in name for k in ("开发", "测试", "运维", "治理", "分析", "计量", "管理", "建模")):
        return "capability"
    return "domain"


async def main() -> None:
    s = get_settings()
    conn = await asyncpg.connect(
        host=s.pghost, port=s.pgport, user=s.pguser, password=s.pgpassword, database=s.pgdatabase,
    )
    try:
        # ---------- 1. 汇集候选种子 ----------
        seeds: dict[str, dict] = {}  # norm_name → {name, type, source}

        raw_tags = await conn.fetch("SELECT text FROM agent.raw_tags ORDER BY tag_id")
        for r in raw_tags:
            name = r["text"].strip()
            seeds.setdefault(_norm(name), {"name": name, "type": _guess_type(name), "source": "raw_tags"})

        content_tags = await conn.fetch("SELECT DISTINCT unnest(tags) AS tag FROM public.contents")
        for r in content_tags:
            name = (r["tag"] or "").strip()
            if name and _norm(name) not in seeds:
                seeds[_norm(name)] = {"name": name, "type": _guess_type(name), "source": "contents"}

        ras = await conn.fetch("SELECT title FROM public.responsibility_assignments WHERE status='active'")
        for r in ras:
            name = r["title"].replace("相关事务", "").strip()
            if name and _norm(name) not in seeds:
                seeds[_norm(name)] = {"name": name, "type": "domain", "source": "responsibility"}

        print(f"[seed] 候选种子概念: {len(seeds)} (来源: raw_tags/contents/responsibility)")

        # ---------- 2. 写入 concepts(status=seed) ----------
        n_new = 0
        async with conn.transaction():
            for i, item in enumerate(seeds.values(), 1):
                cid = f"concept-seed-{i:04d}"
                exists = await conn.fetchval(
                    "SELECT concept_id FROM agent.concepts WHERE canonical_name=$1 AND status IN ('seed','active')",
                    item["name"],
                )
                if exists:
                    continue
                await conn.execute(
                    "INSERT INTO agent.concepts(concept_id, canonical_name, concept_type, description, status)"
                    " VALUES($1,$2,$3,$4,'seed')",
                    cid, item["name"], item["type"],
                    f"Seed Concept,来源: {item['source']}",
                )
                n_new += 1
        print(f"[seed] 新增 Seed Concept: {n_new}")

        # ---------- 3. 第一级自动映射:Canonical Name Exact(§7.3) ----------
        pairs = await conn.fetch(
            "SELECT rt.tag_id, c.concept_id"
            " FROM agent.raw_tags rt"
            " JOIN agent.concepts c ON lower(c.canonical_name) = rt.normalized_text"
            " WHERE c.status IN ('seed','active')"
        )
        n_map = 0
        async with conn.transaction():
            for i, p in enumerate(pairs, 1):
                mid = f"map-seed-{i:04d}"
                res = await conn.execute(
                    "INSERT INTO agent.tag_concept_map(map_id, tag_id, concept_id, mapping_type,"
                    " confidence, generated_by, review_status, reason)"
                    " VALUES($1,$2,$3,'exact_alias',1.0,'rule','auto_approved','标准名精确匹配')"
                    " ON CONFLICT (tag_id, concept_id) DO NOTHING",
                    mid, p["tag_id"], p["concept_id"],
                )
                if res.endswith("1"):
                    n_map += 1
        print(f"[seed] 第一级自动映射(exact_alias): {n_map}")

        # ---------- 4. 汇总 ----------
        for label, sql in (
            ("concepts(seed/active)", "SELECT count(*) FROM agent.concepts WHERE status IN ('seed','active')"),
            ("tag_concept_map", "SELECT count(*) FROM agent.tag_concept_map"),
        ):
            print(f"[seed] {label}: {await conn.fetchval(sql)}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
