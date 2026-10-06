"""私聊代理（二期 R2，必须需求 #2）。

模式：off=关闭 | draft=仅起草（建议发给本人） | auto=自动处理（未读期间自主代答）。
触发：对方消息在「未读」状态（seq > 委托人 last_read_seq）→ 等待窗口（5s 可调）
→ 委托人已读则撤销，否则评估：知识命中则代答/起草，命中不了保持沉默或交接。
红线：禁止"用户没看到请稍后"式废话回复——无把握时沉默或交接（附件 §6）。
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from .agent_knowledge import answer_with_llm, find_owner_knowledge
from . import im as im_service

logger = logging.getLogger(__name__)

WAIT_SECONDS = 5.0  # 未读等待窗口（产品可调参数，附件 §6.2 初值）

QUESTION_MARKERS = ("吗", "怎么", "如何", "什么", "哪", "能否", "可以", "多少", "为什么", "?", "？")


def get_delegation(db: Session, conv_id: int) -> dict | None:
    row = db.execute(text(
        "SELECT conversation_id, owner_person_id, mode, updated_at "
        "FROM public.agent_delegations WHERE conversation_id=:cid"
    ), {"cid": conv_id}).fetchone()
    if not row:
        return None
    return {"conversationId": row[0], "ownerId": row[1], "mode": row[2],
            "updatedAt": row[3].isoformat() if row[3] else None}


def set_delegation(db: Session, conv_id: int, user_id: str, mode: str) -> dict:
    """设置委托（仅会话成员；切片 1：一个会话一个委托人=设置者本人）。"""
    if mode not in ("off", "draft", "auto"):
        raise ValueError("mode 取值不合法")
    member = db.execute(text(
        "SELECT 1 FROM im.conversation_members WHERE conversation_id=:cid AND user_id=:uid AND left_at IS NULL"
    ), {"cid": conv_id, "uid": user_id}).fetchone()
    if not member:
        raise PermissionError("不是该会话成员")
    conv = db.execute(text(
        "SELECT type FROM im.conversations WHERE id=:cid"
    ), {"cid": conv_id}).fetchone()
    if not conv or conv[0] != "direct":
        raise ValueError("切片仅支持单聊代理")
    db.execute(text(
        """
        INSERT INTO public.agent_delegations (conversation_id, owner_person_id, mode)
        VALUES (:cid, :uid, :mode)
        ON CONFLICT (conversation_id) DO UPDATE
           SET mode = EXCLUDED.mode, owner_person_id = EXCLUDED.owner_person_id, updated_at = now()
        """
    ), {"cid": conv_id, "uid": user_id, "mode": mode})
    db.commit()
    return get_delegation(db, conv_id) or {}


def handle_direct_message(db: Session, message: dict[str, Any]) -> None:
    """私聊消息到达：委托生效且委托人未读 → 后台线程进入等待窗口（不阻塞发送主链）。"""
    conv_id = int(message.get("conversationId") or message.get("conversation_id") or 0)
    sender = message.get("senderId") or message.get("sender_id") or ""
    row = db.execute(text(
        """
        SELECT d.mode, d.owner_person_id, m.last_read_seq, u.name
          FROM public.agent_delegations d
          JOIN im.conversation_members m
            ON m.conversation_id = d.conversation_id AND m.user_id = d.owner_person_id
          LEFT JOIN public.user2 u ON u.id = d.owner_person_id
         WHERE d.conversation_id = :cid AND d.mode <> 'off'
        """
    ), {"cid": conv_id}).fetchone()
    if not row:
        return
    mode, owner, last_read, owner_name = row
    if sender == owner:
        return  # 委托人自己发的
    if (message.get("seq") or 0) <= (last_read or 0):
        return  # 已读过的不代理
    threading.Thread(
        target=_evaluate_later,
        args=(conv_id, owner, owner_name or owner, sender, mode, dict(message)),
        daemon=True,
    ).start()


def _evaluate_later(conv_id: int, owner: str, owner_name: str, sender: str,
                    mode: str, message: dict[str, Any]) -> None:
    from ..core.database import SessionLocal

    time.sleep(WAIT_SECONDS)
    db = SessionLocal()
    try:
        # 等待窗口内委托人已读 → 撤销自动处理（附件 §6.2）
        read_row = db.execute(text(
            "SELECT last_read_seq FROM im.conversation_members "
            "WHERE conversation_id=:cid AND user_id=:uid"
        ), {"cid": conv_id, "uid": owner}).fetchone()
        if (read_row and read_row[0] or 0) >= (message.get("seq") or 0):
            return

        text_body = str((message.get("content") or {}).get("text") or "")
        hits = find_owner_knowledge(db, owner, text_body)
        sender_name_row = db.execute(text(
            "SELECT name FROM public.user2 WHERE id=:uid"), {"uid": sender}).fetchone()
        sender_name = (sender_name_row[0] if sender_name_row else sender)

        if hits and mode == "auto":
            answer = answer_with_llm(text_body, hits)
            content = {
                "text": answer,
                "automation": {
                    "by": "agent", "principalId": owner, "principalName": owner_name,
                    "knowledge": [{"id": h["id"], "title": h["title"]} for h in hits],
                },
            }
            msg, _ = im_service.send_message(
                db, conv_id, owner, "text", content,
                client_msg_id=f"proxy:{message.get('id') or message.get('seq')}")
            from ..ws.im_gateway import broadcast_message_sync
            broadcast_message_sync(conv_id, msg)
            return

        if hits and mode == "draft":
            im_service.notify_user(db, owner,
                f"【草稿·代你回复】{sender_name} 问：{text_body}\n"
                f"建议回复（我没有直接发送，请确认后手动回复）：\n{answer_with_llm(text_body, hits)}")
            return

        # 无把握 → 不说废话；像提问才交接通知本人
        if _looks_like_question(text_body):
            im_service.notify_user(db, owner,
                f"【代理交接】{sender_name} 问你：{text_body}\n"
                f"我的知识库覆盖不了这个问题，需要你亲自回复（我已停止自动处理）。")
    except Exception:  # noqa: BLE001
        logger.exception("私聊代理评估失败 conv=%s", conv_id)
    finally:
        db.close()


def _looks_like_question(text_body: str) -> bool:
    return any(m in text_body for m in QUESTION_MARKERS)
