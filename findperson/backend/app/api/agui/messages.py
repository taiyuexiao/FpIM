"""AGUI 问答收口：POST /agui/sessions/{session_id}/messages（SSE 透传 + 落库）

链路：收前端 message → 存 public.messages → 转发 Agent → SSE 事件流回前端
      同时从结果顺路落库 recommendation_logs / 回填 messages 字段。
"""
import json
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ...core.database import get_db, SessionLocal
from ...middleware.deps import get_current_user
from ...models.assistant import RecommendationLog
from ...models.session import Message, Session
from ...services.agent_client import (
    agent_available, build_agent_payload, call_agent, map_cards_to_logs,
)
from .schemas import SendMessageRequest

router = APIRouter(prefix="/sessions", tags=["AGUI"])

_RANK_LABELS = ["首推", "可协助", "相关人员"]


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _reply_text(action: dict, matches: list) -> str:
    atype = action.get("type") if action else "match"
    if atype == "profile":
        return action.get("description") or "检测到资料维护需求。"
    if atype == "review":
        return "好的，我为你整理了一条评价草稿，请确认。"
    if atype == "content":
        return action.get("description") or "已整理内容发布草稿。"
    if matches:
        return "好的，下面为你推荐相关负责人。"
    return "目前还没有找到足够明确的对象，建议补充系统名、流程名或材料名。"


@router.post("/{session_id}/messages", summary="Send AGUI Message", description="问答主入口（SSE 流式返回）")
def send_message(
    session_id: str,
    body: SendMessageRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    # 前端用自己的会话 ID（session-xxx）发消息，该会话可能未落库（v1 无 POST /sessions 建会话接口）。
    # 兜底：会话不存在则按前端 ID 建会话，避免 messages.session_id 外键失败。
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        db.add(Session(id=session_id, user_id=user.id, title="新对话"))
        db.commit()
    question = body.message.text.strip()
    message_id = uuid.uuid4().hex[:12]
    run_id = (body.context.clientTraceId if body.context else None) or f"run-{uuid.uuid4().hex[:12]}"

    return StreamingResponse(
        _event_stream(session_id, message_id, run_id, user.id, question),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _event_stream(session_id: str, message_id: str, run_id: str, user_id: str, question: str):
    db = SessionLocal()
    common = {"sessionId": session_id, "runId": run_id, "messageId": message_id}
    try:
        # 1. 存消息
        msg = Message(id=message_id, session_id=session_id, user_id=user_id, question=question)
        db.add(msg)
        db.commit()

        # 2. 转发 Agent（未配置则降级）
        result = None
        if agent_available():
            payload = build_agent_payload(question, user_id, session_id)
            result = await run_in_threadpool(call_agent, payload)

        if not result:
            # 降级：只存 message，返回空推荐 + 提示
            yield _sse({"type": "run_started", **common, "result": {
                "analysis": {"intent": None, "domains": [], "tokens": [], "confidence": 0},
                "action": {"type": "match"}, "matches": [], "contentHits": [],
            }})
            yield _sse({"type": "text_delta", **common, "delta": "智能问答服务暂未接入，请稍后重试。"})
            yield _sse({"type": "text_finished", **common})
            yield _sse({"type": "run_finished", **common})
            return

        analysis = result.get("analysis") or {}
        action = result.get("action") or {"type": "match"}
        matches = result.get("matches") or []

        # 3. 回填消息字段（意图 / 领域 / 关键词 / 置信度 / 动作）
        msg.intent = analysis.get("intent")
        msg.domains = analysis.get("domains")
        msg.tokens = analysis.get("tokens")
        msg.confidence = analysis.get("confidence")
        msg.action_type = action.get("type")
        if action.get("type") != "match":
            msg.action_json = action
        db.commit()

        # 4. 流式输出事件
        yield _sse({"type": "run_started", **common, "result": result})
        reply = _reply_text(action, matches)
        for i in range(0, len(reply), 4):
            yield _sse({"type": "text_delta", **common, "delta": reply[i:i + 4]})
        yield _sse({"type": "text_finished", **common})

        if action.get("type") == "match" and matches:
            cards = []
            for i, m in enumerate(matches):
                person = m.get("person") or {}
                cards.append({
                    "id": f"rec-{message_id}-{person.get('id')}",
                    "kind": "recommendation",
                    "rank": i + 1,
                    "rankLabel": _RANK_LABELS[i] if i < len(_RANK_LABELS) else "相关人员",
                    "person": person,
                    "personId": person.get("id"),
                    "reasons": m.get("reasons") or [],
                    "related": m.get("related") or [],
                })
            # 落库推荐日志（一行一个被推荐人）
            for row in map_cards_to_logs(cards, message_id, session_id, user_id, question):
                db.add(RecommendationLog(**row))
            db.commit()
            yield _sse({"type": "recommendation_cards", **common, "cards": cards})
        else:
            card = {
                "id": f"confirm-{message_id}", "kind": "confirmation",
                "action": action, "analysis": analysis, "status": "active",
            }
            yield _sse({"type": "confirmation_card", **common, "card": card})

        yield _sse({"type": "state_delta", **common, "patch": {
            "title": question[:28],
            "turnCountIncrement": 1,
            "summary": f"{question} {analysis.get('intent') or ''}",
        }})
        yield _sse({"type": "run_finished", **common})
    finally:
        db.close()
