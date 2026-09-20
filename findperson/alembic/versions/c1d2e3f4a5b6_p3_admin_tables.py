"""p3 admin tables: audit_logs + statistics_data

Revision ID: c1d2e3f4a5b6
Revises: 64c9fe23ca1b
Create Date: 2026-08-14

P3 新增两张 public 表：
- statistics_data：统计结果快照（ADM-05 定时刷新写入）
- audit_logs：操作审计日志（ADM-06 审计中间件写入）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = '64c9fe23ca1b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'statistics_data',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('metric_key', sa.String(64), nullable=False),
        sa.Column('value', sa.Numeric(20, 4), nullable=True),
        sa.Column('dimension', sa.String(64), nullable=True),
        sa.Column('stat_date', sa.Date(), nullable=False, server_default=sa.func.current_date()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema='public',
    )
    op.create_index('ix_statistics_data_metric_key', 'statistics_data', ['metric_key'],
                    schema='public')

    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.String(32), sa.ForeignKey('public.users.id'), nullable=True),
        sa.Column('action', sa.String(64), nullable=False),
        sa.Column('resource_type', sa.String(64), nullable=True),
        sa.Column('resource_id', sa.String(64), nullable=True),
        sa.Column('method', sa.String(16), nullable=True),
        sa.Column('path', sa.String(256), nullable=True),
        sa.Column('detail', postgresql.JSONB(), nullable=True),
        sa.Column('ip', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema='public',
    )
    op.create_index('ix_audit_logs_user_id', 'audit_logs', ['user_id'], schema='public')


def downgrade() -> None:
    op.drop_table('audit_logs', schema='public')
    op.drop_table('statistics_data', schema='public')
