"""AGUI 收口接口的请求/响应模型（字段名直接对齐前端 mock 的 camelCase）"""
from pydantic import BaseModel


class AguiMessage(BaseModel):
    """前端发来的单条消息"""
    id: str | None = None
    role: str = "user"
    text: str = ""


class AguiContext(BaseModel):
    """前端发来的上下文（userId / page / clientTraceId）"""
    userId: str | None = None
    page: str | None = None
    clientTraceId: str | None = None


class SendMessageRequest(BaseModel):
    """POST /agui/sessions/{id}/messages 请求体"""
    message: AguiMessage
    context: AguiContext | None = None


class InteractionEvent(BaseModel):
    """POST /agui/events 请求体（reporter.js 上报的交互事件）"""
    sessionId: str | None = None
    messageId: str | None = None
    eventType: str | None = None
    targetType: str | None = None
    targetId: str | None = None
    value: str | None = None
    context: dict | None = None
    timestamp: str | None = None
