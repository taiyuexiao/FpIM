"""收信:IMAP 轮询收件箱 → 关联问题 → LLM 分析回信 → 落库。

设计要点:
- 只处理未读邮件,处理后标记已读(不会重复处理,幂等);
- 关联优先级:In-Reply-To → 我们发出的邮件 Message-ID;其次主题里的 `#ISSUE-<id>` 标记;
- 收到回信后:问题状态推进到「处理中」(已解决的除外),同时把 LLM 的判断
  (是否切题/是否已解决/建议状态)写进邮件记录与时间线,**由用户在「我的问题」里确认最终状态**
  —— 机器只提议,不自动下结论。
"""
from __future__ import annotations

import asyncio
import imaplib
import logging
import re
import ssl
from datetime import datetime, timezone
from email import message_from_bytes
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime

from sqlalchemy import text

from ..core.config import settings
from ..core.database import SessionLocal
from ..models.issue import Issue, IssueEvent, MailMessage
from . import llm

logger = logging.getLogger("mail_inbox")

ISSUE_TOKEN_RE = re.compile(r"#ISSUE-(\d+)")

# 163 要求登录后发 ID 命令,否则报 Unsafe Login
imaplib.Commands["ID"] = ("AUTH", "SELECTED")

_QUOTE_CUT = re.compile(r"\n(-{2,}\s*原始邮件|在\s*\d{4}年.*写道|发件人[:：]|From:)", re.S)


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _body_text(msg) -> str:
    """取纯文本正文;只有 HTML 时粗暴去掉标签。"""
    text_part, html_part = None, None
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if part.get("Content-Disposition", "").startswith("attachment"):
                continue
            if ctype == "text/plain" and text_part is None:
                text_part = part
            elif ctype == "text/html" and html_part is None:
                html_part = part
    else:
        return _part_text(msg) if msg.get_content_type() == "text/plain" else _strip_html(_part_text(msg))
    if text_part is not None:
        return _part_text(text_part)
    if html_part is not None:
        return _strip_html(_part_text(html_part))
    return ""


def _part_text(part) -> str:
    try:
        payload = part.get_payload(decode=True)
    except Exception:
        return ""
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", "", html or "")
    text = re.sub(r"(?s)<br\s*/?>|</p>", "\n", text)
    return re.sub(r"(?s)<[^>]+>", "", text).strip()


def _clean_reply(body: str) -> str:
    """去掉引用的原文,只留本次回复内容(能切则切,切不动就保留)。"""
    body = (body or "").strip()
    if not body:
        return ""
    cut = _QUOTE_CUT.search(body)
    if cut and cut.start() > 20:
        body = body[: cut.start()]
    return body.strip()


