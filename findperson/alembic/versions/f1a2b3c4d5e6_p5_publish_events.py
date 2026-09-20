"""p5 publish events: rag.publish_events

Revision ID: f1a2b3c4d5e6
Revises: c1d2e3f4a5b6
Create Date: 2026-08-14

P5 新增 rag.publish_events：内容发布/变更事件的落库信号表。
后端在内容「审核通过发布」「编辑已发布内容」「删除已发布内容」时写入一条事件，
RAG 服务（knowledge-service）消费后触发 generate-from-db + index 重新索引。
本表只做事件信号，不重复 RAG 的切片/向量/入库逻辑。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'publish_events',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('event_type', sa.Text(), nullable=False),   # content_published / content_changed / content_deleted
        sa.Column('resource_id', sa.Text(), nullable=False),  # 内容 id
        sa.Column('status', sa.Text(), nullable=False, server_default='pending'),  # pending / done / failed（RAG 消费方更新）
        sa.Column('created_by', sa.Text(), nullable=True),    # 触发人 user.id
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        schema='rag',
    )
    op.create_index('ix_publish_events_status', 'publish_events', ['status'], schema='rag')


def downgrade() -> None:
    op.drop_index('ix_publish_events_status', table_name='publish_events', schema='rag')
    op.drop_table('publish_events', schema='rag')
