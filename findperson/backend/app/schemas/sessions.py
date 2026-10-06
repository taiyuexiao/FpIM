from datetime import datetime
from pydantic import BaseModel


class SessionResponse(BaseModel):
    """会话列表项"""
    id: str
    user_id: str
    title: str
    summary: str
    turn_count: int
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    """消息记录"""
    id: str
    session_id: str
    user_id: str
    question: str
    intent: str | None = None
    reply_text: str | None = None
    confirm_status: str | None = None
    action_type: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class PaginatedResponse(BaseModel):
    """分页响应"""
    items: list
    total: int
    page: int
    page_size: int
    pages: int
