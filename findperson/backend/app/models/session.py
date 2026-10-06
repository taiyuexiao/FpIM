import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship

from ..core.database import Base


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex[:12])
    user_id = Column(String(32), ForeignKey("user2.id"), nullable=False, index=True)
    title = Column(String(256), default="新会话")
    summary = Column(Text, default="")
    turn_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    messages = relationship("Message", back_populates="session", lazy="dynamic",
                            order_by="Message.created_at")


class Message(Base):
    __tablename__ = "messages"

    id = Column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex[:12])
    session_id = Column(String(32), ForeignKey("sessions.id"), nullable=False, index=True)
    user_id = Column(String(32), ForeignKey("user2.id"), nullable=False)
    question = Column(Text, nullable=False)
    intent = Column(String(64), nullable=True)
    reply_text = Column(Text, nullable=True)
    confirm_status = Column(String(16), nullable=True)
    action_type = Column(String(32), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    session = relationship("Session", back_populates="messages", lazy="joined")


class QueryLog(Base):
    """查询日志，用于管理看板活动趋势"""
    __tablename__ = "query_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(32), ForeignKey("user2.id"), nullable=True)
    query_type = Column(String(32), default="search")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
