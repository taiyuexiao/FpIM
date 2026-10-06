"""反馈回流导出(离线部分,功能详细说明v4 §十二:推荐效果评估数据)。

产出:
1. data/feedback_export.jsonl —— 推荐记录 × 反馈 关联数据(评测/调优用);
2. 点踩(dislike)案例写入 agent.concept_review_queue(item_type='anomaly'),
   供概念/别名治理复核(例:某概念下人员被反复点踩 → 检查别名/映射质量)。

用法: .\\venv\\Scripts\\python.exe scripts\\export_feedback.py [--out data\\feedback_export.jsonl]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.db import close_pool, init_pool  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/feedback_export.jsonl")
    args = parser.parse_args()

    await init_pool()
    try:
        from app.core import db
        rows = await db.fetch(
            "SELECT f.id, f.trace_id, f.session_id, f.message_id, f.user_id,"
            "       f.feedback_type, f.target_type, f.target_id, f.value, f.reason,"
            "       f.created_at, r.query_summary, r.query_type, r.rank_policy,"
            "       r.ranked_candidates, r.gate_decision"
            " FROM agent.feedback_events f"
            " LEFT JOIN agent.agent_recommendation_logs r"
            "   ON r.message_id = f.message_id AND r.message_id <> ''"
            " WHERE f.feedback_type IN ('like','dislike')"
            " ORDER BY f.id",
        )
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        n = 0
        with out_path.open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps({
                    "feedback_id": r["id"], "trace_id": r["trace_id"],
                    "session_id": r["session_id"], "message_id": r["message_id"],
                    "user_id": r["user_id"], "feedback_type": r["feedback_type"],
                    "target_type": r["target_type"], "target_id": r["target_id"],
                    "value": r["value"], "reason": r["reason"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                    "query_summary": r["query_summary"], "query_type": r["query_type"],
                    "rank_policy": r["rank_policy"],
                    "ranked_candidates": r["ranked_candidates"],
                    "gate_decision": r["gate_decision"],
                }, ensure_ascii=False, default=str) + "\n")
                n += 1
        print(f"[export] {n} 条反馈已导出 → {out_path}")

        # 点踩人员案例 → 概念治理复核队列(幂等:同 message+target 不重复入队)
        dislikes = [r for r in rows if r["feedback_type"] == "dislike"
                    and r["target_type"] == "person"]
        enqueued = 0
        for r in dislikes:
            payload = {
                "source": "user_feedback", "person_id": r["target_id"],
                "message_id": r["message_id"], "query_summary": r["query_summary"],
                "reason": r["reason"],
            }
            exists = await db.fetchval(
                "SELECT 1 FROM agent.concept_review_queue"
                " WHERE item_type='anomaly' AND status='pending'"
                "   AND payload->>'source'='user_feedback'"
                "   AND payload->>'person_id'=$1 AND payload->>'message_id'=$2",
                r["target_id"], r["message_id"])
            if exists:
                continue
            await db.execute(
                "INSERT INTO agent.concept_review_queue(review_id, item_type, payload)"
                " VALUES($1,'anomaly',$2)",
                f"fb-{r['id']}", json.dumps(payload, ensure_ascii=False))
            enqueued += 1
        print(f"[export] {enqueued} 条点踩案例入治理队列(共 {len(dislikes)} 条人员点踩)")
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
