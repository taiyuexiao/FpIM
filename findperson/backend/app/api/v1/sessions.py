"""会话管理"""
import uuid

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...middleware.deps import get_current_user
from ...models.session import Session, Message
from ...schemas.sessions import SessionResponse, MessageResponse, PaginatedResponse

router = APIRouter(prefix="/sessions", tags=["会话"])


class SessionCreateRequest(BaseModel):
    """前端创建会话(允许携带前端本地生成的 id,保持路由/状态一致)。"""
    id: str | None = None
    title: str = "新会话"


class SessionUpdateRequest(BaseModel):
    """会话补丁(标题/摘要/轮次/激活态)。"""
    title: str | None = None
    summary: str | None = None
    turnCount: int | None = None
    is_active: bool | None = None


@router.post("", status_code=201, summary="Create Session", description="新建会话")
def create_session(body: SessionCreateRequest, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    session = Session(id=body.id or uuid.uuid4().hex[:12], user_id=user.id, title=body.title)
    db.add(session)
    db.commit()
    db.refresh(session)
    return SessionResponse.model_validate(session)


@router.patch("/{session_id}", summary="Update Session", description="更新会话标题/摘要/轮次")
def update_session(session_id: str, body: SessionUpdateRequest,
                   request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    session = db.query(Session).filter(Session.id == session_id,
                                       Session.user_id == user.id).first()
    if not session:
        # 前端本地会话尚未落库:补丁即创建(幂等,避免 404 打断问答流)
        session = Session(id=session_id, user_id=user.id)
        db.add(session)
    data = body.model_dump(exclude_unset=True)
    if "turnCount" in data:
        data["turn_count"] = data.pop("turnCount")
    for key, value in data.items():
        setattr(session, key, value)
    db.commit()
    db.refresh(session)
    return SessionResponse.model_validate(session)


@router.delete("/{session_id}", summary="Delete Session", description="删除会话(软删除)")
def delete_session(session_id: str, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    session = db.query(Session).filter(Session.id == session_id,
                                       Session.user_id == user.id).first()
    if session:
        session.is_active = False
        db.commit()
    return {"ok": True}


@router.get("", summary="List Sessions", description="我的会话列表")
def list_sessions(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    q = db.query(Session).filter(Session.user_id == user.id, Session.is_active == True)
    total = q.count()
    items = q.order_by(Session.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    result = [SessionResponse.model_validate(s) for s in items]
    pages = (total + page_size - 1) // page_size if total > 0 else 1
    return PaginatedResponse(items=result, total=total, page=page, page_size=page_size, pages=pages)


@router.get("/{session_id}/messages", summary="List Messages", description="某会话的消息列表")
def list_messages(
    session_id: str,
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    get_current_user(request, db)
    q = db.query(Message).filter(Message.session_id == session_id)
    total = q.count()
    items = q.order_by(Message.created_at).offset((page - 1) * page_size).limit(page_size).all()
    result = [MessageResponse.model_validate(m) for m in items]
    pages = (total + page_size - 1) // page_size if total > 0 else 1
    return PaginatedResponse(items=result, total=total, page=page, page_size=page_size, pages=pages)
