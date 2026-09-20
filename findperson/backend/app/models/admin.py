"""管理后台支撑表：统计口径 / 统计结果 / 操作审计日志（P3 ADM-05/06）"""
from datetime import datetime, timezone, date

from sqlalchemy import Column, Integer, String, Text, Date, DateTime, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB

from ..core.database import Base


class StatisticsDefinition(Base):
    """统计口径定义（P0 已建表，P3 读取用于定时刷新）"""
    __tablename__ = "statistics_definitions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    metric_key = Column(String(64), unique=True, nullable=False)
    metric_name = Column(String(64), nullable=False)
    metric_category = Column(String(32), default="admin")
    formula = Column(Text, nullable=True)       # 统计口径 SQL（仅允许 SELECT）
    unit = Column(String(16), default="次")
    refresh_cron = Column(String(32), nullable=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class StatisticsData(Base):
    """统计结果数据（定时任务刷新写入）"""
    __tablename__ = "statistics_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    metric_key = Column(String(64), nullable=False, index=True)
    value = Column(Numeric(20, 4), nullable=True)
    dimension = Column(String(64), nullable=True)
    stat_date = Column(Date, default=date.today, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class AuditLog(Base):
    """操作审计日志（P3 ADM-06，审计中间件写入）"""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(32), ForeignKey("user2.id"), nullable=True, index=True)
    action = Column(String(64), nullable=False)       # create / update / delete / audit / login ...
    resource_type = Column(String(64), nullable=True)  # content / user / review / session ...
    resource_id = Column(String(64), nullable=True)
    method = Column(String(16), nullable=True)         # POST / PUT / PATCH / DELETE
    path = Column(String(256), nullable=True)
    detail = Column(JSONB, nullable=True)
    ip = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
