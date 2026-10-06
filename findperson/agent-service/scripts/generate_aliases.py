"""批量别名生成:从概念的映射标签/标准名/已有别名中提取拉丁字母词条,登记为概念别名。

规则(确定性,§7.3 别名治理的批量冷启动):
- 词条来源:概念的 canonical_name + 已有 alias + 所有 approved 映射的 raw_tag 文本;
- 提取其中的拉丁字母 token(如 "Hadoop平台" → hadoop、"大模型API Key" → api/key 太泛会被消歧过滤);
- 同一 token 只对应唯一概念时才登记(多概念共享的泛词跳过,避免错路由);
- 已有别名不动(ON CONFLICT DO NOTHING);normalized 与查询侧一致(压缩空白+小写)。

用法: python scripts/generate_aliases.py [--apply]   (默认 dry-run 打印计划)
"""
from __future__ import annotations

import asyncio
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core import db  # noqa: E402

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#.]*")
MIN_LEN = 2  # 单字母不收


def _tokens(text: str) -> set[str]:
    return {m.group(0).lower() for m in TOKEN_RE.finditer(text or "")
            if len(m.group(0)) >= MIN_LEN}


async def main() -> None:
    apply = "--apply" in sys.argv
    await db.init_pool()
    try:
        # 概念 → 文本集合(标准名 + 已有别名 + 已生效映射的标签原文)
        concepts = await db.fetch(
            "SELECT concept_id, canonical_name FROM agent.concepts WHERE status IN ('seed','active')")
        aliases = await db.fetch("SELECT concept_id, alias FROM agent.concept_aliases")
        tag_rows = await db.fetch(
            "SELECT m.concept_id, rt.text FROM agent.tag_concept_map m"
            " JOIN agent.raw_tags rt ON rt.tag_id = m.tag_id"
            " WHERE m.review_status IN ('auto_approved','approved')")

        texts_by_concept: dict[str, set[str]] = {}
        for r in concepts:
            texts_by_concept.setdefault(r["concept_id"], set()).add(r["canonical_name"])
        for r in aliases:
            texts_by_concept.setdefault(r["concept_id"], set()).add(r["alias"])
        for r in tag_rows:
            texts_by_concept.setdefault(r["concept_id"], set()).add(r["text"])

        # token → concepts(消歧)
        token_concepts: dict[str, set[str]] = {}
        for cid, texts in texts_by_concept.items():
            for t in texts:
                for tok in _tokens(t):
                    token_concepts.setdefault(tok, set()).add(cid)

        # 已有 alias 集合(避免重复)
        existing = {(r["concept_id"], r["alias"]) for r in aliases}

        plan: list[tuple[str, str]] = []   # (token, concept_id)
        ambiguous: list[tuple[str, list[str]]] = []
        for tok, cids in sorted(token_concepts.items()):
            if len(cids) > 1:
                ambiguous.append((tok, sorted(cids)))
                continue
            cid = next(iter(cids))
            if (cid, tok) not in existing:
                plan.append((tok, cid))

        print(f"[plan] 待新增别名 {len(plan)} 条; 跳过歧义词 {len(ambiguous)} 个")
        for tok, cid in plan[:40]:
            print(f"  + {tok} -> {cid}")
        if len(plan) > 40:
            print(f"  ... 等共 {len(plan)} 条")
        if ambiguous:
            print("[skip] 歧义词示例(多概念共享,不自动登记):")
            for tok, cids in ambiguous[:15]:
                print(f"  - {tok}: {cids}")

        if apply and plan:
            for tok, cid in plan:
                await db.execute(
                    "INSERT INTO agent.concept_aliases(alias_id, concept_id, alias)"
                    " VALUES($1,$2,$3) ON CONFLICT (concept_id, alias) DO NOTHING",
                    f"alias-auto-{uuid.uuid4().hex[:8]}", cid, tok)
            print(f"[done] 已写入 {len(plan)} 条别名")
    finally:
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
