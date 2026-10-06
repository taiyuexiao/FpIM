"""V2 测评集真实全链评测。

使用真实 DeepSeek LLM + 真实 bge-small-zh Embedding + V2 Excel 数据。
逐条运行并持续输出结果。

用法:
  .\\venv\\Scripts\\python.exe scripts\\run_v2_eval.py [--split dev|test] [--limit N] [--output result.jsonl]
"""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent.chain import build_orchestrator
from app.contracts.agent_state import AgentState, RequestState, UserContext
from app.core.db import close_pool, init_pool

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "v2_import"

# V2 query_type → 项目 QueryType 映射
QUERY_TYPE_MAP = {
    "explicit_exact": "explicit_responsibility",
    "alias_lookup": "explicit_responsibility",
    "duty_specific": "explicit_responsibility",
    "diagnostic": "diagnostic",
    "cross_system_diagnostic": "diagnostic",
    "expert_finding": "expert_finding",
    "broad_concept": "expert_finding",
    "department_contact": "contact_lookup",
    "multi_owner_routing": "explicit_responsibility",
    "process_guidance": "knowledge_qa",
    "boundary_case": "unclear",
}


def norm_pid(pid: str) -> str:
    """P0001 -> p-0001"""
    if pid and pid.startswith("P") and len(pid) == 5:
        return f"p-{pid[1:]}"
    return pid


def load_v2_cases(split: str = "dev") -> list[dict]:
    """加载 V2 评测集并转换为项目格式。"""
    with open(DATA_DIR / "evalset.json", encoding="utf-8") as f:
        raw = json.load(f)
    cases = []
    for r in raw:
        if r["split"] != split:
            continue
        acceptable = json.loads(r["acceptable_person_ids"]) if isinstance(r["acceptable_person_ids"], str) else (r["acceptable_person_ids"] or [])
        gold_pids = [norm_pid(p) for p in acceptable]
        gold_primary = norm_pid(r["gold_primary_person_id"]) if r["gold_primary_person_id"] else None
        if gold_primary and gold_primary not in gold_pids:
            gold_pids.insert(0, gold_primary)
        cases.append({
            "id": r["test_id"],
            "query": r["question"],
            "intent": "find_person" if r["query_type"] != "process_guidance" else "knowledge_qa",
            "query_type": QUERY_TYPE_MAP.get(r["query_type"], "explicit_responsibility"),
            "v2_query_type": r["query_type"],
            "difficulty": r["difficulty"],
            "gold_primary_person_id": gold_primary,
            "gold_person_ids": gold_pids,
            "gold_concept_names": json.loads(r["gold_concept_names"]) if isinstance(r["gold_concept_names"], str) else (r["gold_concept_names"] or []),
            "expected_identity": r.get("expected_identity"),
            "scenario_group": r.get("scenario_group"),
            "evaluation_mode": r.get("evaluation_mode"),
        })
    return cases


async def run_one(case: dict, timeout: float = 60.0) -> dict:
    """运行单条评测，返回结果。"""
    orch = build_orchestrator()
    state = AgentState(
        request=RequestState(
            trace_id=f"v2-{case['id']}",
            run_id="v2-eval",
            user_context=UserContext(user_id="p-0001", name="评测"),
            original_query=case["query"],
            normalized_query=" ".join(case["query"].split()),
        )
    )
    start = time.time()
    try:
        final = await asyncio.wait_for(orch.run(state), timeout=timeout)
        latency = time.time() - start
        ranked = [c["person_id"] for c in final.ranking.ranked_candidates]
        top1 = ranked[0] if ranked else None
        top3 = ranked[:3]
        gold_set = set(case["gold_person_ids"])
        hit_top1 = top1 in gold_set if gold_set else False
        hit_top3 = bool(set(top3) & gold_set) if gold_set else False
        hit_primary = top1 == case["gold_primary_person_id"] if case["gold_primary_person_id"] else False
        return {
            "id": case["id"],
            "query": case["query"],
            "v2_query_type": case["v2_query_type"],
            "difficulty": case["difficulty"],
            "gold_primary": case["gold_primary_person_id"],
            "gold_persons": case["gold_person_ids"],
            "predicted_top1": top1,
            "predicted_top3": top3,
            "hit_top1": hit_top1,
            "hit_top3": hit_top3,
            "hit_primary": hit_primary,
            "gate_decision": final.ranking.gate_decision.value if final.ranking.gate_decision else None,
            "degraded": final.execution.degraded,
            "latency_ms": round(latency * 1000, 2),
            "resolved_concepts": [c.get("canonical_name") for c in final.concept.resolved_concepts],
            "error": None,
        }
    except asyncio.TimeoutError:
        return {
            "id": case["id"], "query": case["query"], "v2_query_type": case["v2_query_type"],
            "difficulty": case["difficulty"], "gold_primary": case["gold_primary_person_id"],
            "gold_persons": case["gold_person_ids"], "predicted_top1": None, "predicted_top3": [],
            "hit_top1": False, "hit_top3": False, "hit_primary": False,
            "gate_decision": None, "degraded": True, "latency_ms": timeout * 1000,
            "resolved_concepts": [], "error": "timeout",
        }
    except Exception as e:
        return {
            "id": case["id"], "query": case["query"], "v2_query_type": case["v2_query_type"],
            "difficulty": case["difficulty"], "gold_primary": case["gold_primary_person_id"],
            "gold_persons": case["gold_person_ids"], "predicted_top1": None, "predicted_top3": [],
            "hit_top1": False, "hit_top3": False, "hit_primary": False,
            "gate_decision": None, "degraded": True, "latency_ms": (time.time() - start) * 1000,
            "resolved_concepts": [], "error": str(e)[:300],
        }


