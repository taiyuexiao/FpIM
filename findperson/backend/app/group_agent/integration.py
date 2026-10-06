"""FpIM 群聊事件桥接。

`im_service.send_message` 在消息落库后调用本模块；群聊里的 @Agent / `/agent`
消息会进入通用 GroupAgentService，回复再由 FpIMReplySink 写回同一会话。
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.config import settings
from ..services import im as im_service
from .adapters import FpIMActionExecutor, FpIMReplySink, GROUP_AGENT_ID
from .contracts import ContextMessage, GroupAgentEvent
from .service import GroupAgentService, build_brain

logger = logging.getLogger(__name__)

_service: GroupAgentService | None = None


def get_service() -> GroupAgentService:
    global _service
    if _service is None:
        from ..agent_tools import make_tool_executor
        _service = GroupAgentService(
            brain=build_brain(
                settings.AGENT_SERVICE_URL,
                use_agent_service=settings.GROUP_AGENT_USE_AGENT_SERVICE,
                timeout_seconds=settings.GROUP_AGENT_BRAIN_TIMEOUT_SECONDS,
                tool_executor=make_tool_executor(),
            ),
            reply_sink=FpIMReplySink(),
            action_executor=FpIMActionExecutor(),
        )
    return _service


def reset_service_for_tests(service: GroupAgentService | None = None) -> None:
    global _service
    _service = service


def _load_context(db: Session, conversation_id: int, limit: int = 20) -> list[ContextMessage]:
    rows = db.execute(text(
        """
        SELECT sender_id, msg_type, content, created_at
          FROM im.messages
         WHERE conversation_id = :cid
         ORDER BY seq DESC
         LIMIT :limit
        """
    ), {"cid": conversation_id, "limit": limit}).fetchall()
    result: list[ContextMessage] = []
    for sender_id, msg_type, content, created_at in reversed(rows):
        payload = content or {}
        message_text = str(payload.get("text") or payload.get("summary") or "")
        if not message_text:
            continue
        result.append(ContextMessage(
            sender_id=sender_id,
            sender_name="群聊 Agent" if sender_id == GROUP_AGENT_ID else None,
            text=message_text,
            created_at=created_at.isoformat() if created_at else None,
            metadata={"messageType": msg_type},
        ))
    return result


def _try_mention_human(db: Session, m: dict[str, Any], text_body: str) -> dict[str, Any] | None:
    """@了群里的真人（不是 @Agent）：其 Agent 必有响应——代答或实质交接。

    - 命中该成员的知识库（无需分享授权：是回答"被问到 TA 的问题"）→ LLM 代答并署名
    - 未命中且像提问 → 交接确认 + 小管家提醒 TA 亲自回复（不装死、不说废话）
    - 普通 @（非提问）→ 静默，避免刷屏
    """
    from .adapters import GROUP_AGENT_ID  # noqa: F401  (保持命名一致)
    from ..services.agent_knowledge import answer_with_llm, find_owner_knowledge
    from ..services.agent_proxy import _looks_like_question

    members = db.execute(text(
        "SELECT user_id FROM im.conversation_members WHERE conversation_id=:cid AND left_at IS NULL"
    ), {"cid": m["conversationId"]}).fetchall()
    people = db.execute(text(
        "SELECT id, name FROM public.user2 WHERE id = ANY(:ids)"
    ), {"ids": [r[0] for r in members]}).fetchall()
    mentioned = [(pid, name) for pid, name in people if name and f"@{name}" in text_body]
    if not mentioned:
        return None
    pid, name = mentioned[0]
    hits = find_owner_knowledge(db, pid, text_body)
    if hits:
        answer = answer_with_llm(text_body, hits)
        text_reply = f"【{name} 的知识库·代答】\n{answer}"
    elif _looks_like_question(text_body):
        text_reply = (f"我代 {name} 收到了这个问题，但 TA 的知识库暂未覆盖，"
                     f"已提醒 TA 亲自回复你。")
    else:
        return None
    try:
        _send_and_broadcast(db, int(m["conversationId"]),
            {"text": text_reply, "agent": {"name": "群聊 Agent", "kind": "mention"}},
            f"mention:{m['id'] or m['seq']}")
    except Exception:  # noqa: BLE001
        logger.exception("提及响应发送失败")
        return None
    # 未命中知识的提问 → 小管家提醒被 @ 的人
    if not hits:
        try:
            from ..services import im as _im
            asker = db.execute(text("SELECT name FROM public.user2 WHERE id=:uid"),
                               {"uid": m["senderId"]}).fetchone()
            _im.notify_user(db, pid,
                f"【有人在会话里问你】{(asker[0] if asker else m['senderId'])}：{text_body}\n"
                f"我的知识库覆盖不了，请你亲自回复。")
        except Exception:  # noqa: BLE001
            logger.exception("提醒被@人失败")
    return {"handled": True, "reason": "mention-human", "runId": f"mention-{m['id']}",
            "traceId": f"mention-{m['id']}",
            "replies": [{"text": text_reply, "kind": "text"}], "actions": []}


def _is_bare_summon(text_body: str) -> bool:
    """只有触发词、没有正文（🤖 召唤 / 纯 @）。大小写/空格不敏感。"""
    import re as _re
    stripped = _re.sub(r"@(群聊\s*agent|agent|小管家)", " ", text_body, flags=_re.IGNORECASE)
    stripped = _re.sub(r"/(agent|ask)", " ", stripped, flags=_re.IGNORECASE)
    return not stripped.strip(" ，,。.！!？?～~@")


def _try_knowledge_answer(db: Session, message: dict[str, Any], text_body: str):
    """命中知识库且满足触发条件时直接代答；返回结果或 None（走原有 @Agent 流程）。

    触发：@知识库主人（其被问）或 @Agent/命令；披露检查在 find_relevant_knowledge 内完成。
    """
    if not text_body:
        return None
    from .adapters import GROUP_AGENT_ID  # 延迟导入防循环
    from ..services.agent_knowledge import answer_with_llm, find_relevant_knowledge

    hits = find_relevant_knowledge(db, int(_norm(message)["conversationId"] or 0), text_body)
    if not hits:
        return None
    owner_mentioned = any(f"@{h['ownerName']}" in text_body for h in hits if h.get("ownerName"))
    agent_trigger = any(t in text_body for t in ("@agent", "@小管家", "@群聊 Agent", "/agent", "/ask"))
    if not (owner_mentioned or agent_trigger):
        return None   # 命中知识但没人问 → 保持安静（附件 §5.2 抑制自动发言）

    answer = answer_with_llm(text_body, hits)
    try:
        _send_and_broadcast(db, int(_norm(message)["conversationId"]),
            {"text": answer, "agent": {"name": "知识库代答", "kind": "knowledge"},
             "knowledge": [{"id": h["id"], "title": h["title"], "ownerName": h["ownerName"]} for h in hits]},
            f"kb:{message.get('id') or message.get('seq')}")
    except Exception:  # noqa: BLE001 - 代答失败不影响用户消息
        logger.exception("知识库代答发送失败")
        return None
    return {
        "handled": True,
        "reason": "knowledge",
        "runId": f"kb-{message.get('id')}",
        "traceId": f"kb-{message.get('id')}",
        "replies": [{"text": answer, "kind": "text"}],
        "actions": [],
    }


def _send_and_broadcast(db: Session, conv_id: int, content: dict,
                        client_msg_id: str | None = None) -> dict:
    """Agent 回复统一出口：落库 + WS 广播。

    BUG 教训（im-frontend.md BUG-005）：问候/知识/提及/工具四条回复路径此前
    只落库不广播，用户页面收不到实时推送（"刷新才见"）。所有 Agent 发送必须走这里。
    """
    from ..ws.im_gateway import broadcast_message_sync

    msg, _ = im_service.send_message(db, conv_id, GROUP_AGENT_ID, "text", content,
                                     client_msg_id, None, None)
    broadcast_message_sync(conv_id, msg)
    return msg


def _norm(message: dict[str, Any]) -> dict[str, Any]:
    """消息字典是驼峰（_msg_dict_from_row），旧桥接读蛇形——统一规范化。

    BUG 记录见 group-agent.md：MVP 起桥接守卫读 message.get("msg_type") 恒为 None，
    导致整条群 Agent 链路从未触发；此处统一两种键名，防再犯。
    """
    return {
        "id": message.get("id"),
        "seq": message.get("seq"),
        "conversationId": message.get("conversationId") or message.get("conversation_id"),
        "senderId": message.get("senderId") or message.get("sender_id"),
        "msgType": message.get("msgType") or message.get("msg_type"),
        "content": message.get("content") or {},
    }


def handle_im_message(db: Session, message: dict[str, Any]) -> dict[str, Any] | None:
    """处理当前 FpIM 的一条普通消息；返回 Agent 结果或 None。"""
    m = _norm(message)
    if m["senderId"] == GROUP_AGENT_ID or m["msgType"] != "text":
        return None
    row = db.execute(text(
        "SELECT type FROM im.conversations WHERE id = :cid"
    ), {"cid": m["conversationId"]}).fetchone()
    if not row:
        return None
    conv_type = row[0]
    content = m["content"]
    text_body = str(content.get("text") or "")
    # 触发匹配归一化（大小写/空格不敏感：@群聊Agent、@Agent 都能触发）
    norm = text_body.lower().replace(" ", "")
    triggers = ("@agent", "@小管家", "@群聊agent", "/agent", "/ask")
    has_trigger = any(t in norm for t in triggers)

    # 工具调用（文件搜索/发送等）交给 DeepSeek 函数调用循环自主决策
    # （旧正则快路径会误切自然语言，已移除——见 im-frontend.md 本日记录）

    # ── 裸召唤（🤖 按钮 / 纯 @）：固定问候，不劳烦大模型 ──
    if has_trigger and _is_bare_summon(text_body):
        greeting = ("我在，有何吩咐？可以让我：\n"
                    "· 找问题负责人（谁负责 XX）\n"
                    "· 总结当前对话\n"
                    "· 依据知识库答疑（@ 知识库主人也可）\n"
                    "· 发送文件（把名为 XX 的文件发给对方）")
        try:
            _send_and_broadcast(db, int(_norm(message)["conversationId"]),
                {"text": greeting, "agent": {"name": "群聊 Agent", "kind": "greeting"}},
                f"summon:{_norm(message)['id'] or _norm(message)['seq']}")
            return {"handled": True, "reason": "summon", "runId": f"summon-{_norm(message)['id']}",
                    "traceId": f"summon-{_norm(message)['id']}",
                    "replies": [{"text": greeting, "kind": "text"}], "actions": []}
        except Exception:  # noqa: BLE001
            logger.exception("召唤问候发送失败")
            return None

    # ── R1 知识库代答（二期）：@了在本群绑定知识库的人 / @Agent 且命中知识 ──
    knowledge_answer = _try_knowledge_answer(db, message, text_body)
    if knowledge_answer is not None:
        return knowledge_answer

    # ── @真人必有反应（二期修正）：命中其知识→代答；未命中→实质交接 + 通知本人 ──
    human_answer = _try_mention_human(db, m, text_body)
    if human_answer is not None:
        return human_answer

    event = GroupAgentEvent(
        source="fpim",
        conversation_id=str(m["conversationId"]),
        message_id=str(m["id"] or m["seq"] or ""),
        sender_id=str(m["senderId"] or ""),
        text=text_body,
        mentions=["agent"] if has_trigger else [],
        context=_load_context(db, int(m["conversationId"])),
        metadata={"seq": m["seq"]},
        trigger_mode="mention",
    )
    try:
        result = get_service().handle_event(event)
        if result.handled:
            return result.model_dump(by_alias=True, mode="json")
    except Exception:  # noqa: BLE001 - Agent 失败不能影响原消息发送
        logger.exception("Agent 处理失败 conversation_id=%s", event.conversation_id)
        return None
    # 未触发的单聊消息 → 私聊代理（R2）
    if conv_type != "group":
        try:
            from ..services import agent_proxy
            agent_proxy.handle_direct_message(db, m)
        except Exception:  # noqa: BLE001
            logger.exception("私聊代理触发失败")
    return None
