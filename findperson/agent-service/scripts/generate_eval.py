"""生成评测集(V1.2 §16.1)。

从真实数据确定性生成评测问题与 gold 标注,分 dev/test 两套(test 冻结,调参只能用 dev):
- contact_lookup:          人名 → 查电话,gold=该人
- explicit_responsibility: 领域 → 谁负责,gold=该领域自填人员+正式责任人
- diagnostic:              领域+故障模板 → 找谁,gold=同上
- expert_finding:          领域 → 谁比较懂,gold=该领域自填人员+文章作者
- knowledge_qa:            责任/内容知识 → gold=document_id

输出: data/eval/eval_set.json
用法: .\\venv\\Scripts\\python.exe scripts\\generate_eval.py
"""
import asyncio
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402

from app.config import get_settings  # noqa: E402

random.seed(42)  # 确定性

SYMPTOM_TEMPLATES = [
    "{domain}相关的系统最近老是超时,该找谁?",
    "{domain}平台好像出故障了,响应特别慢,找谁处理?",
]


async def main() -> None:
    s = get_settings()
    conn = await asyncpg.connect(
        host=s.pghost, port=s.pgport, user=s.pguser, password=s.pgpassword, database=s.pgdatabase,
    )
    cases: list[dict] = []
    try:
        # ---- contact_lookup(抽 12 人)----
        people = await conn.fetch(
            "SELECT id, name FROM public.people WHERE status='active' ORDER BY id")
        for p in random.sample(list(people), 12):
            cases.append({
                "query": f"{p['name']}的电话是多少?",
                "intent": "find_person", "query_type": "contact_lookup",
                "gold": {"person_ids": [p["id"]], "concept_names": [], "document_ids": []},
            })

        # ---- 领域类问题(取覆盖人数前 10 的领域)----
        domains = await conn.fetch(
            "SELECT rt.text AS domain, c.canonical_name, c.concept_id,"
            "       array_agg(pt.person_id ORDER BY pt.person_id) AS persons"
            " FROM agent.raw_tags rt"
            " JOIN agent.tag_concept_map m ON m.tag_id = rt.tag_id AND m.review_status='auto_approved'"
            " JOIN agent.concepts c ON c.concept_id = m.concept_id"
            " JOIN agent.person_tags pt ON pt.tag_id = rt.tag_id AND pt.is_active"
            " GROUP BY rt.text, c.canonical_name, c.concept_id"
            " ORDER BY count(pt.person_id) DESC NULLS LAST, rt.text LIMIT 10")
        # 正式责任映射:domain → 责任文档 owner
        ras = await conn.fetch(
            "SELECT title, owner_person_id FROM public.responsibility_assignments WHERE status='active'")
        for d in domains:
            domain = d["domain"]
            persons = list(d["persons"])[:8]
            formal = [r["owner_person_id"] for r in ras
                      if domain in r["title"] and r["owner_person_id"]]
            gold_persons = sorted(set(persons) | set(formal))
            gold = {"person_ids": gold_persons, "concept_names": [d["canonical_name"]],
                    "document_ids": []}
            cases.append({
                "query": f"谁负责{domain}?",
                "intent": "find_person", "query_type": "explicit_responsibility",
                "gold": gold,
            })
            cases.append({
                "query": random.choice(SYMPTOM_TEMPLATES).format(domain=domain),
                "intent": "find_person", "query_type": "diagnostic",
                "gold": gold,
            })
            cases.append({
                "query": f"谁比较懂{domain}?",
                "intent": "find_person", "query_type": "expert_finding",
                "gold": gold,
            })

        # ---- knowledge_qa(责任知识 6 条 + 文章内容 4 条)----
        for r in ras[:6]:
            domain = r["title"].replace("相关事务", "")
            cases.append({
                "query": f"{domain}相关事务的处理时限和升级路径是什么?",
                "intent": "knowledge_qa", "query_type": None,
                "gold": {"person_ids": [], "concept_names": [], "document_ids": []},
            })
        contents = await conn.fetch("SELECT id, title FROM public.contents ORDER BY id LIMIT 4")
        for c in contents:
            cases.append({
                "query": f"{c['title']}的主要内容是什么?",
                "intent": "knowledge_qa", "query_type": None,
                "gold": {"person_ids": [], "concept_names": [],
                         "document_ids": [f"content-{c['id']}"]},
            })
    finally:
        await conn.close()

    # ---- dev/test 切分(按类型分层,test 冻结)----
    random.shuffle(cases)
    dev, test = [], []
    by_type: dict[str, list] = {}
    for c in cases:
        key = f"{c['intent']}/{c['query_type']}"
        by_type.setdefault(key, []).append(c)
    n = 0
    for group in by_type.values():
        half = len(group) // 2
        for i, case in enumerate(group):
            case["id"] = f"eval-{n:04d}"
            n += 1
            (dev if i < half else test).append(case)

    out = Path(__file__).resolve().parent.parent / "data" / "eval"
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "dev.json", "w", encoding="utf-8") as f:
        json.dump(dev, f, ensure_ascii=False, indent=1)
    with open(out / "test.json", "w", encoding="utf-8") as f:
        json.dump(test, f, ensure_ascii=False, indent=1)
    print(f"[eval] dev={len(dev)}, test={len(test)}, total={len(cases)}")
    from collections import Counter
    print("[eval] 分布:", dict(Counter(f"{c['intent']}/{c['query_type']}" for c in cases)))


if __name__ == "__main__":
    asyncio.run(main())
