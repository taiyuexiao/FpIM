"""内容管理"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...middleware.deps import get_current_user, require_admin
from ...models.content import Content
from ...models.user import User
from ...services.publish_event import (
    CONTENT_CHANGED, CONTENT_DELETED, CONTENT_PUBLISHED, emit_publish_event,
)
from ...schemas.contents import (
    ContentCreateRequest,
    ContentUpdateRequest,
    ContentAuditRequest,
    ContentResponse,
)

router = APIRouter(prefix="/contents", tags=["内容"])

# 状态中文→英文映射
_STATUS_MAP = {
    "draft": "草稿",
    "pending_review": "待审核",
    "published": "已发布",
    "rejected": "已驳回",
}
_STATUS_REVERSE = {v: k for k, v in _STATUS_MAP.items()}

# PUT 请求 camelCase → snake_case 映射
_FIELD_MAP = {
    "auditTrail": "audit_trail",
    "publishedSnapshot": "published_snapshot",
    "ownerId": "owner_id",
    "ownerName": "owner_name",
    "submittedAt": "submitted_at",
    "publishedAt": "published_at",
    "weeklyQueryCount": "weekly_query_count",
    "weeklyRecommendCount": "weekly_recommend_count",
}


def _content_to_response(c: Content) -> ContentResponse:
    """将 ORM 对象转为 ContentResponse（含中文状态 + camelCase）"""
    return ContentResponse(
        id=c.id,
        ownerId=c.owner_id,
        ownerName=c.owner.name if c.owner else None,
        title=c.title,
        tags=c.tags or [],
        summary=c.summary or "",
        body=c.body,
        status=_STATUS_MAP.get(c.status, c.status),
        version=c.version,
        pinned=c.pinned,
        publishedAt=c.published_at,
        submittedAt=c.submitted_at,
        auditTrail=c.audit_trail or [],
        publishedSnapshot=c.published_snapshot,
        weeklyQueryCount=c.weekly_query_count or 0,
        weeklyRecommendCount=c.weekly_recommend_count or 0,
        createdAt=c.created_at,
        updatedAt=c.updated_at,
    )


@router.get("", summary="List Contents", description="内容列表（分页）")
def list_contents(
    status_q: str | None = Query(None, alias="status", description="draft | pending_review | published | rejected"),
    owner_id: str | None = None,
    pinned: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),  # 问答详情/人员主页需拉全量(当前数据量级 620)
    db: Session = Depends(get_db),
):
    q = db.query(Content).filter(Content.is_deleted == False)
    if status_q:
        q = q.filter(Content.status == status_q)
    if owner_id:
        q = q.filter(Content.owner_id == owner_id)
    if pinned is not None:
        q = q.filter(Content.pinned == pinned)
    total = q.count()
    items = q.order_by(Content.pinned.desc(), Content.updated_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    return [_content_to_response(c).model_dump() for c in items]


@router.post("", response_model=ContentResponse, status_code=201, summary="Create Content", description="创建内容")
def create_content(
    body: ContentCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    # 生成内容 ID：C + 5 位序号
    max_seq = db.query(sa_func.max(Content.id)).filter(Content.id.like("C%")).scalar()
    seq = int(max_seq[1:]) + 1 if max_seq else 1
    content_id = f"C{seq:05d}"

    # 状态映射
    eng_status = _STATUS_REVERSE.get(body.status, "draft") if body.status else "draft"

    now = datetime.now(timezone.utc)
    content = Content(
        id=content_id,
        owner_id=user.id,
        title=body.title,
        tags=body.tags or [],
        summary=body.summary,
        body=body.body,
        status=eng_status,
        submitted_at=now if eng_status == "pending_review" else None,
    )
    if eng_status == "published":
        # 直接以已发布创建(管理端/导入):补 published_at 并发索引事件,与审核通过链路语义一致
        content.published_at = (now + timedelta(hours=8)).date()
        emit_publish_event(db, CONTENT_PUBLISHED, content.id, created_by=user.id)
    db.add(content)
    db.commit()
    if eng_status == "published":
        # 文章自打标签回流为声明类证据(tag_sync,尽力而为不阻断)
        from ...services.tag_sync import sync_article_tags
        sync_article_tags(db, person_id=user.id)
        db.commit()
    db.refresh(content)
    return _content_to_response(content)


@router.get("/{content_id}", response_model=ContentResponse, summary="Get Content", description="内容详情")
def get_content(content_id: str, db: Session = Depends(get_db)):
    content = db.query(Content).filter(Content.id == content_id, Content.is_deleted == False).first()
    if not content:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="内容不存在")
    return _content_to_response(content)


@router.put("/{content_id}", response_model=ContentResponse, summary="Update Content", description="编辑内容")
@router.patch("/{content_id}", response_model=ContentResponse, summary="Update Content", description="编辑内容")
def update_content(
    content_id: str,
    body: ContentUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    content = db.query(Content).filter(Content.id == content_id, Content.is_deleted == False).first()
    if not content:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="内容不存在")

    update_data = body.model_dump(exclude_unset=True)
    # 映射 camelCase → snake_case
    for camel, snake in _FIELD_MAP.items():
        if camel in update_data:
            update_data[snake] = update_data.pop(camel)

    # 状态中文→英文
    if "status" in update_data and update_data["status"] in _STATUS_REVERSE:
        update_data["status"] = _STATUS_REVERSE[update_data["status"]]

    # v4 §六:已发布内容被实质性修改时,保留对外公开快照并转入待审核,
    # 审核通过前外部仍只见旧版本(快照以前端消费形态存储:camelCase + 中文状态)
    substantive = any(k in update_data for k in ("title", "summary", "body", "tags"))
    was_published = content.status == "published"
    if was_published and substantive:
        content.published_snapshot = {
            "id": content.id, "ownerId": content.owner_id,
            "ownerName": content.owner.name if content.owner else None,
            "title": content.title, "tags": content.tags or [],
            "summary": content.summary or "", "body": content.body,
            "status": "已发布",
            "publishedAt": content.published_at.isoformat() if content.published_at else None,
            "version": content.version, "auditTrail": content.audit_trail or [],
        }
        content.status = "pending_review"
        content.submitted_at = datetime.now(timezone.utc)

    # 处理 published_at（字符串 → date）
    if "published_at" in update_data and isinstance(update_data["published_at"], str):
        from datetime import date as dt_date
        try:
            update_data["published_at"] = dt_date.fromisoformat(update_data["published_at"])
        except (ValueError, TypeError):
            update_data["published_at"] = None

    for key, value in update_data.items():
        setattr(content, key, value)

    content.version += 1
    if was_published and substantive:
        # 发布变更事件(rag.publish_events,供增量重建索引消费)
        emit_publish_event(db, CONTENT_CHANGED, content.id, created_by=user.id)
    db.commit()
    # 文章标签回流(标签编辑/转待审核撤下均按最新已发布并集重算)
    from ...services.tag_sync import sync_article_tags
    sync_article_tags(db, person_id=content.owner_id)
    db.commit()
    db.refresh(content)
    return _content_to_response(content)


@router.delete("/{content_id}", summary="Delete Content", description="软删除内容")
def delete_content(content_id: str, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    content = db.query(Content).filter(Content.id == content_id, Content.is_deleted == False).first()
    if not content:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="内容不存在")
    if content.owner_id != user.id and user.system_role != "管理员":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作")
    if content.status == "published":
        emit_publish_event(db, CONTENT_DELETED, content.id, created_by=user.id)
    content.is_deleted = True
    db.commit()
    # 删除后重算作者已发布标签并集(该文标签若无其他已发布文章覆盖则停用)
    from ...services.tag_sync import sync_article_tags
    sync_article_tags(db, person_id=content.owner_id)
    db.commit()
    return {"message": "已删除"}


@router.post("/{content_id}/submit", response_model=ContentResponse, summary="Submit Content", description="提交审核")
def submit_content(content_id: str, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    content = db.query(Content).filter(Content.id == content_id, Content.is_deleted == False).first()
    if not content:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="内容不存在")
    content.status = "pending_review"
    content.submitted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(content)
    return _content_to_response(content)


@router.post("/{content_id}/audit", response_model=ContentResponse, summary="Audit Content", description="审核内容（通过 / 驳回）")
def audit_content(
    content_id: str,
    body: ContentAuditRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    require_admin(request)  # v4 §十:内容审核仅管理员
    user = get_current_user(request, db)
    content = db.query(Content).filter(Content.id == content_id, Content.is_deleted == False).first()
    if not content:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="内容不存在")

    new_status = "published" if body.action == "approve" else "rejected"

    # 审核轨迹（北京时间，精确到秒）
    trail = list(content.audit_trail) if content.audit_trail else []
    now = datetime.now(timezone.utc)
    beijing_now = now + timedelta(hours=8)
    trail.append({
        "operator": user.id,
        "operated_at": beijing_now.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "result": new_status,
        "reason": body.reason or "",
    })
    content.audit_trail = trail
    content.status = new_status

    if new_status == "published":
        content.published_at = beijing_now.date()
        content.version += 1
        emit_publish_event(db, CONTENT_PUBLISHED, content.id, created_by=user.id)

    db.commit()
    # 审核通过/驳回后重算作者已发布标签并集
    from ...services.tag_sync import sync_article_tags
    sync_article_tags(db, person_id=content.owner_id)
    db.commit()
    db.refresh(content)
    return _content_to_response(content)


@router.post("/{content_id}/pin", response_model=ContentResponse, summary="Toggle Pin", description="切换置顶状态")
def toggle_pin(content_id: str, request: Request, db: Session = Depends(get_db)):
    require_admin(request)  # v4 §十:置顶仅管理员
    user = get_current_user(request, db)
    content = db.query(Content).filter(Content.id == content_id, Content.is_deleted == False).first()
    if not content:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="内容不存在")
    content.pinned = not content.pinned
    db.commit()
    db.refresh(content)
    return _content_to_response(content)
