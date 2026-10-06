"""金标准评测:对 data/golden.json 逐条跑真实主链,输出报告(用于改动前后对照)。

用法(在 _agent_exp 目录,用原 venv):
  python scripts/golden_eval.py [报告输出路径]
DB:测试一律连 shouwenzeren_test(conftest 同款隔离;评测链会写 query_concept_logs,勿指 newdb)。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("FASTEMBED_CACHE_PATH", r"C:\python\pycharm\shouwenzeren\deploy_bundle\fastembed_cache")
os.environ["PGDATABASE"] = "shouwenzeren_test"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.chain import build_orchestrator
from app.contracts.agent_state import AgentState, RequestState, UserContext
from app.core.db import close_pool, init_pool

USER = UserContext(user_id="P0002", name="冉紫萱", department_id=4, department="综合管理部")


async def run_case(orch, case: dict) -> dict:
    state = AgentState(request=RequestState(
        trace_id="t", run_id="r", user_context=USER,
        original_query=case["query"], normalized_query=case["query"]))
    t0 = time.time()
    final = await orch.run(state)
    latency = round((time.time() - t0) * 1000)

    i = final.intent
    cards = final.response.recommendation_cards
    card_brief = [{"pid": c["person_id"], "identity": c.get("identity"), "score": c.get("score")}
                  for c in cards]
    confirm = final.response.confirmation_card
    result = {
        "id": case["id"], "query": case["query"], "kind": case["kind"],
        "intent": i.intent and i.intent.value,
        "query_type": i.query_type and i.query_type.value,
        "cards": card_brief, "card_count": len(cards),
        "action": confirm and confirm["action"]["type"],
        "answer_head": (final.response.final_answer or "")[:120],
        "latency_ms": latency,
    }

    # 判定
    pids = [c["pid"] for c in card_brief]
    fails = []
    if case["kind"] == "find":
        for pid in case.get("expect_persons", []):
            if pid not in pids:
                fails.append(f"missing {pid}")
        expect_any = case.get("expect_any")
        if expect_any and not any(pid in pids for pid in expect_any):
            fails.append(f"none of {expect_any}")
        top1 = case.get("expect_top1")
        if top1 and (not pids or pids[0] != top1):
            fails.append(f"top1!={top1}")
        not_id = case.get("expect_identity_not")
        if not_id:
            for c in card_brief:
                if c["pid"] in case.get("expect_persons", []) and c["identity"] == not_id:
                    fails.append(f"{c['pid']} identity={not_id}")
        top1_id = case.get("expect_top1_identity")
        if top1_id and card_brief and card_brief[0]["identity"] != top1_id:
            fails.append(f"top1 identity={card_brief[0]['identity']}")
    elif case["kind"] == "nocard":
        if cards:
            fails.append(f"unexpected {len(cards)} cards")
    elif case["kind"] == "edit":
        if result["action"] != case["expect_action"]:
            fails.append(f"action={result['action']}")
    result["pass"] = not fails
    result["fails"] = fails
    return result


async def main() -> None:
    out_path = sys.argv[1] if len(sys.argv) > 1 else "golden_report.json"
    cases = json.load(open(os.path.join(os.path.dirname(__file__), "..", "data", "golden.json"),
                           encoding="utf-8"))
    await init_pool()
    orch = build_orchestrator()
    results = []
    for case in cases:
        r = await run_case(orch, case)
        results.append(r)
        mark = "PASS" if r["pass"] else "FAIL"
        print(f"[{mark}] {r['id']} {r['query'][:24]} intent={r['intent']}/{r['query_type']} "
              f"cards={r['card_count']} action={r['action']} {r['fails']} {r['latency_ms']}ms")
    await close_pool()
    report = {"results": results,
              "summary": {"total": len(results), "passed": sum(1 for r in results if r["pass"]),
                          "p95_latency_ms": sorted(r["latency_ms"] for r in results)[int(len(results) * 0.95) - 1]}}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nsummary: {report['summary']} -> {out_path}")


asyncio.run(main())
