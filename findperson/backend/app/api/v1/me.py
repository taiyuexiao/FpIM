"""当前用户"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...middleware.deps import get_current_user
from ...schemas.people import PersonResponse, PersonUpdateRequest
from ...models.user import User
from ...services.publish_event import emit_publish_event, PERSON_CHANGED
from ...services.tag_sync import sync_person_domain_tags

router = APIRouter(prefix="/me", tags=["当前用户"])


@router.get("", response_model=PersonResponse, summary="Get Me", description="当前登录用户信息")
def get_me(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    return user


@router.put("/profile", response_model=PersonResponse, summary="Update My Profile", description="更新当前用户自己的资料")
def update_my_profile(body: PersonUpdateRequest, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    update_data = body.model_dump(exclude_unset=True)
    # 映射 camelCase → snake_case
    field_map = {
        "departmentId": "department_id",
        "selfPortrait": "self_portrait",
        "systemRole": "system_role",
        "managerId": "manager_id",
    }
    for camel, snake in field_map.items():
        if camel in update_data:
            update_data[snake] = update_data.pop(camel)
    for key, value in update_data.items():
        setattr(user, key, value)
    # 负责领域变更:同步 Agent 标签体系(source=self),立即参与结构化检索(验收#6)
    if "domains" in update_data:
        sync_person_domain_tags(db, person_id=user.id, domains=user.domains or [])
    # 资料/领域变更:发事件,agent-service 消费后重建该人员 OKF/RAG 索引
    if update_data.keys() & {"domains", "self_portrait", "contact", "role"}:
        emit_publish_event(db, PERSON_CHANGED, user.id, created_by=user.id)
    db.commit()
    db.refresh(user)
    return user
