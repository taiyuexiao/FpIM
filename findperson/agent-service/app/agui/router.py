"""AGUI HTTP 路由(前端 src/services/api/agui.js + agui/transport.js 对齐)。

端点:
- POST /api/agui/sessions                     创建会话
- GET  /api/agui/sessions/{session_id}/state  会话状态(历史消息/卡片)
- POST /api/agui/sessions/{session_id}/messages  发送消息(SSE 事件流)
- POST /api/agui/events                       交互/反馈事件上报

文档兼容端点(实施方案v3 §3.2):
- POST /agent/feedback          提交带 trace_id 的推荐反馈
- GET  /agent/feedback/reasons  点踩原因配置

身份适配器[Demo]:X-User-Id 头优先,其次请求体 context.userId;均经 public.people 校验。
正式环境由网关/JWT 替换,接入接口不变(同 /agent/chat 约定)。
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.agui.service import AguiService
from app.api_agent import _build_user_context
from app.contracts.agent_state import UserContext
from app.feedback.repository import FeedbackRepository
from app.feedback.service import FeedbackService

router = APIRouter(tags=["agui"])
_service = AguiService()
_feedback_repo = FeedbackRepository()
_feedback_service = FeedbackService()

MAX_QUERY_LEN = 10000  # 对话发布长文需要(正文照抄原文);仍兜底防滥用


# ---------------------------------------------------------------- 请求模型

class CreateSessionRequest(BaseModel):
    title: str = "新对话"
    userId: str | None = None


class AguiMessage(BaseModel):
    id: str = ""
    role: str = "user"
    text: str = Field(min_length=1, max_length=MAX_QUERY_LEN)


class AguiContext(BaseModel):
    userId: str | None = None
    page: str = ""
    clientTraceId: str = ""
    # 前端本地生成的助手消息 ID:服务端事件必须以此归属(v3 §3.3 事件归属约束)
    assistantMessageId: str = ""


class SendMessageRequest(BaseModel):
    message: AguiMessage
    context: AguiContext = AguiContext()


class EventReport(BaseModel):
    """前端 reporter.js 上报结构。"""

    sessionId: str = ""
    messageId: str = ""
    eventType: str = "interaction"
    targetType: str = ""
    targetId: str = ""
    value: str = ""
    reason: str = ""
    traceId: str = ""
    context: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = ""


class FeedbackRequest(BaseModel):
    """文档契约(实施方案v3 §3.2):推荐反馈必须带 trace_id。"""

    trace_id: str
    session_id: str | None = None
    message_id: str = ""
    target_type: str = "answer"
    target_id: str = ""
    value: str  # up/down
    reason: str = ""
    user_id: str = ""


# ---------------------------------------------------------------- 身份

async def _resolve_user_context(x_user_id: str | None, payload_user_id: str | None) -> UserContext:
    return await _build_user_context(x_user_id or payload_user_id)


# ---------------------------------------------------------------- AGUI 端点

@router.post("/api/agui/sessions")
async def create_session(body: CreateSessionRequest,
                         x_user_id: str | None = Header(default=None)):
    ctx = await _resolve_user_context(x_user_id, body.userId)
    return await _service.create_session(ctx.user_id, body.title)


@router.get("/api/agui/sessions/{session_id}/state")
async def session_state(session_id: str):
    state = await _service.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return state


@router.post("/api/agui/sessions/{session_id}/messages")
async def send_message(session_id: str, body: SendMessageRequest,
                       x_user_id: str | None = Header(default=None)):
    try:
        ctx = await _resolve_user_context(x_user_id, body.context.userId)
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    text = " ".join(body.message.text.split())
    if not text:
        raise HTTPException(status_code=400, detail="message.text 不能为空")

    async def stream():
        async for event in _service.run_message(
            session_id=session_id, text=text, user_context=ctx,
            user_message_id=body.message.id,
            client_trace_id=body.context.clientTraceId,
            assistant_message_id=body.context.assistantMessageId,
        ):
            # 前端 transport.js 只解析 data: 行,事件类型在 JSON 的 type 字段内
            yield {"data": json.dumps(event, ensure_ascii=False)}

    return EventSourceResponse(stream())


@router.post("/api/agui/events")
async def report_event(body: EventReport,
                       x_user_id: str | None = Header(default=None)):
    """交互/反馈上报。value=up/down 视为互斥反馈,其余为普通交互事件。"""
    user_id = x_user_id or str(body.context.get("userId") or "")
    if body.value in ("up", "down"):
        result = await _feedback_repo.record_vote(
            user_id=user_id, target_type=body.targetType or "answer",
            target_id=body.targetId or body.messageId, value=body.value,
            message_id=body.messageId, session_id=body.sessionId or None,
            trace_id=body.traceId, reason=body.reason, payload=body.context,
        )
        return {"ok": True, **result}
    await _feedback_repo.record_interaction(
        user_id=user_id, event_type=body.eventType,
        target_type=body.targetType, target_id=body.targetId,
        message_id=body.messageId, session_id=body.sessionId or None,
        trace_id=body.traceId, context=body.context,
    )
    return {"ok": True}


# ---------------------------------------------------------------- 文档兼容端点(v3 §3.2)

@router.post("/agent/feedback")
async def submit_feedback(body: FeedbackRequest):
    result = await _feedback_repo.record_vote(
        user_id=body.user_id, target_type=body.target_type,
        target_id=body.target_id or body.message_id, value=body.value,
        message_id=body.message_id, session_id=body.session_id,
        trace_id=body.trace_id, reason=body.reason,
    )
    return {"ok": True, **result}


@router.get("/agent/feedback/reasons")
async def feedback_reasons():
    return {"reasons": _feedback_service.down_reasons()}
