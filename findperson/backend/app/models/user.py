import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from ..core.database import Base


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class User(Base):
    __tablename__ = "user2"

    id = Column(String(32), primary_key=True, default=_new_id)
    account = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(64), nullable=False)
    password_hash = Column(String(256), nullable=False)
    phone = Column(String(20), nullable=True)
    email = Column(String(128), nullable=True)  # 行内邮箱(xxx@bosc.cn),邮件功能收件地址
    system_role = Column(String(32), nullable=False, default="普通成员")  # 管理员 / 普通成员
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    role = Column(String(128), nullable=True)
    contact = Column(String(64), nullable=True)
    domains = Column(JSONB, nullable=True)
    self_portrait = Column(Text, nullable=True)
    manager_id = Column(String(32), nullable=True)  # 直接上级(users 自引用,树状汇报关系)
    completeness = Column(Integer, default=0)
    recommended_count = Column(Integer, default=0)
    active = Column(Boolean, default=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # 与 departments 存在两条 FK 路径(department_id / departments.leader_id),必须显式指定
    department = relationship("Department", back_populates="members", lazy="joined",
                              foreign_keys=[department_id])
    contents = relationship("Content", back_populates="owner", lazy="dynamic")
    sent_reviews = relationship("PeerReview", back_populates="reviewer_user", lazy="dynamic",
                                foreign_keys="PeerReview.reviewer_id")
    received_reviews = relationship("PeerReview", back_populates="person_user", lazy="dynamic",
                                    foreign_keys="PeerReview.person_id")
