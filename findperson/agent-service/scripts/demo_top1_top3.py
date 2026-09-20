"""演示:Top1/Top3 命中的判定(取 3 个真实用例打印 ranked 与 gold 对照)。"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.db import close_pool, fetch, init_pool  # noqa: E402
from app.eval.runner import EvaluationRunner, load_cases  # noqa: E402


async def main() -> None:
    await init_pool()
    runner = EvaluationRunner()
    cases = [c for c in load_cases("test") if c["query_type"] in
             ("explicit_responsibility", "expert_finding")][:3]
    for case in cases:
        r = await runner.run_chain(case)
        gold = r.gold_person_ids
        rows = await fetch("SELECT id, name FROM public.people WHERE id = ANY($1)",
                           (r.ranked_person_ids + gold)[:12])
        names = {row["id"]: row["name"] for row in rows}
        print(f"\nQ: {case['query']}")
        print(f"  gold(对的人): {[names.get(g, g) for g in gold][:6]}{'...' if len(gold) > 6 else ''}")
        for i, pid in enumerate(r.ranked_person_ids[:3], 1):
            hit = "[命中]" if pid in gold else "[未中]"
            print(f"  Top{i}: {names.get(pid, pid)} {hit}")
        top1 = bool(set(r.ranked_person_ids[:1]) & set(gold))
        top3 = bool(set(r.ranked_person_ids[:3]) & set(gold))
        print(f"  → Top1命中={top1}, Top3命中={top3}")
    await close_pool()


asyncio.run(main())
