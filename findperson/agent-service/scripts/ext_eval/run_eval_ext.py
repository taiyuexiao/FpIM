"""外部模拟数据 200 题评测。

用法:
  .\venv\Scripts\python.exe scripts\ext_eval\run_eval_ext.py [--split dev|test|all] [--limit N] [--baselines D,C]
环境:
  PGDATABASE=shouwenzeren_ext
  OKF_REPO_DIR=knowledge-okf-ext
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.core.db import close_pool, init_pool  # noqa: E402
from app.eval.metrics import (  # noqa: E402
    CaseResult, MetricsAccumulator, attribute_error, hit_at_k, recall_at_k,
)
from app.eval.runner import EvaluationRunner  # noqa: E402

EXT_DIR = Path(r"C:\Users\12115\Downloads\首问责任平台模拟数据评测与技术方案")
QUESTIONS_FILE = EXT_DIR / "evaluation_questions_200.jsonl"

QUERY_TYPE_MAP: dict[str, str] = {
    "explicit_exact": "explicit_responsibility",
    "alias_lookup": "explicit_responsibility",
    "duty_specific": "diagnostic",
    "diagnostic": "explicit_responsibility",
    "cross_system_diagnostic": "diagnostic",
    "broad_concept": "expert_finding",
    "expert_finding": "expert_finding",
    "department_contact": "contact_lookup",
}

INTENT_MAP: dict[str, str] = {
    "article_citation": "knowledge_qa",
}


def _arg(name: str, default: str) -> str:
    for i, a in enumerate(sys.argv):
        if a == name and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return default


def load_external_cases(split: str = "all", limit: int | None = None) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with open(QUESTIONS_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            if split != "all" and raw.get("split") != split:
                continue
            gold: dict[str, Any] = {}
            # 系统内结构化/RAG 证据返回的 person_id 都是 public.people.id(P0001),
            # OKF 文档 id 为 person-P0001,但 RagEvidenceAdapter 会去除前缀。
            person_ids = list(raw.get("acceptable_person_ids", []))
            if raw.get("gold_primary_person_id"):
                primary = raw["gold_primary_person_id"]
                if primary not in person_ids:
                    person_ids.insert(0, primary)
                gold["primary_person_id"] = primary
            gold["person_ids"] = person_ids
            gold["concept_names"] = raw.get("gold_concept_names", [])
            docs = []
            if raw.get("gold_article_id"):
                docs.append(f"content-{raw['gold_article_id']}")
            gold["document_ids"] = docs

            ext_qt = raw.get("query_type", "explicit_exact")
            intent = INTENT_MAP.get(ext_qt, "find_person")
            query_type = QUERY_TYPE_MAP.get(ext_qt, "explicit_responsibility")

            cases.append({
                "id": raw["test_id"],
                "query": raw["question"],
                "intent": intent,
                "query_type": query_type,
                "ext_query_type": ext_qt,
                "difficulty": raw.get("difficulty", "unknown"),
                "expected_identity": raw.get("expected_identity", ""),
                "expected_evidence_tier": raw.get("expected_evidence_tier", 0),
                "gold": gold,
            })
            if limit and len(cases) >= limit:
                break
    return cases


def primary_top1(r: CaseResult) -> bool:
    primary = r.gold_person_ids[0] if r.gold_person_ids else None
    return bool(primary and r.ranked_person_ids and r.ranked_person_ids[0] == primary)


def compute_metrics(results: list[CaseResult]) -> dict[str, Any]:
    acc = MetricsAccumulator()
    for r in results:
        acc.add(r)
    base = acc.summary()
    n = len(results)
    if n == 0:
        return base

    def avg(values):
        values = list(values)
        return round(sum(values) / len(values), 4) if values else 0.0

    fp = [r for r in results if r.intent == "find_person"]
    base["Primary Top1"] = avg(primary_top1(r) for r in fp if r.gold_person_ids)
    base["MRR"] = avg(
        (1.0 / (next((i + 1 for i, pid in enumerate(r.ranked_person_ids) if pid in r.gold_person_ids), 0)))
        if any(pid in r.ranked_person_ids for pid in r.gold_person_ids) else 0.0
        for r in fp if r.gold_person_ids
    )
    base["Final Recall@5"] = avg(
        hit_at_k(r.ranked_person_ids, r.gold_person_ids, 5) for r in fp if r.gold_person_ids
    )

    # 按外部 query_type / difficulty 分组
    by_qt: dict[str, list[CaseResult]] = {}
    by_diff: dict[str, list[CaseResult]] = {}
    for r in results:
        qt = getattr(r, "ext_query_type", r.query_type or "unknown")
        by_qt.setdefault(qt, []).append(r)
        diff = getattr(r, "difficulty", "unknown")
        by_diff.setdefault(diff, []).append(r)

    def group_metrics(group_results: list[CaseResult]) -> dict[str, float]:
        g_fp = [r for r in group_results if r.intent == "find_person"]
        return {
            "cases": len(group_results),
            "Final Top1": avg(
                hit_at_k(r.ranked_person_ids, r.gold_person_ids, 1) for r in g_fp if r.gold_person_ids
            ),
            "Final Recall@3": avg(
                hit_at_k(r.ranked_person_ids, r.gold_person_ids, 3) for r in g_fp if r.gold_person_ids
            ),
            "Primary Top1": avg(primary_top1(r) for r in g_fp if r.gold_person_ids),
        }

    base["by_query_type"] = {k: group_metrics(v) for k, v in sorted(by_qt.items())}
    base["by_difficulty"] = {k: group_metrics(v) for k, v in sorted(by_diff.items())}

    # article_citation 单独算文档召回
    article_cases = [r for r in results if getattr(r, "ext_query_type", None) == "article_citation"]
    if article_cases:
        base["Article Citation Doc Recall@5"] = avg(
            recall_at_k(r.rag_document_ids, r.gold_document_ids, 5)
            for r in article_cases if r.gold_document_ids
        )
    return base


class ExternalEvaluationRunner(EvaluationRunner):
    """复用内部 runner,但保留外部 query_type/difficulty 用于分组。"""

    def _to_result(self, case: dict, final: Any = None) -> CaseResult:
        r = super()._to_result(case, final)
        r.ext_query_type = case.get("ext_query_type")  # type: ignore[attr-defined]
        r.difficulty = case.get("difficulty")  # type: ignore[attr-defined]
        r.expected_identity = case.get("expected_identity")  # type: ignore[attr-defined]
        return r


async def run_baseline(cases: list[dict], baseline: str) -> dict[str, Any]:
    runner = ExternalEvaluationRunner()
    results: list[CaseResult] = []
    for i, case in enumerate(cases):
        print(f"[{baseline}] {i + 1}/{len(cases)} {case['id']}", flush=True)
        if baseline == "A":
            r = await runner.run_structured_only(case)
        elif baseline == "B":
            r = await runner.run_rag_only(case)
        elif baseline == "C":
            r = await runner.run_hybrid(case)
        elif baseline == "E":
            r = await runner.run_string_match_only(case)
        else:
            r = await runner.run_chain(case)
        # 补充分组字段
        r.ext_query_type = case.get("ext_query_type")  # type: ignore[attr-defined]
        r.difficulty = case.get("difficulty")  # type: ignore[attr-defined]
        r.expected_identity = case.get("expected_identity")  # type: ignore[attr-defined]
        if not r.error_attribution:
            r.error_attribution = attribute_error(r)
        results.append(r)
    metrics = compute_metrics(results)
    failed = [
        {"id": r.case_id, "query": r.query, "ranked": r.ranked_person_ids[:3],
         "gold": r.gold_person_ids, "attribution": r.error_attribution}
        for r in results if r.error_attribution
    ]
    return {"metrics": metrics, "failed_cases": failed, "results": [r.__dict__ for r in results]}


async def main() -> None:
    split = _arg("--split", "all")
    limit = int(_arg("--limit", "0")) or None
    baselines = tuple(_arg("--baselines", "D").split(","))
    cases = load_external_cases(split, limit)
    print(f"[ext_eval] 加载 {split} 用例: {len(cases)} 条")
    if not cases:
        return

    await init_pool()
    try:
        output: dict[str, Any] = {"split": split, "baselines": {}}
        for baseline in baselines:
            output["baselines"][baseline] = await run_baseline(cases, baseline)
    finally:
        await close_pool()

    for b, data in output["baselines"].items():
        m = data["metrics"]
        print(f"\n===== Baseline {b} ({split}) =====")
        for k, v in m.items():
            if k in ("by_query_type", "by_difficulty", "Error Attribution"):
                continue
            print(f"  {k}: {v}")
        if m.get("by_query_type"):
            print("  按 query_type:")
            for qt, gm in m["by_query_type"].items():
                print(f"    {qt}: {gm}")
        if m.get("by_difficulty"):
            print("  按 difficulty:")
            for diff, gm in m["by_difficulty"].items():
                print(f"    {diff}: {gm}")
        if m.get("Error Attribution"):
            print(f"  错误归因: {m['Error Attribution']}")

    out_dir = Path(__file__).resolve().parent.parent.parent / "data" / "eval_ext"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"report_{split}_{'_'.join(baselines)}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=1)
    print(f"\n[ext_eval] 报告已写入 {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
