"""AGUI 会话收口：POST /agui/sessions + GET /agui/sessions/{id}/state"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...middleware.deps import get_current_user
from ...models.session import Session

router = APIRouter(prefix="/sessions", tags=["AGUI"])


@router.post("", summary="Create AGUI Session", description="新建问答会话")
def create_session(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    session = Session(id=uuid.uuid4().hex[:12], user_id=user.id, title="新对话")
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"id": session.id, "title": session.title, "userId": session.user_id}


@router.get("/{session_id}/state", summary="Get AGUI Session State", description="查询会话状态快照")
def get_state(session_id: str, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    session = db.query(Session).filter(Session.id == session_id, Session.user_id == user.id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {
        "id": session.id,
        "title": session.title,
        "summary": session.summary,
        "turnCount": session.turn_count,
        "isActive": session.is_active,
    }
