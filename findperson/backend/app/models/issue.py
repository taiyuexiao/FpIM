"""问题跟踪 + 知识沉淀 + 邮件往来(后端业务表模型)。

链路:对话同步问题 → 邮件联系(发出/收回信) → LLM 分析 + 用户确认 → 沉淀候选 → FAQ。
DDL 见 agent-service/scripts/ddl/07_issues_knowledge.sql。
"""
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from ..core.database import Base


def _now():
    return datetime.now(timezone.utc)


class Issue(Base):
    """问题跟踪(个人中心「我的问题」)。状态:未联系/处理中/已解决/未解决。"""
    __tablename__ = "issues"

    id = Column(BigInteger, primary_key=True)
    user_id = Column(String(32), nullable=False)
    session_id = Column(String(64))
    message_id = Column(String(64))  # agent.agui_messages.message_id(用户消息)
    question = Column(Text, nullable=False)
    summary = Column(Text)  # LLM 归一化问题
    status = Column(String(16), nullable=False, default="not_contacted")
    assignee_person_id = Column(String(32))
    repeated_count = Column(Integer, nullable=False, default=1)
    source = Column(String(16), nullable=False, default="sync")
    last_action_at = Column(DateTime(timezone=True), default=_now)
    resolved_at = Column(DateTime(timezone=True))
    resolution_note = Column(Text)
    # ── IM 化新增（08_im.sql 里 ALTER TABLE 加的列，ORM 必须同步声明）──
    conversation_id = Column(BigInteger)            # 该问题在哪个会话里聊的
    first_read_at = Column(DateTime(timezone=True))      # 责任人首次看到（证据，不可覆盖）
    first_response_at = Column(DateTime(timezone=True))  # 责任人首次回复
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)


class IssueEvent(Base):
    """问题时间线(同步/改状态/发信/收信/分析/备注)。"""
    __tablename__ = "issue_events"

    id = Column(BigInteger, primary_key=True)
    issue_id = Column(BigInteger, nullable=False)
    event_type = Column(String(24), nullable=False)
    detail = Column(Text)
    payload = Column(JSONB)
    operator_id = Column(String(32))
    created_at = Column(DateTime(timezone=True), default=_now)


class MailMessage(Base):
    """邮件往来(out 发出 / in 收到),可与问题关联。"""
    __tablename__ = "mail_messages"

    id = Column(BigInteger, primary_key=True)
    direction = Column(String(4), nullable=False)
    message_id = Column(String(255))
    in_reply_to = Column(String(255))
    from_addr = Column(String(128))
    to_addr = Column(String(128))
    subject = Column(Text)
    body_text = Column(Text)
    issue_id = Column(BigInteger)
    sent_by = Column(String(32))
    analysis = Column(JSONB)  # LLM 对回信的分析
    received_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=_now)


class KnowledgeCandidate(Base):
    """知识沉淀候选池(问答 → 待确认 FAQ/文章)。"""
    __tablename__ = "knowledge_candidates"

    id = Column(BigInteger, primary_key=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    summary = Column(Text)
    score = Column(Integer, nullable=False, default=0)
    signals = Column(JSONB)
    status = Column(String(16), nullable=False, default="pending")
    source_issue_ids = Column(JSONB)
    target_faq_id = Column(BigInteger)
    target_content_id = Column(String(32))  # 确认成文章草稿时指向 contents.id(字符串,如 C00319)
    reviewed_by = Column(String(32))
    reviewed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)


class Faq(Base):
    """FAQ 知识条目(沉淀结果)。"""
    __tablename__ = "faqs"

    id = Column(BigInteger, primary_key=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    tags = Column(JSONB)
    owner_person_id = Column(String(32))
    scope_department_ids = Column(JSONB)
    source = Column(String(16))
    version = Column(Integer, nullable=False, default=1)
    status = Column(String(16), nullable=False, default="published")
    asked_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)
