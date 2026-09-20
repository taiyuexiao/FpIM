from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB

from ..core.database import Base


class RecommendationLog(Base):
    """业务推荐日志：一行一个被推荐人（P2 收口写入）"""
    __tablename__ = "recommendation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(String(32), ForeignKey("messages.id"), nullable=True, index=True)
    session_id = Column(String(32), ForeignKey("sessions.id"), nullable=True, index=True)
    user_id = Column(String(32), ForeignKey("user2.id"), nullable=False, index=True)  # 提问人
    query_text = Column(Text, nullable=False)
    person_id = Column(String(32), ForeignKey("user2.id"), nullable=False, index=True)  # 被推荐人
    rank = Column(Integer, nullable=False)
    score = Column(Integer, nullable=False)
    reasons = Column(JSONB, default=[])  # [{kind, text}] 命中依据
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Feedback(Base):
    """内容/回答/人员维度的轻量赞踩（P2 收口写入）"""
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(32), ForeignKey("user2.id"), nullable=False, index=True)
    target_type = Column(String(32), nullable=False)  # answer | person | content
    target_key = Column(String(256), nullable=False)  # e.g. 'answer:turn-xxx'
    value = Column(String(8), nullable=False)  # up | down
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
