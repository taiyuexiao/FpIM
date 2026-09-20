"""问题跟踪 + 知识沉淀接口。

- POST  /issues/sync                         从问答记录同步问题(LLM 过滤有效问题/判重/建议责任人)
- GET   /issues                              我的问题列表(按状态筛选)
- GET   /issues/{id}                         问题详情(时间线 + 邮件往来)
- PATCH /issues/{id}                         改状态/责任人/备注;标记已解决 → 自动进沉淀候选
- GET   /knowledge/candidates                沉淀候选列表(管理员)
- POST  /knowledge/candidates/{id}/approve   确认沉淀为 FAQ(管理员,可改文案)
- POST  /knowledge/candidates/{id}/reject    忽略候选(管理员)
- GET   /faqs                                知识条目列表
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...middleware.deps import get_current_user
from ...models.content import Content
from ...models.issue import Faq, Issue, IssueEvent, KnowledgeCandidate, MailMessage
from ...models.user import User
from ...services import im as im_service
from ...services import knowledge

router = APIRouter(tags=["问题跟踪"])

STATUSES = ("not_contacted", "processing", "resolved", "unresolved")


class SyncRequest(BaseModel):
    limit: int = Field(default=30, ge=1, le=200)


class IssueUpdate(BaseModel):
    status: str | None = None
    assigneePersonId: str | None = None
    note: str | None = Field(default=None, max_length=2000)
    resolutionNote: str | None = Field(default=None, max_length=2000)


class CandidateApprove(BaseModel):
    mode: str = Field(default="faq")  # faq=写成知识条目 | article=转成文章草稿(进内容审核链路)
    question: str | None = None
    answer: str | None = None
    tags: list | None = None
    ownerPersonId: str | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _admin_user(request: Request, db: Session) -> User:
    """仅管理员可用(返回操作人,便于记录审核人)。"""
    user = get_current_user(request, db)
    if user.system_role != "管理员":
        raise HTTPException(status_code=403, detail="Admin only")
    return user


def _person_name(db: Session, person_id: str | None) -> str | None:
    if not person_id:
        return None
    row = db.execute(text("SELECT name FROM public.user2 WHERE id=:p"), {"p": person_id}).fetchone()
    return row[0] if row else None


def _norm_person_id(db: Session, person_id: str | None) -> str | None:
    """校验并归一化人员 id(cards 里可能是小写 p-0xxx 形式)。"""
    if not person_id:
        return None
    for candidate in (person_id, person_id.upper()):
        row = db.execute(text("SELECT id FROM public.user2 WHERE id=:p"), {"p": candidate}).fetchone()
        if row:
            return row[0]
    return None


def _cards_people(cards) -> list[dict]:
    """从助手卡片的 cards JSONB 里取推荐人(去重,保序)。"""
    out, seen = [], set()
    for card in cards or []:
        if not isinstance(card, dict):
            continue
        pid = card.get("personId") or (card.get("person") or {}).get("id")
        if not pid or pid in seen:
            continue
        seen.add(pid)
        out.append({"id": pid, "name": (card.get("person") or {}).get("name") or pid})
    return out


def _answer_for_issue(db: Session, issue: Issue) -> str:
    """取该次问答助手的回答文本(沉淀候选的答案正文)。"""
    if not issue.message_id:
        return ""
    row = db.execute(
        text("SELECT a.text FROM agent.agui_messages m "
             "JOIN agent.agui_messages a ON a.run_id = m.run_id AND a.role='assistant' "
             "WHERE m.message_id = :mid LIMIT 1"),
        {"mid": issue.message_id},
    ).fetchone()
    return (row[0] if row else "") or ""


def _issue_dict(db: Session, issue: Issue) -> dict:
    return {
        "id": issue.id,
        "question": issue.question,
        "summary": issue.summary,
        "status": issue.status,
        "assigneePersonId": issue.assignee_person_id,
        "assigneeName": _person_name(db, issue.assignee_person_id),
        "repeatedCount": issue.repeated_count,
        "source": issue.source,
        "sessionId": issue.session_id,
        "lastActionAt": issue.last_action_at.isoformat() if issue.last_action_at else None,
        "resolvedAt": issue.resolved_at.isoformat() if issue.resolved_at else None,
        "resolutionNote": issue.resolution_note,
        "createdAt": issue.created_at.isoformat() if issue.created_at else None,
        # ── IM 闭环字段（立项/待办视图用）──
        "conversationId": issue.conversation_id,
        "firstReadAt": issue.first_read_at.isoformat() if issue.first_read_at else None,
        "firstResponseAt": issue.first_response_at.isoformat() if issue.first_response_at else None,
        "askerId": issue.user_id,
        "askerName": _person_name(db, issue.user_id),
    }


@router.get("/issues/assigned", summary="Assigned Issues",
            description="待我处理：我作为责任人的问题（⚠️ 必须声明在 /issues/{issue_id} 之前，否则被路径参数吞掉）")
def list_assigned(request: Request, db: Session = Depends(get_db), status: str | None = None):
    user = get_current_user(request, db)
    query = db.query(Issue).filter(Issue.assignee_person_id == user.id)
    if status:
        if status not in STATUSES:
            raise HTTPException(status_code=400, detail="状态取值不合法")
        query = query.filter(Issue.status == status)
    issues = query.order_by(Issue.last_action_at.desc()).limit(200).all()
    counts = {s: 0 for s in STATUSES}
    for st, n in db.execute(
        text("SELECT status, count(*) FROM public.issues WHERE assignee_person_id=:u GROUP BY status"),
        {"u": user.id},
    ).fetchall():
        if st in counts:
            counts[st] = int(n)
    return {"counts": counts, "items": [_issue_dict(db, i) for i in issues]}


@router.get("/issues/leaderboard", summary="Help Leaderboard",
            description="帮助榜（全员可见的正向榜）：按解决数排名；不放负向明细（决策 D3）。⚠️ 须在 /issues/{issue_id} 之前声明")
def help_leaderboard(request: Request, db: Session = Depends(get_db),
                     limit: int = Query(default=20, ge=1, le=100)):
    get_current_user(request, db)
    rows = db.execute(text(
        """
        SELECT i.assignee_person_id AS pid,
               u.name, d.name AS dept,
               count(*) AS asked,
               count(*) FILTER (WHERE i.status = 'resolved') AS resolved,
               avg(EXTRACT(EPOCH FROM (i.first_response_at - i.created_at)) / 3600.0)
                   FILTER (WHERE i.first_response_at IS NOT NULL) AS avg_resp_hours
          FROM public.issues i
          LEFT JOIN public.user2 u ON u.id = i.assignee_person_id
          LEFT JOIN public.departments d ON d.id = u.department_id
         WHERE i.assignee_person_id IS NOT NULL
         GROUP BY 1, 2, 3
         ORDER BY resolved DESC, asked DESC
         LIMIT :lim
        """
    ), {"lim": limit}).fetchall()
    return {"items": [{
        "rank": idx + 1, "personId": r[0], "name": r[1] or r[0],
        "department": r[2], "askedCount": int(r[3]), "resolvedCount": int(r[4]),
        "avgFirstResponseHours": round(float(r[5]), 1) if r[5] is not None else None,
    } for idx, r in enumerate(rows)]}


@router.get("/issues/gap-map", summary="Knowledge Gap Map",
            description="知识缺口地图（全员可见）：未结问题按责任人所在部门聚合。⚠️ 须在 /issues/{issue_id} 之前声明")
def gap_map(request: Request, db: Session = Depends(get_db)):
    get_current_user(request, db)
    rows = db.execute(text(
        """
        SELECT COALESCE(d.name, '未分组') AS dept,
               count(*) AS open_count,
               count(*) FILTER (WHERE i.status = 'not_contacted') AS untouched
          FROM public.issues i
          LEFT JOIN public.user2 u ON u.id = i.assignee_person_id
          LEFT JOIN public.departments d ON d.id = u.department_id
         WHERE i.status IN ('not_contacted', 'processing')
         GROUP BY 1
         ORDER BY open_count DESC
        """
    )).fetchall()
    examples = db.execute(text(
        """
        SELECT DISTINCT ON (COALESCE(d.name, '未分组'))
               COALESCE(d.name, '未分组') AS dept,
               i.summary, i.question, i.created_at
          FROM public.issues i
          LEFT JOIN public.user2 u ON u.id = i.assignee_person_id
          LEFT JOIN public.departments d ON d.id = u.department_id
         WHERE i.status IN ('not_contacted', 'processing')
         ORDER BY COALESCE(d.name, '未分组'), i.created_at DESC
        """
    )).fetchall()
    ex_map = {r[0]: {"summary": r[1] or r[2], "createdAt": r[3].isoformat() if r[3] else None}
              for r in examples}
    return {"items": [{
        "department": r[0], "openCount": int(r[1]), "untouchedCount": int(r[2]),
        "latestOpen": ex_map.get(r[0]),
    } for r in rows]}


@router.post("/issues/sync", summary="Sync Issues", description="从问答记录同步问题(LLM 判定有效问题并去重)")
def sync_issues(request: Request, db: Session = Depends(get_db), body: SyncRequest | None = None):
    user = get_current_user(request, db)
    limit = (body.limit if body else 30)
    rows = db.execute(
        text("SELECT m.message_id, m.session_id, m.run_id, m.text AS question, a.text AS answer, a.cards AS cards "
             "FROM agent.agui_messages m "
             "JOIN agent.agui_messages a ON a.run_id = m.run_id AND a.role='assistant' "
             "WHERE m.role='user' AND m.user_id = :uid "
             "ORDER BY m.id DESC LIMIT :n"),
        {"uid": user.id, "n": limit},
    ).fetchall()

    existing = [
        {"id": i.id, "summary": i.summary or i.question}
        for i in db.query(Issue).filter(Issue.user_id == user.id).order_by(Issue.id.desc()).limit(50)
    ]
    seen_ids = {
        r[0] for r in db.execute(
            text("SELECT message_id FROM public.issues WHERE user_id=:u AND message_id IS NOT NULL"),
            {"u": user.id},
        ).fetchall()
    }

    created = merged = invalid = 0
    items: list[dict] = []
    for row in rows:
        if row.message_id in seen_ids:
            continue
        people = _cards_people(row.cards)
        verdict = knowledge.judge_question(row.question, row.answer or "", people, existing)
        if not verdict.get("is_valid"):
            invalid += 1
            continue
        dup_id = verdict.get("duplicate_of")
        if dup_id:
            target = db.query(Issue).filter(Issue.id == dup_id, Issue.user_id == user.id).first()
            if target:
                target.repeated_count = (target.repeated_count or 1) + 1
                target.last_action_at = _now()
                db.add(IssueEvent(issue_id=target.id, event_type="synced", operator_id=user.id,
                                  detail="相同问题再次提问(已合并)",
                                  payload={"question": row.question, "messageId": row.message_id}))
                merged += 1
                continue
        assignee = _norm_person_id(db, verdict.get("assignee_person_id"))
        issue = Issue(
            user_id=user.id,
            session_id=row.session_id,
            message_id=row.message_id,
            question=row.question,
            summary=verdict.get("summary"),
            status="not_contacted",
            assignee_person_id=assignee,
            source="sync",
            last_action_at=_now(),
        )
        db.add(issue)
        db.flush()
        db.add(IssueEvent(issue_id=issue.id, event_type="created", operator_id=user.id,
                          detail="从问答记录同步", payload={"answer": (row.answer or "")[:600]}))
        seen_ids.add(row.message_id)
        existing.append({"id": issue.id, "summary": issue.summary or issue.question})
        created += 1
        items.append(_issue_dict(db, issue))
    db.commit()
    return {"scanned": len(rows), "created": created, "merged": merged, "invalid": invalid, "items": items}


@router.get("/issues", summary="List My Issues", description="我的问题列表(可按状态筛选)")
def list_issues(request: Request, db: Session = Depends(get_db), status: str | None = None):
    user = get_current_user(request, db)
    query = db.query(Issue).filter(Issue.user_id == user.id)
    if status:
        if status not in STATUSES:
            raise HTTPException(status_code=400, detail="状态取值不合法")
        query = query.filter(Issue.status == status)
    issues = query.order_by(Issue.last_action_at.desc()).limit(200).all()
    counts = {s: 0 for s in STATUSES}
    for st, n in db.execute(
        text("SELECT status, count(*) FROM public.issues WHERE user_id=:u GROUP BY status"),
        {"u": user.id},
    ).fetchall():
        if st in counts:
            counts[st] = int(n)
    return {"counts": counts, "items": [_issue_dict(db, i) for i in issues]}


@router.get("/issues/{issue_id}", summary="Issue Detail", description="问题详情:时间线 + 邮件往来")
def issue_detail(issue_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    issue = db.query(Issue).filter(Issue.id == issue_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail="问题不存在")
    if issue.user_id != user.id and user.system_role != "管理员":
        raise HTTPException(status_code=403, detail="只能查看自己的问题")

    events = [
        {
            "id": e.id,
            "eventType": e.event_type,
            "detail": e.detail,
            "payload": e.payload,
            "createdAt": e.created_at.isoformat() if e.created_at else None,
        }
        for e in db.query(IssueEvent).filter(IssueEvent.issue_id == issue_id)
        .order_by(IssueEvent.created_at.desc()).limit(100)
    ]
    mails = [
        {
            "id": m.id,
            "direction": m.direction,
            "from": m.from_addr,
            "to": m.to_addr,
            "subject": m.subject,
            "analysis": m.analysis,
            "createdAt": (m.received_at or m.created_at).isoformat() if (m.received_at or m.created_at) else None,
        }
        for m in db.query(MailMessage).filter(MailMessage.issue_id == issue_id)
        .order_by(MailMessage.id.desc()).limit(50)
    ]
    return {"issue": _issue_dict(db, issue), "events": events, "mails": mails}


@router.patch("/issues/{issue_id}", summary="Update Issue", description="改状态/责任人/备注;标记已解决自动进沉淀候选")
async def update_issue(issue_id: int, body: IssueUpdate, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    issue = db.query(Issue).filter(Issue.id == issue_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail="问题不存在")
    if issue.user_id != user.id:
        raise HTTPException(status_code=403, detail="只能更新自己的问题")

    if body.status is not None:
        if body.status not in STATUSES:
            raise HTTPException(status_code=400, detail="状态取值不合法")
        if body.status != issue.status:
            old = issue.status
            issue.status = body.status
            issue.last_action_at = _now()
            if body.status == "resolved":
                issue.resolved_at = _now()
            db.add(IssueEvent(issue_id=issue.id, event_type="status_changed", operator_id=user.id,
                              detail=f"{old} → {body.status}", payload={"from": old, "to": body.status}))
            if body.status == "resolved":
                answer = _answer_for_issue(db, issue)
                cand = knowledge.create_candidate_for_issue(db, issue, answer)
                if cand:
                    db.add(IssueEvent(issue_id=issue.id, event_type="candidate_created", operator_id=user.id,
                                      detail=f"已进入知识沉淀候选(#{cand.id},分数 {cand.score})"))
    if body.assigneePersonId is not None:
        assignee = _norm_person_id(db, body.assigneePersonId)
        if assignee != issue.assignee_person_id:
            issue.assignee_person_id = assignee
            issue.last_action_at = _now()
            db.add(IssueEvent(issue_id=issue.id, event_type="status_changed", operator_id=user.id,
                              detail=f"责任人改为 {_person_name(db, assignee) or assignee or '无'}"))
    if body.resolutionNote is not None:
        issue.resolution_note = body.resolutionNote
        issue.last_action_at = _now()
    if body.note:
        db.add(IssueEvent(issue_id=issue.id, event_type="note", operator_id=user.id, detail=body.note))
        issue.last_action_at = _now()
    db.commit()
    db.refresh(issue)

    # 解决/未解决且已挂会话 → 往会话插 resolve_confirm 系统消息并实时广播（过程留痕在聊天里可见）
    if body.status in ("resolved", "unresolved") and issue.conversation_id:
        result = im_service.insert_resolve_confirm(
            db, issue.id, user.id, body.status, (body.resolutionNote or None))
        if result:
            from ...ws.im_gateway import _load_member_ids, hub
            member_ids = await asyncio.to_thread(_load_member_ids, issue.conversation_id)
            await hub.send_to_users(
                [m for m in member_ids if m != user.id],
                {"type": "message", "message": result["message"]},
            )
            # 小管家给责任人的通知也实时推
            notify = result.get("notify")
            if notify:
                await hub.send_to_users(
                    [notify["toUserId"]],
                    {"type": "message", "message": notify["message"]},
                )

    return _issue_dict(db, issue)


def _candidate_owner(db: Session, cand: KnowledgeCandidate) -> str | None:
    """候选的责任人:优先显式指定,其次取来源问题上已确认的责任人。"""
    ids = [i for i in (cand.source_issue_ids or []) if isinstance(i, int)]
    if not ids:
        return None
    row = db.execute(
        text("SELECT assignee_person_id FROM public.issues "
             "WHERE id = ANY(:ids) AND assignee_person_id IS NOT NULL "
             "ORDER BY id LIMIT 1"),
        {"ids": ids},
    ).fetchone()
    return _norm_person_id(db, row[0]) if row else None


def _create_article_draft(db: Session, cand: KnowledgeCandidate, owner_id: str,
                          body: CandidateApprove) -> Content:
    """把候选转成「内容草稿」(进现有发布-审核链路,不直接对外)。"""
    max_seq = db.query(func.max(Content.id)).filter(Content.id.like("C%")).scalar()
    seq = int(max_seq[1:]) + 1 if max_seq else 1
    content = Content(
        id=f"C{seq:05d}",
        owner_id=owner_id,
        title=(body.question or cand.question).strip()[:250],
        tags=body.tags or [],
        summary=(body.answer or cand.answer or "").strip()[:200],
        body=(body.answer or cand.answer or "").strip(),
        status="draft",
    )
    db.add(content)
    db.flush()
    return content


@router.get("/knowledge/candidates", summary="List Candidates", description="沉淀候选列表(管理员)")
def list_candidates(request: Request, db: Session = Depends(get_db), status: str = "pending"):
    _admin_user(request, db)
    cands = (
        db.query(KnowledgeCandidate)
        .filter(KnowledgeCandidate.status == status)
        .order_by(KnowledgeCandidate.score.desc(), KnowledgeCandidate.id.desc())
        .limit(100).all()
    )
    return {
        "items": [
            {
                "id": c.id,
                "question": c.question,
                "answer": c.answer,
                "score": c.score,
                "signals": c.signals,
                "status": c.status,
                "sourceIssueIds": c.source_issue_ids,
                "createdAt": c.created_at.isoformat() if c.created_at else None,
            }
            for c in cands
        ]
    }


@router.post("/knowledge/candidates/{candidate_id}/approve", summary="Approve Candidate", description="确认沉淀为 FAQ(管理员)")
def approve_candidate(candidate_id: int, body: CandidateApprove, request: Request, db: Session = Depends(get_db)):
    reviewer = _admin_user(request, db)
    cand = db.query(KnowledgeCandidate).filter(KnowledgeCandidate.id == candidate_id).first()
    if not cand:
        raise HTTPException(status_code=404, detail="候选不存在")
    if cand.status != "pending":
        raise HTTPException(status_code=400, detail="该候选已处理")

    owner_id = _norm_person_id(db, body.ownerPersonId) or _candidate_owner(db, cand)
    if body.mode == "article":
        # 转文章草稿:进内容草稿箱,由作者/审核链路决定是否发布
        owner_id = owner_id or reviewer.id
        content = _create_article_draft(db, cand, owner_id, body)
        cand.status = "approved"
        cand.reviewed_by = reviewer.id
        cand.reviewed_at = _now()
        cand.target_content_id = content.id
        db.commit()
        return {"ok": True, "mode": "article", "contentId": content.id}

    faq = knowledge.approve_candidate(
        db, cand, reviewer_id=reviewer.id,
        question=body.question, answer=body.answer, tags=body.tags,
        owner_person_id=owner_id,
    )
    db.commit()
    return {"ok": True, "mode": "faq", "faqId": faq.id}


@router.post("/knowledge/candidates/{candidate_id}/reject", summary="Reject Candidate", description="忽略候选(管理员)")
def reject_candidate(candidate_id: int, request: Request, db: Session = Depends(get_db)):
    reviewer = _admin_user(request, db)
    cand = db.query(KnowledgeCandidate).filter(KnowledgeCandidate.id == candidate_id).first()
    if not cand:
        raise HTTPException(status_code=404, detail="候选不存在")
    cand.status = "rejected"
    cand.reviewed_by = reviewer.id
    cand.reviewed_at = _now()
    db.commit()
    return {"ok": True}


@router.get("/admin/issues/overview", summary="Issue Overview", description="问题闭环总览(管理员):解决率/时长/按责任人分布")
def issues_overview(request: Request, db: Session = Depends(get_db)):
    _admin_user(request, db)
    counts = {s: 0 for s in STATUSES}
    for st, n in db.execute(text("SELECT status, count(*) FROM public.issues GROUP BY status")).fetchall():
        if st in counts:
            counts[st] = int(n)
    total = sum(counts.values())
    resolved = counts["resolved"]
    avg_hours = db.execute(text(
        "SELECT COALESCE(AVG(EXTRACT(EPOCH FROM (resolved_at - created_at)) / 3600), 0)"
        " FROM public.issues WHERE status = 'resolved' AND resolved_at IS NOT NULL")).scalar()
    by_assignee = db.execute(text(
        "SELECT i.assignee_person_id, COALESCE(u.name, i.assignee_person_id),"
        "       count(*) AS total, count(*) FILTER (WHERE i.status = 'resolved') AS resolved"
        " FROM public.issues i LEFT JOIN public.user2 u ON u.id = i.assignee_person_id"
        " WHERE i.assignee_person_id IS NOT NULL"
        " GROUP BY 1, 2 ORDER BY total DESC LIMIT 10")).fetchall()
    by_dept = db.execute(text(
        "SELECT COALESCE(d.name, '未分组'), count(*) AS total,"
        "       count(*) FILTER (WHERE i.status = 'resolved') AS resolved"
        " FROM public.issues i LEFT JOIN public.user2 u ON u.id = i.user_id"
        " LEFT JOIN public.departments d ON d.id = u.department_id"
        " GROUP BY 1 ORDER BY total DESC LIMIT 10")).fetchall()
    recent = db.execute(text(
        "SELECT id, summary, status, assignee_person_id, last_action_at"
        " FROM public.issues ORDER BY last_action_at DESC LIMIT 10")).fetchall()
    return {
        "total": total,
        "counts": counts,
        "resolutionRate": round(resolved / total, 3) if total else 0.0,
        "avgResolveHours": round(float(avg_hours or 0), 1),
        "byAssignee": [{"personId": r[0], "name": r[1], "total": int(r[2]), "resolved": int(r[3])}
                       for r in by_assignee],
        "byDepartment": [{"department": r[0], "total": int(r[1]), "resolved": int(r[2])}
                         for r in by_dept],
        "recent": [{"id": r[0], "summary": r[1], "status": r[2], "assigneePersonId": r[3],
                    "lastActionAt": r[4].isoformat() if r[4] else None} for r in recent],
    }


@router.get("/faqs", summary="List FAQs", description="知识条目列表")
def list_faqs(request: Request, db: Session = Depends(get_db)):
    get_current_user(request, db)
    rows = db.query(Faq).filter(Faq.status == "published").order_by(Faq.updated_at.desc()).limit(200).all()
    return {
        "items": [
            {
                "id": f.id,
                "question": f.question,
                "answer": f.answer,
                "tags": f.tags,
                "ownerPersonId": f.owner_person_id,
                "ownerName": _person_name(db, f.owner_person_id),
                "askedCount": f.asked_count,
                "updatedAt": f.updated_at.isoformat() if f.updated_at else None,
            }
            for f in rows
        ]
    }
