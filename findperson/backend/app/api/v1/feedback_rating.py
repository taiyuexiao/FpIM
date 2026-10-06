"""评价与反馈接口（feedback-rating.md，一期）。

- POST /issues/{id}/review     提问方对已解决问题提交评价（评分/标签/评语；一问题一评价，可改）
- GET  /issues/{id}/review     读评价（提问方/责任人可见）
- POST /feedback               产品意见反馈（category + content）
- GET  /admin/product-feedback 意见反馈列表（管理员）
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

router = APIRouter(tags=["评价与反馈"])

# 评价标签预设（前端同款；也接受自由标签，降低评价成本）
REVIEW_TAGS = ("解决及时", "讲解清晰", "态度好", "专业靠谱", "一次解决")

FEEDBACK_CATEGORIES = ("bug", "feature", "experience", "other")


class ReviewUpsert(BaseModel):
    rating: int = Field(ge=1, le=5)
    tags: list[str] = Field(default_factory=list, max_length=10)
    comment: str = Field(default="", max_length=2000)


class ProductFeedbackCreate(BaseModel):
    category: str = Field(default="other")
    content: str = Field(min_length=1, max_length=2000)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _review_dict(row) -> dict:
    return {
        "issueId": row[0],
        "reviewerId": row[1],
        "reviewerName": row[2],
        "rating": row[3],
        "tags": row[4] or [],
        "comment": row[5] or "",
        "createdAt": row[6].isoformat() if row[6] else None,
        "updatedAt": row[7].isoformat() if row[7] else None,
    }


@router.post("/issues/{issue_id}/review", summary="Review Resolved Issue",
             description="提问方评价已解决的问题（一问题一评价，可改；仅 status=resolved 可评）")
def upsert_review(issue_id: int, body: ReviewUpsert, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    issue = db.execute(
        text("SELECT user_id, assignee_person_id, status FROM public.issues WHERE id=:id"),
        {"id": issue_id},
    ).fetchone()
    if not issue:
        raise HTTPException(status_code=404, detail="问题不存在")
    if issue[0] != user.id:
        raise HTTPException(status_code=403, detail="只有提问方可以评价")
    if issue[2] != "resolved":
        raise HTTPException(status_code=400, detail="问题解决后才能评价")

    tags = [str(t)[:24] for t in body.tags if str(t).strip()][:10]
    row = db.execute(text(
        """
        INSERT INTO public.issue_reviews (issue_id, reviewer_id, rating, tags, comment, updated_at)
        VALUES (:iid, :uid, :rating, CAST(:tags AS jsonb), :comment, :now)
        ON CONFLICT (issue_id) DO UPDATE
           SET rating = EXCLUDED.rating,
               tags = EXCLUDED.tags,
               comment = EXCLUDED.comment,
               updated_at = EXCLUDED.updated_at
        RETURNING issue_id, reviewer_id,
                  (SELECT name FROM public.user2 WHERE id = issue_reviews.reviewer_id),
                  rating, tags, comment, created_at, updated_at
        """
    ), {"iid": issue_id, "uid": user.id, "rating": body.rating,
        "tags": json.dumps(tags, ensure_ascii=False),
        "comment": body.comment.strip(), "now": _now()}).fetchone()
    db.commit()
    return {"item": _review_dict(row)}


@router.get("/issues/{issue_id}/review", summary="Get Issue Review",
             description="读问题评价（提问方/责任人可见；无评价返回 item=null）")
def get_review(issue_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    issue = db.execute(
        text("SELECT user_id, assignee_person_id FROM public.issues WHERE id=:id"),
        {"id": issue_id},
    ).fetchone()
    if not issue:
        raise HTTPException(status_code=404, detail="问题不存在")
    if user.id not in (issue[0], issue[1]):
        raise HTTPException(status_code=403, detail="仅问题参与者可见")
    row = db.execute(text(
        """
        SELECT r.issue_id, r.reviewer_id, u.name, r.rating, r.tags, r.comment, r.created_at, r.updated_at
          FROM public.issue_reviews r
          LEFT JOIN public.user2 u ON u.id = r.reviewer_id
         WHERE r.issue_id = :id
        """
    ), {"id": issue_id}).fetchone()
    return {"item": _review_dict(row) if row else None}


@router.post("/feedback", summary="Product Feedback",
             description="产品意见反馈（与业务问题闭环分离）")
def create_feedback(body: ProductFeedbackCreate, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    category = body.category if body.category in FEEDBACK_CATEGORIES else "other"
    row = db.execute(text(
        """
        INSERT INTO public.product_feedback (user_id, category, content)
        VALUES (:uid, :cat, :content)
        RETURNING id, category, content, created_at
        """
    ), {"uid": user.id, "cat": category, "content": body.content.strip()}).fetchone()
    db.commit()
    return {"item": {
        "id": row[0], "category": row[1], "content": row[2],
        "createdAt": row[3].isoformat() if row[3] else None,
    }}


@router.get("/admin/issue-reviews", summary="List Issue Reviews",
            description="问题评价列表（管理员，含评价人与责任人）")
def list_issue_reviews(request: Request, db: Session = Depends(get_db),
                       limit: int = Query(default=50, ge=1, le=200)):
    admin = get_current_user(request, db)
    if admin.system_role != "管理员":
        raise HTTPException(status_code=403, detail="Admin only")
    rows = db.execute(text(
        """
        SELECT r.id, r.issue_id, r.reviewer_id, ru.name, r.rating, r.tags, r.comment,
               i.assignee_person_id, au.name, r.created_at
          FROM public.issue_reviews r
          LEFT JOIN public.user2 ru ON ru.id = r.reviewer_id
          LEFT JOIN public.issues i ON i.id = r.issue_id
          LEFT JOIN public.user2 au ON au.id = i.assignee_person_id
         ORDER BY r.created_at DESC
         LIMIT :lim
        """
    ), {"lim": limit}).fetchall()
    return {"items": [{
        "id": r[0], "issueId": r[1], "reviewerId": r[2], "reviewerName": r[3],
        "rating": r[4], "tags": r[5] or [], "comment": r[6] or "",
        "assigneeId": r[7], "assigneeName": r[8],
        "createdAt": r[9].isoformat() if r[9] else None,
    } for r in rows]}


@router.get("/admin/product-feedback", summary="List Product Feedback",
            description="意见反馈列表（管理员）")
def list_feedback(request: Request, db: Session = Depends(get_db),
                  limit: int = Query(default=50, ge=1, le=200)):
    admin = get_current_user(request, db)
    if admin.system_role != "管理员":
        raise HTTPException(status_code=403, detail="Admin only")
    rows = db.execute(text(
        """
        SELECT f.id, f.user_id, u.name, f.category, f.content, f.created_at
          FROM public.product_feedback f
          LEFT JOIN public.user2 u ON u.id = f.user_id
         ORDER BY f.created_at DESC
         LIMIT :lim
        """
    ), {"lim": limit}).fetchall()
    return {"items": [{
        "id": r[0], "userId": r[1], "userName": r[2], "category": r[3],
        "content": r[4], "createdAt": r[5].isoformat() if r[5] else None,
    } for r in rows]}
