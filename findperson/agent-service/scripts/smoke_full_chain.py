"""全链路冒烟:AGUI 会话 → 找人问答(SSE 事件) → 写操作确认卡 → 反馈互斥 → 回流。

用法:
  .\\venv\\Scripts\\python scripts\\smoke_full_chain.py              # 真实 LLM(DeepSeek)
  .\\venv\\Scripts\\python scripts\\smoke_full_chain.py --mock-llm   # 离线 Mock LLM

注意:RAG Embedding 由 EMBEDDING_PROVIDER 决定(mock=离线链路验证;
openai_compatible=生产 1536 维,需先以同一 provider 重建索引)。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

if "--mock-llm" in sys.argv:
    os.environ["LLM_USE_MOCK"] = "1"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agui.service import AguiService  # noqa: E402
from app.contracts.agent_state import UserContext  # noqa: E402
from app.core import db  # noqa: E402
from app.core.db import close_pool, init_pool  # noqa: E402
from app.feedback.repository import FeedbackRepository  # noqa: E402


async def run() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock-llm", action="store_true")
    args = parser.parse_args()
    print(f"[smoke] LLM={'mock' if args.mock_llm else 'real(deepseek)'}")

    await init_pool()
    try:
        # 0) 找一个真实用户做上下文
        row = await db.fetchrow(
            "SELECT id, name, department, department_id FROM public.people"
            " WHERE status='active' ORDER BY id LIMIT 1")
        assert row, "public.people 为空,请先 import_v2_data"
        ctx = UserContext(user_id=row["id"], name=row["name"],
                          department=row["department"], department_id=row["department_id"])
        print(f"[smoke] 用户: {ctx.name}({ctx.user_id})")

        service = AguiService()

        # 1) 创建会话
        session = await service.create_session(ctx.user_id)
        sid = session["sessionId"]
        print(f"[smoke] 会话: {sid}")

        # 2) 找人问题 → 期望 run_started/text_delta/recommendation_cards/run_finished
        q1 = "谁负责模型网关?"
        events1 = [e async for e in service.run_message(
            session_id=sid, text=q1, user_context=ctx, user_message_id="msg-u-smoke-1")]
        types1 = [e["type"] for e in events1]
        print(f"[smoke] Q1={q1} 事件序列: {types1}")
        assert types1[0] == "run_started" and types1[-1] == "run_finished"
        assert "text_delta" in types1 and "text_finished" in types1
        answer1 = "".join(e.get("delta", "") for e in events1 if e["type"] == "text_delta")
        print(f"[smoke] Q1 回答前 120 字: {answer1[:120]}")
        cards = next((e["cards"] for e in events1 if e["type"] == "recommendation_cards"), [])
        print(f"[smoke] Q1 推荐卡片: {[c['person']['name'] for c in cards]}")
        for c in cards:
            assert c["reasons"] and all("匹配度高" not in r for r in c["reasons"])

        # 3) 写操作 → 期望 confirmation_card
        q2 = "修改我的联系方式为 010-8888"
        events2 = [e async for e in service.run_message(
            session_id=sid, text=q2, user_context=ctx, user_message_id="msg-u-smoke-2")]
        types2 = [e["type"] for e in events2]
        print(f"[smoke] Q2={q2} 事件序列: {types2}")
        card = next((e["card"] for e in events2 if e["type"] == "confirmation_card"), None)
        if card is None:
            print("[smoke] WARN: 未产出确认卡(mock LLM 提取为空时属预期降级)")
        else:
            assert card["kind"] == "confirmation" and card["action"]["type"] == "profile"
            print(f"[smoke] Q2 确认卡: {card['action']['nextProfilePatch']}")

        # 4) 反馈:up → down(改值) → down(取消)
        repo = FeedbackRepository()
        r1 = await repo.record_vote(user_id=ctx.user_id, target_type="person",
                                    target_id=cards[0]["personId"] if cards else "p-0001",
                                    value="up", message_id="msg-a-smoke-1",
                                    session_id=sid, trace_id="smoke")
        r2 = await repo.record_vote(user_id=ctx.user_id, target_type="person",
                                    target_id=cards[0]["personId"] if cards else "p-0001",
                                    value="down", message_id="msg-a-smoke-1",
                                    session_id=sid, trace_id="smoke", reason="人选不对")
        r3 = await repo.record_vote(user_id=ctx.user_id, target_type="person",
                                    target_id=cards[0]["personId"] if cards else "p-0001",
                                    value="down", message_id="msg-a-smoke-1",
                                    session_id=sid, trace_id="smoke")
        assert (r1["status"], r2["status"], r3["status"]) == ("recorded", "updated", "cancelled")
        print("[smoke] 反馈互斥/改值/取消: OK")

        # 5) 会话状态与推荐日志
        state = await service.get_state(sid)
        assert state and state["turnCount"] >= 1 and len(state["messages"]) >= 2
        n_reco = await db.fetchval(
            "SELECT count(*) FROM agent.agent_recommendation_logs WHERE session_id=$1", sid)
        print(f"[smoke] 会话消息: {len(state['messages'])} 条, 推荐日志: {n_reco} 条")

        print("[smoke] 全链路冒烟通过 ✅")
        return 0
    finally:
        await close_pool()


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
