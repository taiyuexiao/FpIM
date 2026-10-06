"""IM 即时通讯内核模型(独立 schema: im)。

与业务表的关系:
- 参与者统一为 public.user2.id(TEXT),与 issues.user_id / assignee_person_id 同源
- im.conversations.issue_id 锚定"主问题";一个会话可聊出多个问题(issues.conversation_id 反向指回)
- 消息与问题同库同事务 —— 报表口径恒等于聊天记录

DDL 单一来源: agent-service/scripts/ddl/08_im.sql
"""
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from ..core.database import Base


def _now():
    return datetime.now(timezone.utc)


class Conversation(Base):
    """会话(单聊 direct / 群聊 group)。单聊靠 direct_key 唯一索引天然去重,无需分布式锁。"""
    __tablename__ = "conversations"
    __table_args__ = {"schema": "im"}

    id = Column(BigInteger, primary_key=True)
    type = Column(Text, nullable=False)              # direct | group
    direct_key = Column(Text)                        # 两个 user_id 升序拼接;群聊为 NULL
    title = Column(Text)
    owner_id = Column(Text)
    created_by = Column(Text, nullable=False)
    issue_id = Column(BigInteger)                    # 主问题锚点
    last_seq = Column(BigInteger, nullable=False, default=0)
    last_message_id = Column(BigInteger)
    last_message_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)


class ConversationMember(Base):
    """会话成员 + 已读游标(供未读红点;可被覆盖,不作为留痕证据)。"""
    __tablename__ = "conversation_members"
    __table_args__ = {"schema": "im"}

    conversation_id = Column(BigInteger, primary_key=True)
    user_id = Column(String(32), primary_key=True)
    member_role = Column(Text, nullable=False, default="member")   # owner | member
    last_read_seq = Column(BigInteger, nullable=False, default=0)
    last_read_at = Column(DateTime(timezone=True))
    unread_count = Column(Integer, nullable=False, default=0)
    muted = Column(Boolean, nullable=False, default=False)
    pinned = Column(Boolean, nullable=False, default=False)
    joined_at = Column(DateTime(timezone=True), default=_now)
    left_at = Column(DateTime(timezone=True))


class Message(Base):
    """消息。seq 为会话内严格递增序号,是排序与增量拉取的唯一依据。"""
    __tablename__ = "messages"
    __table_args__ = {"schema": "im"}

    id = Column(BigInteger, primary_key=True)
    conversation_id = Column(BigInteger, nullable=False)
    seq = Column(BigInteger, nullable=False)
    sender_id = Column(String(32), nullable=False)
    msg_type = Column(Text, nullable=False)          # text|image|file|audio|video|system|issue_card|resolve_confirm|report_card
    content = Column(JSONB, nullable=False, default=dict)
    client_msg_id = Column(String(64))               # 幂等键
    reply_to_id = Column(BigInteger)
    issue_id = Column(BigInteger)
    revoked = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=_now)


class Attachment(Base):
    """附件元数据(内容寻址;物理文件落在本地磁盘 /data/fpim/files)。"""
    __tablename__ = "attachments"
    __table_args__ = {"schema": "im"}

    id = Column(BigInteger, primary_key=True)
    sha256 = Column(Text, nullable=False)
    ext = Column(Text)
    mime = Column(Text)
    size_bytes = Column(BigInteger, nullable=False, default=0)
    original_name = Column(Text)
    rel_path = Column(Text, nullable=False)
    uploader_id = Column(String(32))
    ref_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_now)
