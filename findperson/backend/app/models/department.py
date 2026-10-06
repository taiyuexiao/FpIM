from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from ..core.database import Base


class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False)
    level = Column(Integer, nullable=False)
    parent_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    leader_id = Column(String(32), ForeignKey("user2.id"), nullable=True)
    responsibility = Column(Text, nullable=True)
    status = Column(String(16), default="active")
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # 与 users 存在两条 FK 路径(users.department_id / leader_id),显式指定 members 走 department_id
    members = relationship("User", back_populates="department", lazy="dynamic",
                           foreign_keys="User.department_id")
    children = relationship("Department", backref="parent", remote_side=[id], lazy="joined")