def analyze_reply(question: str, sent_body: str, reply_body: str) -> dict:
    """LLM 判断回信:是否切题、是否意味着问题已解决、建议状态。失败降级为保守判断。"""
    fallback = {
        "reply_relevant": True,
        "seems_resolved": False,
        "suggested_status": "processing",
        "summary": (reply_body or "")[:80],
        "degraded": True,
    }
    if not settings.DEEPSEEK_API_KEY or not (reply_body or "").strip():
        return fallback
    prompt = (
        "你是银行内部「首问必答平台」的邮件助手。用户就一个问题联系了负责人并收到回信,"
        "现在判断这封回信的含义。\n\n"
        f"【用户的问题】{question[:500]}\n"
        f"【平台代发的邮件】{(sent_body or '')[:500]}\n"
        f"【收到的回信】{reply_body[:1200]}\n\n"
        "请判断:\n"
        "1) reply_relevant:回信是否在回应这个问题(自动回复/退信/无关内容 → false);\n"
        "2) seems_resolved:从回信看,问题是否已经获得答复/解决;\n"
        "3) suggested_status:not_contacted / processing / resolved / unresolved 选一个;\n"
        "4) summary:一句话概括回信要点。\n\n"
        '只输出 JSON:{"reply_relevant": true, "seems_resolved": false, '
        '"suggested_status": "processing", "summary": "..."}'
    )
    try:
        content = llm.chat(
            [{"role": "system", "content": "你是严谨的邮件意图判断助手,只输出 JSON。"},
             {"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=400,
        )
        t = (content or "").strip()
        if t.startswith("```"):
            t = t.split("\n", 1)[1] if "\n" in t else t
            if t.rstrip().endswith("```"):
                t = t.rstrip()[:-3]
        import json as _json
        data = _json.loads(t.strip())
        status = str(data.get("suggested_status") or "processing").strip()
        if status not in ("not_contacted", "processing", "resolved", "unresolved"):
            status = "processing"
        return {
            "reply_relevant": bool(data.get("reply_relevant", True)),
            "seems_resolved": bool(data.get("seems_resolved")),
            "suggested_status": status,
            "summary": str(data.get("summary") or "")[:300],
        }
    except Exception as exc:  # LLM 不可用不阻断收信
        logger.warning("回信分析降级: %s", exc)
        return fallback


def match_issue_id(db, in_reply_to: str, subject: str) -> int | None:
    """按 In-Reply-To(我们发出的邮件)优先,其次主题里的 #ISSUE-<id> 关联问题。"""
    if in_reply_to:
        row = db.execute(
            text("SELECT issue_id FROM public.mail_messages "
                 "WHERE direction='out' AND message_id=:mid AND issue_id IS NOT NULL LIMIT 1"),
            {"mid": in_reply_to.strip()},
        ).fetchone()
        if row:
            return int(row[0])
    m = ISSUE_TOKEN_RE.search(subject or "")
    if m:
        issue = db.query(Issue).filter(Issue.id == int(m.group(1))).first()
        if issue:
            return issue.id
    return None


def process_inbound(db, raw: bytes) -> dict | None:
    """处理一封收到的邮件:去重 → 关联问题 → LLM 分析 → 落库。返回处理摘要(已存在则 None)。"""
    msg = message_from_bytes(raw)
    message_id = (msg.get("Message-ID") or "").strip()
    if message_id:
        exists = db.execute(
            text("SELECT 1 FROM public.mail_messages WHERE direction='in' AND message_id=:m"),
            {"m": message_id},
        ).fetchone()
        if exists:
            return None

    from_addr = parseaddr(msg.get("From") or "")[1]
    subject = _decode(msg.get("Subject"))
    in_reply_to = (msg.get("In-Reply-To") or "").strip()
    body = _clean_reply(_body_text(msg))
    try:
        received_at = parsedate_to_datetime(msg.get("Date"))
    except Exception:
        received_at = datetime.now(timezone.utc)

    issue_id = match_issue_id(db, in_reply_to, subject)
    analysis = None
    if issue_id:
        issue = db.query(Issue).filter(Issue.id == issue_id).first()
        sent = db.execute(
            text("SELECT body_text FROM public.mail_messages WHERE direction='out' "
                 "AND issue_id=:i ORDER BY id DESC LIMIT 1"), {"i": issue_id},
        ).fetchone()
        analysis = analyze_reply(
            question=issue.summary or issue.question if issue else "",
            sent_body=(sent[0] if sent else "") or "",
            reply_body=body,
        )

    record = MailMessage(
        direction="in",
        message_id=message_id or None,
        in_reply_to=in_reply_to or None,
        from_addr=from_addr,
        to_addr=parseaddr(msg.get("To") or "")[1],
        subject=subject,
        body_text=body,
        issue_id=issue_id,
        analysis=analysis,
        received_at=received_at,
    )
    db.add(record)

    status_after = None
    if issue_id:
        issue = db.query(Issue).filter(Issue.id == issue_id).first()
        if issue:
            if issue.status != "resolved":
                issue.status = "processing"
                issue.last_action_at = datetime.now(timezone.utc)
            status_after = issue.status
            db.add(IssueEvent(
                issue_id=issue.id,
                event_type="mail_received",
                detail=f"收到 {from_addr or '对方'} 的回信",
                payload={"subject": subject, "analysis": analysis, "statusAfter": status_after},
                operator_id=None,
            ))
    db.commit()
    return {
        "issueId": issue_id,
        "from": from_addr,
        "subject": subject,
        "analysis": analysis,
        "statusAfter": status_after,
    }


def _poll_once() -> int:
    """同步拉取一次未读邮件(在线程里跑)。返回处理封数。

    只处理「能关联到问题」的回信(In-Reply-To 或主题 #ISSUE 标记):
    这类邮件处理后标记已读;其它未读邮件一律不动(不标已读、不入库),
    避免把邮箱里的私人邮件吞掉——平台只关心与自己发出的问题相关的回信。
    """
    if not settings.IMAP_USER or not settings.IMAP_PASSWORD:
        return 0
    handled = 0
    db = SessionLocal()
    try:
        ctx = ssl.create_default_context()
        M = imaplib.IMAP4_SSL(settings.IMAP_HOST, settings.IMAP_PORT, ssl_context=ctx, timeout=30)
        try:
            M.login(settings.IMAP_USER, settings.IMAP_PASSWORD)
            try:
                M._simple_command("ID", '("name" "swzr-backend" "version" "1.0" "vendor" "bosc")')
            except Exception:
                pass
            M.select("INBOX")
            typ, data = M.search(None, "UNSEEN")
            for num in (data[0].split() if data and data[0] else []):
                try:
                    typ, head_data = M.fetch(num, "(BODY.PEEK[HEADER])")
                    if not head_data or not isinstance(head_data[0], tuple):
                        continue
                    head = message_from_bytes(head_data[0][1])
                    in_reply_to = (head.get("In-Reply-To") or "").strip()
                    subject = _decode(head.get("Subject"))
                    if match_issue_id(db, in_reply_to, subject) is None:
                        continue  # 与平台问题无关的邮件:不处理也不标已读

                    typ, msg_data = M.fetch(num, "(RFC822)")
                    raw = msg_data[0][1]
                    result = process_inbound(db, raw)
                    if result:
                        handled += 1
                        logger.info("收到回信(问题 #%s): %s", result.get("issueId"), result.get("subject"))
                    M.store(num, "+FLAGS", "\\Seen")
                except Exception as exc:
                    db.rollback()
                    logger.warning("处理邮件失败: %s", exc)
        finally:
            try:
                M.logout()
            except Exception:
                pass
    except Exception as exc:
        logger.warning("IMAP 轮询失败: %s", exc)
    finally:
        db.close()
    return handled


async def run_mail_poller(stop_event: asyncio.Event) -> None:
    """后台轮询:每 MAIL_POLL_SECONDS 秒收一次信(0 表示关闭)。"""
    interval = max(10, int(settings.MAIL_POLL_SECONDS or 0))
    if not settings.IMAP_USER or not settings.IMAP_PASSWORD or not settings.MAIL_POLL_SECONDS:
        logger.info("收信未启用(缺少 IMAP 配置或 MAIL_POLL_SECONDS=0)")
        return
    logger.info("收信轮询启动: %s@%s 每 %ss 一次", settings.IMAP_USER, settings.IMAP_HOST, interval)
    while not stop_event.is_set():
        try:
            await asyncio.to_thread(_poll_once)
        except Exception as exc:
            logger.warning("收信轮询异常: %s", exc)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