async def main() -> None:
    split = "dev"
    limit = None
    offset = 0
    output = None
    for i, arg in enumerate(sys.argv):
        if arg == "--split" and i + 1 < len(sys.argv):
            split = sys.argv[i + 1]
        elif arg == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])
        elif arg == "--offset" and i + 1 < len(sys.argv):
            offset = int(sys.argv[i + 1])
        elif arg == "--output" and i + 1 < len(sys.argv):
            output = sys.argv[i + 1]

    cases = load_v2_cases(split)
    if offset:
        cases = cases[offset:]
    if limit:
        cases = cases[:limit]

    print(f"V2 评测: split={split}, cases={len(cases)}")
    print(f"LLM: DeepSeek 真实 API | Embedding: bge-small-zh-v1.5 (512维)")
    print("=" * 80)

    await init_pool()
    results = []
    try:
        for idx, case in enumerate(cases, 1):
            result = await run_one(case)
            results.append(result)
            status = "PASS" if result["hit_top1"] else ("PART" if result["hit_top3"] else "FAIL")
            print(f"[{idx:3d}/{len(cases)}] {status} {case['id']} | {case['v2_query_type']:20s} | "
                  f"gold={case['gold_primary_person_id']} pred={result['predicted_top1']} | "
                  f"top1={result['hit_top1']} top3={result['hit_top3']} | "
                  f"{result['latency_ms']:.0f}ms")
            if not result["hit_top1"]:
                print(f"      concepts={result['resolved_concepts']} gate={result['gate_decision']} degraded={result['degraded']}")
            if result["error"]:
                print(f"      ERROR: {result['error']}")
    finally:
        await close_pool()

    # 统计
    n = len(results)
    top1_hits = sum(1 for r in results if r["hit_top1"])
    top3_hits = sum(1 for r in results if r["hit_top3"])
    primary_hits = sum(1 for r in results if r["hit_primary"])
    errors = sum(1 for r in results if r["error"])
    avg_latency = sum(r["latency_ms"] for r in results) / max(n, 1)

    print("=" * 80)
    print(f"总计: {n} 条 | Top1={top1_hits}/{n} ({top1_hits/n*100:.1f}%) | "
          f"Top3={top3_hits}/{n} ({top3_hits/n*100:.1f}%) | "
          f"Primary={primary_hits}/{n} ({primary_hits/n*100:.1f}%) | "
          f"错误={errors} | 平均延迟={avg_latency:.0f}ms")

    # 按 query_type 统计
    by_type: dict[str, dict] = {}
    for r in results:
        qt = r["v2_query_type"]
        if qt not in by_type:
            by_type[qt] = {"n": 0, "top1": 0, "top3": 0}
        by_type[qt]["n"] += 1
        by_type[qt]["top1"] += r["hit_top1"]
        by_type[qt]["top3"] += r["hit_top3"]
    print("\n按 query_type 分布:")
    for qt, s in sorted(by_type.items()):
        print(f"  {qt:25s} n={s['n']:2d} top1={s['top1']:2d}({s['top1']/s['n']*100:5.1f}%) "
              f"top3={s['top3']:2d}({s['top3']/s['n']*100:5.1f}%)")

    if output:
        with open(output, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"\n结果已写入: {output}")


if __name__ == "__main__":
    asyncio.run(main())
