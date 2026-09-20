"""IM 内核服务层：会话 / 消息 / 已读 / 附件 / 问题关联。

设计要点（详见 docs/modules/im-core.md）：
- 单聊去重：`direct_key` 唯一索引 + `ON CONFLICT DO UPDATE RETURNING`，一步"查或建"，不需要分布式锁
- 消息序号：`UPDATE im.conversations SET last_seq = last_seq + 1 RETURNING last_seq`，行锁保证严格递增
- 幂等：`(sender_id, client_msg_id)` 唯一索引兜底；重复提交返回已存在的那条，不报错
- 已读游标：`conversation_members.last_read_seq` 供红点（可覆盖）
  首次已读留痕走 `public.issue_events(event_type='read')`，由唯一索引保证不可覆盖
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

GROUP_MEMBER_LIMIT = 100          # 单群上限（已定：100 人）
DEFAULT_PAGE_SIZE = 30
MAX_PAGE_SIZE = 100

MESSAGE_TYPES = (
    "text", "image", "file", "audio", "video", "system",
    "issue_card", "resolve_confirm", "report_card",
)

# 系统发送方：用于 resolve_confirm 等无人格消息（sender_id 存 "system"，NOT NULL 约束下合法）
SYSTEM_SENDER = "system"
SYSTEM_MSG_TYPES = ("system", "resolve_confirm", "report_card")

# 「小管家」通知号 = system（user2 里有同名 bot 行，active=false，仅供取名与鉴权拦截）
BOT_ID = SYSTEM_SENDER


def notify_user(db: Session, user_id: str, text_content: str,
                issue_id: int | None = None) -> dict:
    """小管家通知：发到 bot 与该用户的单聊会话（一人一栏，消息累积）。

    - 会话即 bot↔user 的 direct（direct_key 去重，天然一人一栏）
    - sender 是 system（走系统发送方约定，跳过成员校验）
    - 返回 (消息 dict, 会话 id)，调用方负责 WS 广播
    """
    conv = get_or_create_direct(db, BOT_ID, user_id)
    msg, _ = send_message(
        db, conv["id"], BOT_ID, "system", {"text": text_content}, issue_id=issue_id)
    return msg, conv["id"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def direct_key(a: str, b: str) -> str:
    """单聊去重键：两个 user_id 升序拼接，保证 (A,B) 与 (B,A) 得到同一个键。"""
    x, y = sorted([str(a), str(b)])
    return f"{x}|{y}"


# ── 会话 ──────────────────────────────────────────────────────────

def get_or_create_direct(db: Session, me: str, other: str,
                         issue_id: int | None = None) -> dict:
    """取或建单聊会话（免加好友，任何人可直接对话）。

    ON CONFLICT 命中已存在会话时只更新 updated_at，不覆盖 issue_id，
    避免后来的提问把会话的主问题锚点抢走。
    """
    if me == other:
        raise ValueError("不能与自己发起会话")
    key = direct_key(me, other)
    row = db.execute(text(
        """
        INSERT INTO im.conversations (type, direct_key, created_by, issue_id)
        VALUES ('direct', :key, :me, :issue)
        ON CONFLICT (direct_key) WHERE direct_key IS NOT NULL
        DO UPDATE SET updated_at = now()
        RETURNING id, issue_id
        """
    ), {"key": key, "me": me, "issue": issue_id}).fetchone()
    conv_id = row[0]

    # 成员幂等写入（重复建会话时不重复插入）
    db.execute(text(
        """
        INSERT INTO im.conversation_members (conversation_id, user_id, member_role)
        VALUES (:cid, :u1, 'member'), (:cid, :u2, 'member')
        ON CONFLICT (conversation_id, user_id) DO UPDATE SET left_at = NULL
        """
    ), {"cid": conv_id, "u1": me, "u2": other})
    db.commit()
    return {"id": conv_id, "type": "direct", "created": row[1] is None}


def create_group(db: Session, owner: str, member_ids: list[str],
                 title: str, issue_id: int | None = None) -> dict:
    """建群聊。单群上限 100 人（含群主）。"""
    members = [owner] + [m for m in dict.fromkeys(member_ids) if m != owner]
    if len(members) > GROUP_MEMBER_LIMIT:
        raise ValueError(f"群成员上限 {GROUP_MEMBER_LIMIT} 人，当前 {len(members)} 人")
    if not title.strip():
        raise ValueError("群名称不能为空")

    conv_id = db.execute(text(
        """
        INSERT INTO im.conversations (type, title, owner_id, created_by, issue_id)
        VALUES ('group', :title, :owner, :owner, :issue)
        RETURNING id
        """
    ), {"title": title.strip(), "owner": owner, "issue": issue_id}).scalar()

    db.execute(text(
        """
        INSERT INTO im.conversation_members (conversation_id, user_id, member_role)
        VALUES (:cid, :uid, :role)
        ON CONFLICT (conversation_id, user_id) DO NOTHING
        """
    ), [{"cid": conv_id, "uid": m, "role": "owner" if m == owner else "member"}
        for m in members])
    db.commit()
    return {"id": conv_id, "type": "group", "memberCount": len(members)}


def is_member(db: Session, conv_id: int, user_id: str) -> bool:
    row = db.execute(text(
        "SELECT 1 FROM im.conversation_members "
        "WHERE conversation_id = :cid AND user_id = :uid AND left_at IS NULL"
    ), {"cid": conv_id, "uid": user_id}).fetchone()
    return row is not None


def add_members(db: Session, conv_id: int, user_ids: list[str]) -> int:
    """群聊拉人（问题群多方会诊）。仍受 100 人上限约束。"""
    conv = db.execute(text(
        "SELECT type FROM im.conversations WHERE id = :cid"), {"cid": conv_id}).fetchone()
    if not conv:
        raise ValueError("会话不存在")
    if conv[0] != "group":
        raise ValueError("只有群聊可以加人")

    current = db.execute(text(
        "SELECT count(*) FROM im.conversation_members "
        "WHERE conversation_id = :cid AND left_at IS NULL"), {"cid": conv_id}).scalar() or 0
    new_ids = [u for u in dict.fromkeys(user_ids)
               if not is_member(db, conv_id, u)]
    if current + len(new_ids) > GROUP_MEMBER_LIMIT:
        raise ValueError(f"群成员上限 {GROUP_MEMBER_LIMIT} 人，"
                         f"当前 {current} 人，无法再加入 {len(new_ids)} 人")
    if new_ids:
        db.execute(text(
            """
            INSERT INTO im.conversation_members (conversation_id, user_id, member_role)
            VALUES (:cid, :uid, 'member')
            ON CONFLICT (conversation_id, user_id) DO UPDATE SET left_at = NULL
            """
        ), [{"cid": conv_id, "uid": u} for u in new_ids])
        db.commit()
    return len(new_ids)


def list_conversations(db: Session, user_id: str, limit: int = 50) -> list[dict]:
    """我的会话列表（按最后消息时间倒序），带对方信息 / 未读数 / 最后一条消息预览。"""
    rows = db.execute(text(
        """
        SELECT c.id,
               c.type,
               c.title,
               c.owner_id,
               c.issue_id,
               c.last_message_at,
               m.last_read_seq,
               m.unread_count,
               m.pinned,
               c.last_seq,
               -- 单聊取对方 id（成员表里 user_id != 我 的那一行）
               (SELECT cm2.user_id FROM im.conversation_members cm2
                 WHERE cm2.conversation_id = c.id AND cm2.user_id <> :uid
                   AND cm2.left_at IS NULL
                 LIMIT 1) AS peer_id
          FROM im.conversations c
          JOIN im.conversation_members m
            ON m.conversation_id = c.id AND m.user_id = :uid AND m.left_at IS NULL
         ORDER BY m.pinned DESC, c.last_message_at DESC NULLS LAST, c.id DESC
         LIMIT :lim
        """
    ), {"uid": user_id, "lim": limit}).fetchall()

    conv_ids = [r[0] for r in rows]
    if not conv_ids:
        return []

    # 批量取每个会话最后一条消息（避免 N+1）
    # 注意：列清单必须与 _msg_dict_from_row 的取值顺序完全一致（缺列会直接 IndexError）；
    # dict 的 key 用 r[1]=conversation_id，因为 r[0] 是消息 id。
    last_msgs = {}
    for r in db.execute(text(
        """
        SELECT DISTINCT ON (conversation_id)
               id, conversation_id, seq, sender_id, msg_type, content,
               client_msg_id, reply_to_id, issue_id, created_at
          FROM im.messages
         WHERE conversation_id = ANY(:ids) AND revoked = false
         ORDER BY conversation_id, seq DESC
        """
    ), {"ids": conv_ids}).fetchall():
        last_msgs[r[1]] = r

    peer_ids = [r[10] for r in rows if r[10]]
    people = _people_map(db, peer_ids)

    out = []
    for r in rows:
        peer = people.get(r[10]) if r[10] else None
        last = last_msgs.get(r[0])
        out.append({
            "id": r[0],
            "type": r[1],
            "title": r[2] or (peer or {}).get("name") or "会话",
            "ownerId": r[3],
            "issueId": r[4],
            "lastMessageAt": _iso(r[5]),
            "lastReadSeq": r[6],
            "unreadCount": r[7],
            "pinned": r[8],
            "lastSeq": r[9],
            "peer": peer,
            "lastMessage": _msg_dict_from_row(last) if last else None,
        })
    return out


def get_conversation(db: Session, conv_id: int, user_id: str) -> dict | None:
    """单会话详情（须是成员）。"""
    row = db.execute(text(
        """
        SELECT c.id, c.type, c.title, c.owner_id, c.issue_id, c.last_seq, c.created_at,
               m.last_read_seq, m.unread_count
          FROM im.conversations c
          JOIN im.conversation_members m
            ON m.conversation_id = c.id AND m.user_id = :uid AND m.left_at IS NULL
         WHERE c.id = :cid
        """
    ), {"cid": conv_id, "uid": user_id}).fetchone()
    if not row:
        return None

    members = db.execute(text(
        "SELECT user_id, member_role FROM im.conversation_members "
        "WHERE conversation_id = :cid AND left_at IS NULL ORDER BY member_role DESC, joined_at"
    ), {"cid": conv_id}).fetchall()
    people = _people_map(db, [m[0] for m in members])

    peer_id = next((m[0] for m in members if m[0] != user_id), None) if row[1] == "direct" else None
    return {
        "id": row[0],
        "type": row[1],
        "title": row[2] or (people.get(peer_id) or {}).get("name") or "会话",
        "ownerId": row[3],
        "issueId": row[4],
        "lastSeq": row[5],
        "createdAt": _iso(row[6]),
        "lastReadSeq": row[7],
        "unreadCount": row[8],
        "peer": people.get(peer_id) if peer_id else None,
        "members": [{**people.get(m[0], {"id": m[0], "name": m[0]}), "role": m[1]}
                    for m in members],
    }


# ── 消息 ──────────────────────────────────────────────────────────

def send_message(db: Session, conv_id: int, sender_id: str, msg_type: str = "text",
                 content: dict | None = None, client_msg_id: str | None = None,
                 reply_to_id: int | None = None, issue_id: int | None = None) -> tuple[dict, bool]:
    """发消息。返回 (消息 dict, 是否新建)。

    幂等：同一 sender + client_msg_id 重复提交时，直接返回已存在的那条（created=False），
    客户端重试 / 断线重发都不会产生重复消息。
    """
    if msg_type not in MESSAGE_TYPES:
        raise ValueError(f"不支持的消息类型: {msg_type}")
    content = content or {}

    if client_msg_id:
        dup = db.execute(text(
            """
            SELECT id, conversation_id, seq, sender_id, msg_type, content,
                   client_msg_id, reply_to_id, issue_id, created_at
              FROM im.messages
             WHERE sender_id = :sid AND client_msg_id = :cmid
            """
        ), {"sid": sender_id, "cmid": client_msg_id}).fetchone()
        if dup:
            return _msg_dict_from_row(dup), False

    if not is_member(db, conv_id, sender_id) and sender_id != SYSTEM_SENDER:
        raise PermissionError("不是该会话成员")
    if sender_id == SYSTEM_SENDER and msg_type not in SYSTEM_MSG_TYPES:
        raise ValueError("系统号只允许发系统类消息")

    # 未显式挂接问题时：会话若有"活跃主问题"则自动挂接。
    # 这是"过程即数据"的关键：立项后普通聊天不必记得带 issueId；
    # 问题解决/关闭后锚点仍在但不再挂接，避免闲谈污染已结问题。
    if issue_id is None and msg_type != "issue_card":
        anchor = db.execute(text(
            """
            SELECT c.issue_id FROM im.conversations c
            JOIN public.issues i ON i.id = c.issue_id
            WHERE c.id = :cid AND i.status = 'processing'
            """
        ), {"cid": conv_id}).fetchone()
        if anchor:
            issue_id = anchor[0]

    # 序号分配：行锁 + 自增，严格递增且并发安全
    seq = db.execute(text(
        "UPDATE im.conversations SET last_seq = last_seq + 1, updated_at = now() "
        "WHERE id = :cid RETURNING last_seq"
    ), {"cid": conv_id}).scalar()
    if seq is None:
        raise ValueError("会话不存在")

    row = db.execute(text(
        """
        INSERT INTO im.messages
            (conversation_id, seq, sender_id, msg_type, content,
             client_msg_id, reply_to_id, issue_id)
        VALUES (:cid, :seq, :sid, :mtype, CAST(:content AS jsonb),
                :cmid, :rid, :iid)
        RETURNING id, conversation_id, seq, sender_id, msg_type, content,
                  client_msg_id, reply_to_id, issue_id, created_at
        """
    ), {"cid": conv_id, "seq": seq, "sid": sender_id, "mtype": msg_type,
        "content": _json(content), "cmid": client_msg_id,
        "rid": reply_to_id, "iid": issue_id}).fetchone()

    # 会话摘要 + 其他成员未读数 +1
    db.execute(text(
        "UPDATE im.conversations SET last_message_id = :mid, last_message_at = :ts WHERE id = :cid"
    ), {"mid": row[0], "ts": row[9], "cid": conv_id})
    db.execute(text(
        "UPDATE im.conversation_members SET unread_count = unread_count + 1 "
        "WHERE conversation_id = :cid AND user_id <> :sid AND left_at IS NULL"
    ), {"cid": conv_id, "sid": sender_id})

    # 问题联动：消息挂到问题后，若问题还是"未联系"，被问方的首次响应即由消息产生
    if issue_id:
        _touch_issue_on_message(db, issue_id, sender_id)

    db.commit()
    return _msg_dict_from_row(row), True


def list_messages(db: Session, conv_id: int, user_id: str,
                  before_seq: int | None = None, after_seq: int | None = None,
                  limit: int = DEFAULT_PAGE_SIZE) -> list[dict]:
    """拉历史消息。

    - after_seq 不为空 → 增量拉（断线重连后补齐）
    - before_seq 不为空 → 向上翻页
    """
    if not is_member(db, conv_id, user_id):
        raise PermissionError("不是该会话成员")
    limit = max(1, min(limit, MAX_PAGE_SIZE))

    if after_seq is not None:
        rows = db.execute(text(
            """
            SELECT id, conversation_id, seq, sender_id, msg_type, content,
                   client_msg_id, reply_to_id, issue_id, created_at
              FROM im.messages
             WHERE conversation_id = :cid AND seq > :s AND revoked = false
             ORDER BY seq ASC LIMIT :lim
            """
        ), {"cid": conv_id, "s": after_seq, "lim": limit}).fetchall()
        return [_msg_dict_from_row(r) for r in rows]

    params = {"cid": conv_id, "lim": limit}
    cond = ""
    if before_seq is not None:
        cond = "AND seq < :before"
        params["before"] = before_seq
    rows = db.execute(text(
        f"""
        SELECT id, conversation_id, seq, sender_id, msg_type, content,
               client_msg_id, reply_to_id, issue_id, created_at
          FROM im.messages
         WHERE conversation_id = :cid {cond} AND revoked = false
         ORDER BY seq DESC LIMIT :lim
        """
    ), params).fetchall()
    return [_msg_dict_from_row(r) for r in reversed(rows)]


def mark_read(db: Session, conv_id: int, user_id: str, seq: int) -> dict:
    """推进已读游标（只前进不后退），未读数按游标重算。

    注意：这里只处理"红点"。问题级的**首次已读留痕**在 record_issue_read()，
    写的是 issue_events 且由唯一索引保证不可覆盖。
    """
    row = db.execute(text(
        """
        UPDATE im.conversation_members
           SET last_read_seq = GREATEST(last_read_seq, :seq),
               last_read_at = now(),
               unread_count = (SELECT count(*) FROM im.messages msg
                                WHERE msg.conversation_id = :cid
                                  AND msg.seq > GREATEST(im.conversation_members.last_read_seq, :seq)
                                  AND msg.revoked = false)
         WHERE conversation_id = :cid AND user_id = :uid
        RETURNING last_read_seq, unread_count
        """
    ), {"cid": conv_id, "seq": seq, "uid": user_id}).fetchone()
    if not row:
        raise PermissionError("不是该会话成员")
    db.commit()
    return {"lastReadSeq": row[0], "unreadCount": row[1]}


def revoke_message(db: Session, message_id: int, user_id: str) -> bool:
    """撤回自己的消息（2 分钟内）。"""
    row = db.execute(text(
        """
        UPDATE im.messages
           SET revoked = true, content = '{}'::jsonb
         WHERE id = :mid AND sender_id = :uid
           AND created_at > now() - interval '2 minutes'
        RETURNING conversation_id, seq
        """
    ), {"mid": message_id, "uid": user_id}).fetchone()
    if not row:
        return False
    db.commit()
    return True


# ── 附件 ──────────────────────────────────────────────────────────

def register_attachment(db: Session, sha256: str, ext: str, mime: str,
                        size_bytes: int, original_name: str,
                        rel_path: str, uploader_id: str) -> dict:
    """登记附件。同 sha256 已存在时复用（秒传），只 ref_count +1。"""
    row = db.execute(text(
        """
        INSERT INTO im.attachments
            (sha256, ext, mime, size_bytes, original_name, rel_path, uploader_id, ref_count)
        VALUES (:sha, :ext, :mime, :size, :name, :path, :uid, 1)
        ON CONFLICT (sha256) DO UPDATE SET ref_count = im.attachments.ref_count + 1
        RETURNING id, sha256, ext, mime, size_bytes, original_name, rel_path,
                  (xmax = 0) AS inserted
        """
    ), {"sha": sha256, "ext": ext, "mime": mime, "size": size_bytes,
        "name": original_name, "path": rel_path, "uid": uploader_id}).fetchone()
    db.commit()
    return {"id": row[0], "sha256": row[1], "ext": row[2], "mime": row[3],
            "size": row[4], "name": row[5], "url": f"/api/v1/im/files/{row[6]}"}


# ── 问题联动 ──────────────────────────────────────────────────────

def _touch_issue_on_message(db: Session, issue_id: int, sender_id: str) -> None:
    """消息落到问题上时更新问题活跃时间；若发送方即责任人且尚未响应，记首次响应。"""
    db.execute(text(
        """
        UPDATE public.issues
           SET last_action_at = now(), updated_at = now(),
               first_response_at = COALESCE(first_response_at,
                   CASE WHEN assignee_person_id = :sid THEN now() END)
         WHERE id = :iid
        """
    ), {"iid": issue_id, "sid": sender_id})


def record_issue_read(db: Session, issue_id: int, reader_id: str) -> bool:
    """记录问题级首次已读（唯一事实源，不可覆盖）。

    只认**责任人**的已读：群里 20 个人都看了不算，否则会掩盖"责任人根本没看"。
    由 uq_ev_read_per_actor 唯一索引兜底，重复调用直接忽略。
    """
    issue = db.execute(text(
        "SELECT assignee_person_id, first_read_at FROM public.issues WHERE id = :iid"
    ), {"iid": issue_id}).fetchone()
    if not issue:
        return False
    if issue[0] != reader_id:          # 只有责任人本人的已读才算留痕
        return False

    inserted = db.execute(text(
        """
        INSERT INTO public.issue_events (issue_id, event_type, detail, operator_id)
        VALUES (:iid, 'read', '责任人首次查看', :uid)
        ON CONFLICT DO NOTHING
        RETURNING id
        """
    ), {"iid": issue_id, "uid": reader_id}).fetchone()

    if inserted:
        db.execute(text(
            "UPDATE public.issues SET first_read_at = COALESCE(first_read_at, now()) WHERE id = :iid"
        ), {"iid": issue_id})
    db.commit()
    return inserted is not None


def link_issue_conversation(db: Session, issue_id: int, conv_id: int) -> None:
    """把会话挂到问题上（issues.conversation_id 反向指针，便于从问题一键跳会话）。"""
    db.execute(text(
        "UPDATE public.issues SET conversation_id = :cid, updated_at = now() WHERE id = :iid"
    ), {"cid": conv_id, "iid": issue_id})
    db.commit()


def create_issue_in_conversation(db: Session, conv_id: int, creator_id: str,
                                 question: str, assignee_id: str | None = None,
                                 summary: str | None = None) -> dict:
    """在会话内立项：创建问题 + 双向关联 + 插 issue_card 消息。

    - 状态直接置 processing：立项卡本身就是"联系"这个动作（与邮件链路"发出即处理中"一致）
    - 单聊不指定责任人时默认对方；**群聊必须显式指定**（集体负责 = 无人负责，是考核的底线）
    - 立项后该问题成为会话的"活跃主问题"，后续消息由 send_message 自动挂接
    - 返回 {"issue": {...}, "message": {...}}
    """
    question = (question or "").strip()
    if not question:
        raise ValueError("问题描述不能为空")
    if len(question) > 2000:
        raise ValueError("问题描述过长（≤2000 字）")
    if not is_member(db, conv_id, creator_id):
        raise PermissionError("不是该会话成员")

    conv = db.execute(text(
        "SELECT type, direct_key FROM im.conversations WHERE id = :cid"
    ), {"cid": conv_id}).fetchone()
    if not conv:
        raise ValueError("会话不存在")

    if not assignee_id:
        if conv[0] == "direct" and conv[1]:
            a, b = conv[1].split("|")
            assignee_id = b if a == creator_id else a
        if not assignee_id:
            raise ValueError("群聊立项必须指定唯一责任人（集体负责=无人负责）")
    if assignee_id == creator_id:
        raise ValueError("责任人不能是自己")
    if not is_member(db, conv_id, assignee_id):
        raise ValueError("责任人必须是会话成员")

    people = _people_map(db, [creator_id, assignee_id])
    summary = (summary or "").strip() or question[:120]

    issue_id = db.execute(text(
        """
        INSERT INTO public.issues
            (user_id, question, summary, status, assignee_person_id, source,
             conversation_id, last_action_at)
        VALUES (:uid, :q, :s, 'processing', :aid, 'chat', :cid, now())
        RETURNING id
        """
    ), {"uid": creator_id, "q": question, "s": summary,
        "aid": assignee_id, "cid": conv_id}).scalar()

    db.execute(text(
        """
        INSERT INTO public.issue_events (issue_id, event_type, detail, operator_id)
        VALUES (:iid, 'created', '在会话内立项', :uid)
        """
    ), {"iid": issue_id, "uid": creator_id})

    # 成为会话的活跃主问题
    db.execute(text(
        "UPDATE im.conversations SET issue_id = :iid, updated_at = now() WHERE id = :cid"
    ), {"iid": issue_id, "cid": conv_id})

    # 立项卡消息：结构化卡片（幂等键按问题唯一）
    msg, _ = send_message(
        db, conv_id, creator_id, "issue_card",
        {"issueId": issue_id, "question": question, "summary": summary,
         "assigneePersonId": assignee_id,
         "assigneeName": (people.get(assignee_id) or {}).get("name"),
         "askerName": (people.get(creator_id) or {}).get("name"),
         "status": "processing"},
        client_msg_id=f"issuecard-{issue_id}",
        issue_id=issue_id,
    )
    # send_message 内部已 commit

    # 小管家通知责任人（他可能不在盯着这个会话；通知到他自己的"小管家"一栏）
    asker_name = (people.get(creator_id) or {}).get("name") or creator_id
    notify_msg, notify_cid = notify_user(
        db, assignee_id,
        f"{asker_name} 向你提出了一个问题：「{summary}」\n去「待办」处理，或直接打开我们的会话。",
        issue_id=issue_id,
    )

    return {
        "issue": {
            "id": issue_id, "question": question, "summary": summary,
            "status": "processing", "assigneePersonId": assignee_id,
            "assigneeName": (people.get(assignee_id) or {}).get("name"),
            "askerId": creator_id,
            "askerName": (people.get(creator_id) or {}).get("name"),
        },
        "message": msg,
        "notify": {"message": notify_msg, "conversationId": notify_cid,
                   "toUserId": assignee_id},
    }


def insert_resolve_confirm(db: Session, issue_id: int, actor_id: str,
                           new_status: str, note: str | None = None) -> dict | None:
    """问题被标记解决/未解决时，往其所在会话插一条 resolve_confirm 系统消息（留痕）。

    由 issues.py 的状态变更流程调用；问题没挂会话时不做任何事。
    返回插入的消息 dict 或 None。
    """
    row = db.execute(text(
        "SELECT conversation_id, summary, question, status FROM public.issues WHERE id = :iid"
    ), {"iid": issue_id}).fetchone()
    if not row or not row[0]:
        return None
    conv_id, title = row[0], (row[1] or row[2] or f"问题 #{issue_id}")
    actor = (_people_map(db, [actor_id]).get(actor_id) or {}).get("name") or actor_id
    label = "已解决" if new_status == "resolved" else "未解决"
    text_line = f"「{title}」已由 {actor} 标记为{label}" + (f"：{note}" if note else "")
    # 不带 client_msg_id：重开→再解决 是合法重复事件，不能被幂等键吞掉
    msg, _ = send_message(
        db, conv_id, SYSTEM_SENDER, "resolve_confirm",
        {"text": text_line, "issueId": issue_id, "status": new_status},
        issue_id=issue_id,
    )

    # 小管家通知责任人：TA 处理的问题有结论了（提问方在同会话里已能看到 resolve_confirm）
    assignee = db.execute(text(
        "SELECT assignee_person_id FROM public.issues WHERE id = :iid"
    ), {"iid": issue_id}).scalar()
    if assignee and assignee != actor_id:
        nmsg, ncid = notify_user(
            db, assignee,
            f"你处理的问题「{title}」已被 {actor} 标记为{label}。"
            + (f"\n结论：{note}" if note else ""),
            issue_id=issue_id,
        )
        return {"message": msg, "notify": {"message": nmsg, "conversationId": ncid,
                                           "toUserId": assignee}}
    return {"message": msg}


def conversation_issue_brief(db: Session, conv_id: int) -> list[dict]:
    """该会话关联的问题列表（会话右侧"问题详情 + 处理过程"面板用）。"""
    rows = db.execute(text(
        """
        SELECT id, question, summary, status, assignee_person_id,
               first_read_at, first_response_at, resolved_at, resolution_note,
               created_at, last_action_at, user_id
          FROM public.issues
         WHERE conversation_id = :cid
            OR id = (SELECT issue_id FROM im.conversations WHERE id = :cid)
         ORDER BY created_at DESC
        """
    ), {"cid": conv_id}).fetchall()
    if not rows:
        return []
    people = _people_map(db, [r[4] for r in rows if r[4]] + [r[11] for r in rows if r[11]])
    return [{
        "id": r[0], "question": r[1], "summary": r[2], "status": r[3],
        "assigneePersonId": r[4],
        "assigneeName": (people.get(r[4]) or {}).get("name"),
        "firstReadAt": _iso(r[5]), "firstResponseAt": _iso(r[6]),
        "resolvedAt": _iso(r[7]), "resolutionNote": r[8],
        "createdAt": _iso(r[9]), "lastActionAt": _iso(r[10]),
        # 提问人：前端据此判断"我能不能点已解决"（只有提问方能确认）
        "askerId": r[11], "askerName": (people.get(r[11]) or {}).get("name"),
    } for r in rows]


def issue_timeline(db: Session, issue_id: int) -> list[dict]:
    """问题时间线（从 issue_events 唯一事实源聚合）。"""
    rows = db.execute(text(
        """
        SELECT id, event_type, detail, payload, operator_id, created_at
          FROM public.issue_events
         WHERE issue_id = :iid
         ORDER BY created_at ASC, id ASC
        """
    ), {"iid": issue_id}).fetchall()
    people = _people_map(db, [r[4] for r in rows if r[4]])
    return [{
        "id": r[0], "eventType": r[1], "detail": r[2], "payload": r[3],
        "operatorId": r[4], "operatorName": (people.get(r[4]) or {}).get("name"),
        "createdAt": _iso(r[5]),
    } for r in rows]


# ── 内部工具 ──────────────────────────────────────────────────────

def _people_map(db: Session, ids: list[str]) -> dict[str, dict]:
    """批量取人员公开信息（姓名/部门/职务/上级），供会话与消息渲染。"""
    ids = [i for i in dict.fromkeys(ids) if i]
    if not ids:
        return {}
    rows = db.execute(text(
        """
        SELECT u.id, u.name, u.role, u.manager_id, d.name AS dept_name, u.email
          FROM public.user2 u
          LEFT JOIN public.departments d ON d.id = u.department_id
         WHERE u.id = ANY(:ids)
        """
    ), {"ids": ids}).fetchall()
    return {r[0]: {"id": r[0], "name": r[1], "role": r[2], "managerId": r[3],
                   "department": r[4], "email": r[5]} for r in rows}


def _msg_dict_from_row(r) -> dict:
    """行 → 消息 dict（列顺序与各查询保持一致）。"""
    return {
        "id": r[0],
        "conversationId": r[1],
        "seq": r[2],
        "senderId": r[3],
        "msgType": r[4],
        "content": r[5] or {},
        "clientMsgId": r[6],
        "replyToId": r[7],
        "issueId": r[8],
        "createdAt": _iso(r[9]),
    }


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def _json(value) -> str:
    import json
    return json.dumps(value, ensure_ascii=False)


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
