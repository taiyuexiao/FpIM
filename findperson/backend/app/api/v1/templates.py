"""解决模板接口（二期 agent-knowledge 第一切片）。

- POST /issues/{id}/promote-template  由已解决问题沉淀模板（个人库/公共库）
- GET  /templates                     模板列表（public + 我的 private）
- GET  /templates/match               关键词匹配（首问问答页与 Agent 共用，返回模板+责任人）
- POST /templates/{id}/send           把模板卡片发到会话（人工发送；同库留痕）

设计要点见 docs/modules/agent-knowledge.md：模板与 faqs 不合并；
检索联动走本接口而非改 agent-service（智能内核只读只推理的边界不动）。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...middleware.deps import get_current_user
from ...models.user import User
from ...services import im as im_service

router = APIRouter(tags=["解决模板"])


class PromoteIn(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    visibility: str = Field(default="private")   # private | public
    tags: list[str] = Field(default_factory=list, max_length=10)


class TemplateSendIn(BaseModel):
    conversationId: int
    note: str = Field(default="", max_length=500)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _template_dict(row) -> dict:
    return {
        "id": row[0],
        "sourceIssueId": row[1],
        "title": row[2],
        "question": row[3],
        "solution": row[4],
        "tags": row[5] or [],
        "ownerId": row[6],
        "ownerName": row[7],
        "visibility": row[8],
        "createdBy": row[9],
        "useCount": row[10],
        "createdAt": row[11].isoformat() if row[11] else None,
    }


_SELECT = """
    SELECT t.id, t.source_issue_id, t.title, t.question, t.solution, t.tags,
           t.owner_person_id, u.name, t.visibility, t.created_by, t.use_count, t.created_at
      FROM public.issue_templates t
      LEFT JOIN public.user2 u ON u.id = t.owner_person_id
"""


@router.post("/issues/{issue_id}/promote-template", summary="沉淀解决模板",
             description="由已解决问题生成处理模板（question+solution+责任人）；仅提问方/责任人可沉淀")
def promote_template(issue_id: int, body: PromoteIn,
                     request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    issue = db.execute(text(
        "SELECT user_id, assignee_person_id, status, question, summary, resolution_note "
        "FROM public.issues WHERE id=:id"
    ), {"id": issue_id}).fetchone()
    if not issue:
        raise HTTPException(status_code=404, detail="问题不存在")
    if issue[2] != "resolved":
        raise HTTPException(status_code=400, detail="问题解决后才能沉淀模板")
    if user.id not in (issue[0], issue[1]):
        raise HTTPException(status_code=403, detail="仅提问方/责任人可沉淀模板")
    solution = (issue[5] or "").strip()
    if not solution:
        raise HTTPException(status_code=400, detail="解决结论为空，先补结论再沉淀")
    if body.visibility not in ("private", "public"):
        raise HTTPException(status_code=400, detail="visibility 取值不合法")

    title = (body.title or issue[4] or issue[3] or "").strip()[:120]
    tags = [str(t)[:24] for t in body.tags if str(t).strip()][:10]
    new_id = db.execute(text(
        """
        INSERT INTO public.issue_templates
            (source_issue_id, title, question, solution, tags,
             owner_person_id, visibility, created_by)
        VALUES (:iid, :title, :question, :solution, CAST(:tags AS jsonb),
                :owner, :vis, :uid)
        RETURNING id
        """
    ), {"iid": issue_id, "title": title,
        "question": (issue[4] or issue[3] or "").strip(),
        "solution": solution,
        "tags": json.dumps(tags, ensure_ascii=False),
        "owner": issue[1], "vis": body.visibility, "uid": user.id}).fetchone()
    row = db.execute(text(_SELECT + " WHERE t.id = :tid"), {"tid": new_id[0]}).fetchone()
    db.commit()
    return {"item": _template_dict(row)}


@router.get("/templates", summary="模板列表",
            description="public（全员）+ 我的 private；q 关键词过滤")
def list_templates(request: Request, db: Session = Depends(get_db),
                   q: str = "", visibility: str = "",
                   limit: int = Query(default=50, ge=1, le=200)):
    user = get_current_user(request, db)
    cond = "WHERE (t.visibility = 'public' OR t.created_by = :uid)"
    params: dict = {"uid": user.id, "lim": limit}
    if visibility in ("private", "public"):
        cond += " AND t.visibility = :vis"
        params["vis"] = visibility
    key = q.strip()
    if key:
        cond += (" AND (t.title ILIKE :kw OR t.question ILIKE :kw"
                 " OR t.solution ILIKE :kw OR COALESCE(t.tags::text, '') ILIKE :kw)")
        params["kw"] = f"%{key}%"
    rows = db.execute(text(
        _SELECT + f" {cond} ORDER BY t.created_at DESC LIMIT :lim"
    ), params).fetchall()
    return {"items": [_template_dict(r) for r in rows]}


@router.get("/templates/match", summary="模板匹配（首问检索联动）",
            description="关键词命中模板并带出责任人；AskView 与 Agent 共用")
def match_templates(q: str, request: Request,
                    db: Session = Depends(get_db),
                    limit: int = Query(default=5, ge=1, le=20)):
    user = get_current_user(request, db)
    key = q.strip()
    if not key:
        return {"items": []}
    # 可见性：公共库 + 我自己的个人库
    vis_cond = "(t.visibility = 'public' OR t.created_by = :uid)"
    rows = db.execute(text(
        _SELECT + f"""
         WHERE {vis_cond}
           AND (t.title ILIKE :kw OR t.question ILIKE :kw
                OR t.solution ILIKE :kw OR COALESCE(t.tags::text, '') ILIKE :kw)
         ORDER BY t.use_count DESC, t.created_at DESC LIMIT :lim
        """
    ), {"uid": user.id, "kw": f"%{key}%", "lim": limit}).fetchall()
    return {"items": [_template_dict(r) for r in rows]}


@router.post("/templates/{template_id}/send", summary="发送模板到会话",
             description="模板卡片消息进会话（同库留痕）；use_count+1")
def send_template(template_id: int, body: TemplateSendIn,
                  request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    row = db.execute(text(_SELECT + " WHERE t.id = :tid"), {"tid": template_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="模板不存在")
    tpl = _template_dict(row)
    if tpl["visibility"] != "public" and tpl["createdBy"] != user.id:
        raise HTTPException(status_code=403, detail="该模板属于他人个人库")
    try:
        msg, _ = im_service.send_message(
            db, body.conversationId, user.id, "template",
            {
                "templateId": tpl["id"],
                "title": tpl["title"],
                "question": tpl["question"],
                "solution": tpl["solution"],
                "ownerName": tpl["ownerName"],
                "note": (body.note or "").strip(),
            }, None, None, None)
    except (PermissionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.execute(text(
        "UPDATE public.issue_templates SET use_count = use_count + 1, updated_at = :now WHERE id=:tid"
    ), {"tid": template_id, "now": _now()})
    db.commit()
    return {"message": msg}
