"""Agent 知识库接口（二期 R1，必须需求 #1）。

- POST   /agent/knowledge       预提供知识（可同时授权分享给哪些群）
- GET    /agent/knowledge       我的知识列表
- PUT    /agent/knowledge/{id}  更新（含分享范围）
- DELETE /agent/knowledge/{id}  撤销（status=revoked，派生回答不再引用）

披露红线：只有 shared_group_ids 里授权的群，Agent 代答才可引用该知识。
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...middleware.deps import get_current_user
from ...models.user import User

router = APIRouter(tags=["Agent 知识库"])


class KnowledgeIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=20000)
    domains: list[str] = Field(default_factory=list, max_length=10)
    sharedGroupIds: list[int] = Field(default_factory=list, max_length=50)


def _dict(row) -> dict:
    return {
        "id": row[0], "title": row[1], "content": row[2],
        "domains": row[3] or [], "sharedGroupIds": [int(x) for x in (row[4] or [])],
        "status": row[5], "createdAt": row[6].isoformat() if row[6] else None,
    }


_SELECT = ("SELECT id, title, content, domains, shared_group_ids, status, created_at "
           "FROM public.agent_knowledge")


@router.post("/agent/knowledge", summary="新增知识")
def create_knowledge(body: KnowledgeIn, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    row = db.execute(text(
        f"""
        INSERT INTO public.agent_knowledge
            (owner_person_id, title, content, domains, shared_group_ids, created_by)
        VALUES (:uid, :title, :content, CAST(:domains AS jsonb),
                CAST(:groups AS jsonb), :uid)
        RETURNING id
        """
    ), {"uid": user.id, "title": body.title.strip(), "content": body.content.strip(),
        "domains": json.dumps([str(d)[:32] for d in body.domains], ensure_ascii=False),
        "groups": json.dumps([str(g) for g in body.sharedGroupIds])}).fetchone()
    row = db.execute(text(_SELECT + " WHERE id = :id"), {"id": row[0]}).fetchone()
    db.commit()
    return {"item": _dict(row)}


@router.get("/agent/knowledge", summary="我的知识列表")
def list_knowledge(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    rows = db.execute(text(
        _SELECT + " WHERE owner_person_id = :uid ORDER BY created_at DESC"
    ), {"uid": user.id}).fetchall()
    return {"items": [_dict(r) for r in rows]}


@router.put("/agent/knowledge/{kid}", summary="更新知识（含分享范围）")
def update_knowledge(kid: int, body: KnowledgeIn, request: Request,
                     db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    updated = db.execute(text(
        """
        UPDATE public.agent_knowledge
           SET title = :title, content = :content,
               domains = CAST(:domains AS jsonb),
               shared_group_ids = CAST(:groups AS jsonb),
               updated_at = now()
         WHERE id = :id AND owner_person_id = :uid
        RETURNING id
        """
    ), {"id": kid, "uid": user.id, "title": body.title.strip(),
        "content": body.content.strip(),
        "domains": json.dumps([str(d)[:32] for d in body.domains], ensure_ascii=False),
        "groups": json.dumps([str(g) for g in body.sharedGroupIds])}).fetchone()
    if not updated:
        raise HTTPException(status_code=404, detail="知识不存在或无权修改")
    row = db.execute(text(_SELECT + " WHERE id = :id"), {"id": kid}).fetchone()
    db.commit()
    return {"item": _dict(row)}


@router.delete("/agent/knowledge/{kid}", summary="撤销知识")
def revoke_knowledge(kid: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    updated = db.execute(text(
        "UPDATE public.agent_knowledge SET status='revoked', updated_at=now() "
        "WHERE id=:id AND owner_person_id=:uid RETURNING id"
    ), {"id": kid, "uid": user.id}).fetchone()
    if not updated:
        raise HTTPException(status_code=404, detail="知识不存在或无权撤销")
    db.commit()
    return {"revoked": True, "id": kid}
