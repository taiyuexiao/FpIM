"""他画像（标签）"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...middleware.deps import get_current_user
from ...models.review import PeerReview
from ...models.user import User
from ...schemas.reviews import ReviewCreateRequest, ReviewResponse, PersonTagSummary
from ...schemas.sessions import PaginatedResponse
from ...services.publish_event import emit_publish_event, PERSON_CHANGED
import re

from ...services.tag_sync import sync_person_domain_tags, sync_tag_to_agent


def _split_tags(tag: str) -> list[str]:
    """顿号/逗号/分号/斜杠分隔的多标签拆分(『大数据底层开发、知识工程』→ 两个独立标签)。

    不按空格拆:英文标签可能含合法空格(如 AI 基础研发)。
    """
    return [t.strip() for t in re.split(r"[、，,；;/]+", tag or "") if t.strip()]
from sqlalchemy import text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reviews", tags=["他画像"])


def _sync_review_to_agent_tags(db: Session, *, person_id: str, tag: str, active: bool,
                               approval: str = "approved") -> None:
    """画像评价同步进 Agent 标签体系(代理到 services.tag_sync 公共实现)。

    approval:新他人标签写 'pending'(检索降权),被评价人放行后升 'approved'。
    """
    sync_tag_to_agent(db, person_id=person_id, tag=tag, active=active,
                      source="peer_review", created_by="review-api", approval=approval)


def _review_to_response(r: PeerReview) -> ReviewResponse:
    return ReviewResponse(
        id=r.id,
        personId=r.person_id,
        personName=r.person_user.name if r.person_user else None,
        reviewerId=r.reviewer_id,
        reviewer=r.reviewer_user.name if r.reviewer_user else None,
        tag=r.tag_name,
        date=str(r.created_at.date()) if r.created_at else "",
        status=r.status or "approved",
    )


@router.post("", response_model=ReviewResponse, status_code=201, summary="Create Review", description="为他⼈打标签")
def create_review(body: ReviewCreateRequest, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if body.personId == user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能为自己打标签")
    tags = _split_tags(body.tag) or [body.tag]
    # 多标签:逐标签独立成记录(各自进入被评价人的待放行通知/信任分级流),返回首条
    first: PeerReview | None = None
    for tag in tags:
        existing = db.query(PeerReview).filter(
            PeerReview.person_id == body.personId,
            PeerReview.reviewer_id == user.id,
            PeerReview.tag_name == tag,
        ).first()
        if existing:
            # v4 §五:相同评价人/对象/事项的重复提交按更新处理,不产生重复记录
            # 信任分级:曾被忽略的标签再次被打 → 重新进入待放行(再次通知本人)
            existing.created_at = datetime.now(timezone.utc)
            if existing.status == "ignored":
                existing.status = "pending"
                existing.resolved_at = None
            _sync_review_to_agent_tags(db, person_id=body.personId, tag=tag, active=True,
                                       approval="pending" if existing.status == "pending" else "approved")
            first = first or existing
            continue
        review = PeerReview(
            id=uuid.uuid4().hex[:12],
            person_id=body.personId,
            reviewer_id=user.id,
            tag_name=tag,
            status="pending",  # 信任分级:他人标签需被评价人放行后才获全权重
        )
        db.add(review)
        _sync_review_to_agent_tags(db, person_id=body.personId, tag=tag, active=True,
                                   approval="pending")
        first = first or review
    # 发事件:agent-service 消费后重建该人员的 OKF/RAG 索引(画像进知识检索)
    emit_publish_event(db, PERSON_CHANGED, body.personId, created_by=user.id)
    db.commit()
    db.refresh(first)
    return _review_to_response(first)


@router.get("/pending", summary="Pending Reviews", description="我收到的待放行标签(信任分级通知)")
def get_pending_reviews(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    rows = db.query(PeerReview).filter(
        PeerReview.person_id == user.id, PeerReview.status == "pending",
    ).order_by(PeerReview.created_at.desc()).all()
    return [{
        "id": r.id,
        "tag": r.tag_name,
        "reviewerId": r.reviewer_id,
        "reviewer": r.reviewer_user.name if r.reviewer_user else None,
        "date": str(r.created_at.date()) if r.created_at else "",
    } for r in rows]


@router.post("/{review_id}/approve", summary="Approve Review", description="放行标签(本人/管理员):升全权重并归入我的负责领域")
def approve_review(review_id: str, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    review = db.query(PeerReview).filter(PeerReview.id == review_id).first()
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="标签不存在")
    if review.person_id != user.id and user.system_role != "管理员":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有被评价本人或管理员可放行")
    if review.status != "pending":
        return {"ok": True, "status": review.status}

    review.status = "approved"
    review.resolved_at = datetime.now(timezone.utc)
    # 1) agent 体系:peer_review 标签升为已放行(尽力而为,失败不影响业务)
    try:
        with db.begin_nested():
            db.execute(
                text("UPDATE agent.person_tags pt SET approval='approved'"
                     " FROM agent.raw_tags rt"
                     " WHERE pt.tag_id=rt.tag_id AND rt.normalized_text=:n"
                     "   AND pt.person_id=:p AND pt.source='peer_review'"),
                {"n": " ".join(review.tag_name.split()).lower(), "p": review.person_id})
    except Exception:  # noqa: BLE001
        logger.warning("他画像标签放行同步 Agent 体系失败(已忽略): review=%s", review_id, exc_info=True)
    # 2) 归入本人负责领域(走 self 全量同步;domains 去重追加)
    target = db.query(User).filter(User.id == review.person_id).first()
    if target is not None:
        domains = list(target.domains or [])
        if review.tag_name not in domains:
            domains.append(review.tag_name)
            target.domains = domains
            sync_person_domain_tags(db, person_id=target.id, domains=domains)
    emit_publish_event(db, PERSON_CHANGED, review.person_id, created_by=user.id)
    db.commit()
    return {"ok": True, "status": "approved"}


@router.post("/{review_id}/ignore", summary="Ignore Review", description="忽略标签(保持低权重,不删除)")
def ignore_review(review_id: str, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    review = db.query(PeerReview).filter(PeerReview.id == review_id).first()
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="标签不存在")
    if review.person_id != user.id and user.system_role != "管理员":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有被评价本人或管理员可操作")
    review.status = "ignored"
    review.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "status": "ignored"}


@router.get("/sent", summary="Get Sent Reviews", description="我发出的标签")
def get_sent_reviews(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    q = db.query(PeerReview).filter(PeerReview.reviewer_id == user.id)
    total = q.count()
    items = q.order_by(PeerReview.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return [_review_to_response(r).model_dump() for r in items]


@router.get("/person/{person_id}", response_model=PersonTagSummary, summary="Get Person Tags", description="某人的标签汇总")
def get_person_tags(person_id: str, db: Session = Depends(get_db)):
    reviews = db.query(PeerReview).filter(PeerReview.person_id == person_id).all()
    tags = list(set(r.tag_name for r in reviews))
    return PersonTagSummary(person_id=person_id, tags=tags, tag_count=len(tags))


@router.get("/person/{person_id}/history", summary="Get Person Review History", description="某人的标签历史（含评价人信息）")
def get_person_review_history(
    person_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    q = db.query(PeerReview).filter(PeerReview.person_id == person_id)
    total = q.count()
    items = q.order_by(PeerReview.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    result = [_review_to_response(r) for r in items]
    pages = (total + page_size - 1) // page_size if total > 0 else 1
    return PaginatedResponse(items=result, total=total, page=page, page_size=page_size, pages=pages)


@router.delete("/{review_id}", summary="Delete Review", description="删除标签")
def delete_review(review_id: str, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    review = db.query(PeerReview).filter(PeerReview.id == review_id).first()
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="标签不存在")
    if review.reviewer_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能删除自己发出的标签")
    db.delete(review)
    _sync_review_to_agent_tags(db, person_id=review.person_id, tag=review.tag_name, active=False)
    emit_publish_event(db, PERSON_CHANGED, review.person_id, created_by=user.id)
    db.commit()
    return {"message": "已删除"}
