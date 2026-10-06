"""私聊代理委托接口（二期 R2）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...middleware.deps import get_current_user
from ...models.user import User
from ...services import agent_proxy

router = APIRouter(tags=["私聊代理"])


class DelegationIn(BaseModel):
    mode: str   # off | draft | auto


@router.get("/im/conversations/{cid}/delegation", summary="读取代理设置")
def get_delegation(cid: int, request: Request, db: Session = Depends(get_db)):
    get_current_user(request, db)
    return {"item": agent_proxy.get_delegation(db, cid)}


@router.put("/im/conversations/{cid}/delegation", summary="设置私聊代理",
            description="off=关闭 / draft=仅起草 / auto=未读期间自动处理")
def set_delegation(cid: int, body: DelegationIn, request: Request,
                   db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    try:
        return {"item": agent_proxy.set_delegation(db, cid, user.id, body.mode)}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
