"""存量碎片概念归并(一次性回填,确定性)。

背景:早期"一标签一概念"自动建档把「防火墙/白名单申请」「防火墙/白名单运维」
「防火墙/白名单备岗」等拆成了多个并列概念。本脚本把"职能前缀/后缀"剥离后归并到
根概念(不存在则创建),并废弃孤儿概念,让检索能整组召回。

规则:
- 只处理 concept-auto-* 且只挂了 1 个标签的 seed 概念(碎片化来源);
- 剥离 熟悉/擅长/了解/精通/掌握 前缀 与 -申请/-运维/-备岗/-负责人/-故障处理/-咨询/
  -责任边界/-问题响应快/-分配/-开通/-双层校验 等职能后缀;
- 剥离后为空或与原文相同 → 不动;
- 标签映射重挂到根概念,孤儿概念 deprecated。

用法: python scripts/relink_tags.py [--apply]   (默认 dry-run)
"""
from __future__ import annotations

import asyncio
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core import db  # noqa: E402

PREFIX_RE = re.compile(r"^(熟悉|擅长|了解|精通|掌握|深耕|负责)")
SUFFIX_RE = re.compile(
    r"[-/]?(申请|运维|备岗|负责人|故障处理|咨询|责任边界|问题响应快|分配|开通|办理|值班|"
    r"双层校验|核心功能研发|总体负责人|使用咨询|问题答疑)$")


def root_name(text: str) -> str:
    """剥离职能前缀/后缀,得到根概念名。"""
    name = text.strip()
    prev = None
    while prev != name:
        prev = name
        name = PREFIX_RE.sub("", name)
        name = SUFFIX_RE.sub("", name)
        name = name.strip("-/ ")
    return name


async def main() -> None:
    apply = "--apply" in sys.argv
    await db.init_pool()
    try:
        # 只挂 1 个标签的 concept-auto-* seed 概念
        rows = await db.fetch(
            "SELECT c.concept_id, c.canonical_name, m.tag_id, rt.text"
            " FROM agent.concepts c"
            " JOIN agent.tag_concept_map m ON m.concept_id = c.concept_id"
            " JOIN agent.raw_tags rt ON rt.tag_id = m.tag_id"
            " WHERE c.status='seed' AND c.concept_id LIKE 'concept-auto-%'"
            "   AND (SELECT count(*) FROM agent.tag_concept_map m2 WHERE m2.concept_id=c.concept_id) = 1")
        print(f"[scan] 碎片概念(单标签自动建档): {len(rows)}")

        merged, skipped = [], []
        for r in rows:
            root = root_name(r["text"])
            if not root or root == r["text"].strip():
                skipped.append(r["text"])
                continue
            merged.append((r["text"], root, r["tag_id"], r["concept_id"]))

        print(f"[plan] 可归并 {len(merged)} 条, 无需处理 {len(skipped)} 条")
        for text, root, _, _ in merged[:30]:
            print(f"  {text}  =>  {root}")
        if len(merged) > 30:
            print(f"  ... 共 {len(merged)} 条")

        if not apply:
            print("dry-run,加 --apply 生效")
            return

        n_map = n_dep = 0
        for text, root, tag_id, orphan_cid in merged:
            # 找/建根概念
            cid = await db.fetchval(
                "SELECT concept_id FROM agent.concepts WHERE canonical_name=$1 AND status IN ('seed','active')",
                root)
            if not cid:
                cid = f"concept-merge-{uuid.uuid4().hex[:8]}"
                await db.execute(
                    "INSERT INTO agent.concepts(concept_id, canonical_name, concept_type, status,"
                    " source_tags, description) VALUES($1,$2,'domain','seed',$3,$4)",
                    cid, root, [text], "碎片概念归并根(职能后缀归并)")
            # 重挂映射
            await db.execute(
                "INSERT INTO agent.tag_concept_map(map_id, tag_id, concept_id, mapping_type,"
                " confidence, generated_by, review_status, reason)"
                " VALUES($1,$2,$3,'near_alias',0.95,'rule','auto_approved','职能后缀归并')"
                " ON CONFLICT (tag_id, concept_id) DO NOTHING",
                f"map-{uuid.uuid4().hex[:8]}", tag_id, cid)
            await db.execute(
                "DELETE FROM agent.tag_concept_map WHERE tag_id=$1 AND concept_id=$2",
                tag_id, orphan_cid)
            n_map += 1
            # 孤儿概念废弃
            left = await db.fetchval(
                "SELECT count(*) FROM agent.tag_concept_map WHERE concept_id=$1", orphan_cid)
            if not left:
                await db.execute(
                    "UPDATE agent.concepts SET status='deprecated', valid_to=now() WHERE concept_id=$1",
                    orphan_cid)
                n_dep += 1
        print(f"[done] 重挂映射 {n_map} 条, 废弃孤儿概念 {n_dep} 个")
    finally:
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
