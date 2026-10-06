"""邮件:智能体(DeepSeek)按推荐上下文代拟草稿 + SMTP 发送 + 与问题跟踪联动。"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...core.config import settings
from ...core.database import get_db
from ...middleware.deps import get_current_user
from ...models.issue import Issue, IssueEvent, MailMessage
from ...models.user import User
from ...services import llm, mailer

router = APIRouter(prefix="/mail", tags=["邮件"])


class MailDraftRequest(BaseModel):
    personId: str = Field(min_length=1)
    question: str = Field(default="", max_length=2000)


class MailSendRequest(BaseModel):
    to: str = Field(min_length=3, max_length=128)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20000)
    issueId: int | None = Field(default=None, ge=1)  # 关联的问题(发信后自动置「处理中」,回信按主题标记归档)


def _dept_name(user: User) -> str:
    return user.department.name if user.department else ""


def _surname(user: User) -> str:
    """姓氏(数据无复姓,取首字);称呼用「姓+老师」,不直呼全名。"""
    return (user.name or "")[:1]


def _strip_code_fence(text: str) -> str:
    """去掉 LLM 回复可能带的 ```json 围栏。"""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def _fallback_draft(person: User, question: str, sender_name: str) -> tuple[str, str]:
    """LLM 不可用时的通用模板草稿。"""
    subject = f"关于「{(question or '工作事项')[:30]}」的咨询"
    lead = (
        f"我在使用首问必答平台时了解到，您与以下事项相关：{question}。"
        if question else "有一项工作事项想向您咨询。"
    )
    body = (
        f"{_surname(person)}老师，您好：\n\n"
        f"{lead}\n"
        "想请您在方便时给予指导或协助，如需进一步沟通可随时联系我。\n\n"
        f"谢谢！\n\n{sender_name}"
    )
    return subject, body


@router.post("/draft", summary="Draft Mail", description="智能体按问题上下文代拟邮件草稿(DeepSeek,失败降级模板)")
def draft_mail(body: MailDraftRequest, request: Request, db: Session = Depends(get_db)):
    sender = get_current_user(request, db)
    person = db.query(User).filter(User.id == body.personId).first()
    if not person:
        raise HTTPException(status_code=404, detail="人员不存在")
    if not person.email:
        raise HTTPException(status_code=400, detail="该人员未配置邮箱，无法发送")

    fallback = False
    try:
        context_hint = (
            f"用户的问题/需求：{body.question}\n"
            if body.question else "用户暂无具体问题描述（可能是从名片库直接发起）。\n"
        )
        prompt = (
            "你是银行内部平台「首问必答平台」的邮件助手。平台刚才向用户推荐了一位负责人，"
            "用户现在想给这位负责人发一封内部工作邮件。\n\n"
            f"{context_hint}"
            f"收件人：{person.name}（{_dept_name(person)} {person.role or ''}）\n"
            f"发件人：{sender.name}（{_dept_name(sender)} {sender.role or ''}）\n\n"
            "请以发件人口吻写这封邮件：开头称呼收件人，格式必须是「姓氏+老师」（例如收件人"
            f"{person.name}，称呼「{_surname(person)}老师」），不得直呼全名；"
            "说明来意（结合用户问题转述需求，不要编造事实）；"
            "礼貌请求对方协助或指导；结尾致谢并署发件人姓名。\n"
            "正文 150 字以内，语气专业简洁。\n"
            '只输出 JSON：{"subject": "邮件主题", "body": "邮件正文"}，正文中的换行用 \\n 表示。'
        )
        content = llm.chat(
            [{"role": "system", "content": "你是银行内部邮件撰写助手，只输出 JSON。"},
             {"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=512,
        )
        data = json.loads(_strip_code_fence(content))
        subject = str(data.get("subject", "")).strip()
        mail_body = str(data.get("body", "")).strip()
        if not subject or not mail_body:
            raise ValueError("subject/body 为空")
    except Exception:
        fallback = True
        subject, mail_body = _fallback_draft(person, body.question, sender.name)

    return {"to": person.email, "personName": person.name, "subject": subject, "body": mail_body, "fallback": fallback}


@router.post("/send", summary="Send Mail", description="发送邮件(SMTP 中继投递);可关联问题,发出即置「处理中」并记录时间线")
def send_mail(body: MailSendRequest, request: Request, db: Session = Depends(get_db)):
    sender = get_current_user(request, db)
    to = body.to.strip()
    if "@" not in to:
        raise HTTPException(status_code=400, detail="收件邮箱格式不正确")

    issue = None
    subject = body.subject.strip()
    if body.issueId:
        issue = db.query(Issue).filter(Issue.id == body.issueId).first()
        if not issue:
            raise HTTPException(status_code=404, detail="关联的问题不存在")
        if issue.user_id != sender.id:
            raise HTTPException(status_code=403, detail="只能给自己的问题发信")
        # 主题带问题标记:对方直接回复时,回信可按主题自动归到这个问题上
        subject = f"{subject} #ISSUE-{issue.id}"

    try:
        message_id = mailer.send(to, subject, body.body)
    except mailer.MailSendError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    db.add(MailMessage(direction="out", message_id=message_id, from_addr=settings.SMTP_USER,
                       to_addr=to, subject=subject, body_text=body.body,
                       issue_id=issue.id if issue else None, sent_by=sender.id))
    if issue:
        if issue.status in ("not_contacted", "unresolved"):
            issue.status = "processing"
        issue.last_action_at = datetime.now(timezone.utc)
        db.add(IssueEvent(issue_id=issue.id, event_type="mail_sent", operator_id=sender.id,
                          detail=f"已发邮件给 {to}", payload={"subject": subject, "messageId": message_id}))
    db.commit()
    return {"ok": True, "to": to, "messageId": message_id, "issueId": issue.id if issue else None}
