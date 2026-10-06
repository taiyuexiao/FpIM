"""部门管理"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...middleware.deps import get_current_user, require_admin
from ...models.department import Department
from ...models.user import User
from ...schemas.departments import (
    DepartmentCreateRequest, DepartmentUpdateRequest,
    DepartmentResponse, DepartmentTreeNode, ResponsibilityUpdateRequest,
)
from ...services.publish_event import emit_publish_event, PERSON_CHANGED

router = APIRouter(prefix="/departments", tags=["部门"])


def _build_tree(db: Session, dept: Department) -> DepartmentTreeNode:
    member_count = db.query(User).filter(User.department_id == dept.id).count()
    leader_name = db.query(User.name).filter(User.id == dept.leader_id).scalar() if dept.leader_id else None
    children = [
        _build_tree(db, c)
        for c in db.query(Department).filter(Department.parent_id == dept.id).order_by(Department.sort_order).all()
    ]
    return DepartmentTreeNode(
        id=dept.id, name=dept.name, level=dept.level,
        parent_id=dept.parent_id, leader_id=dept.leader_id,
        leader_name=leader_name, responsibility=dept.responsibility,
        status=dept.status, sort_order=dept.sort_order,
        children=children, member_count=member_count,
    )


@router.get("/tree", summary="Department Tree", description="部门树（含成员数）")
def department_tree(db: Session = Depends(get_db)):
    roots = db.query(Department).filter(Department.parent_id == None).order_by(Department.sort_order).all()
    return [_build_tree(db, r) for r in roots]


@router.get("/{dept_id}", response_model=DepartmentResponse, summary="Get Department", description="部门详情")
def get_department(dept_id: int, db: Session = Depends(get_db)):
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部门不存在")
    return dept


@router.patch("/{dept_id}", response_model=DepartmentResponse, summary="Update Department", description="更新部门")
def update_department(dept_id: int, body: DepartmentUpdateRequest, request: Request, db: Session = Depends(get_db)):
    require_admin(request)  # v4 §十:部门维护仅管理员
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部门不存在")
    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(dept, key, value)
    # 负责人变更联动(v4 §十):成员上级指向新负责人;新负责人上级指向父部门负责人
    changed_person_ids = set()
    if "leader_id" in update_data:
        new_leader = update_data.get("leader_id")
        parent_leader = None
        if dept.parent_id:
            parent = db.query(Department).filter(Department.id == dept.parent_id).first()
            parent_leader = parent.leader_id if parent else None

        members = db.query(User).filter(User.department_id == dept_id)
        member_ids = {u.id for u in members.all()}

        if new_leader:
            members.filter(User.id != new_leader).update(
                {"manager_id": new_leader}, synchronize_session=False)
            changed_person_ids.update(member_ids - {new_leader})
            leader_user = db.query(User).filter(User.id == new_leader).first()
            if leader_user and parent_leader and parent_leader != new_leader:
                leader_user.manager_id = parent_leader
                changed_person_ids.add(new_leader)
        else:
            # 负责人被清空:成员上级回退到父部门负责人(无则置空)
            fallback = parent_leader if parent_leader else None
            members.update({"manager_id": fallback}, synchronize_session=False)
            changed_person_ids.update(member_ids)

    db.commit()
    db.refresh(dept)

    # 触发人员变更事件,供 agent-service 增量更新 OKF/RAG
    for person_id in changed_person_ids:
        emit_publish_event(db, PERSON_CHANGED, person_id, created_by=getattr(request.state, "user_id", None))
    if changed_person_ids:
        db.commit()

    return dept


@router.patch("/{dept_id}/responsibility", response_model=DepartmentResponse, summary="Update Department Responsibility", description="部门负责人编辑职责(仅负责人,非负责人/管理员不可)")
def update_department_responsibility(dept_id: int, body: ResponsibilityUpdateRequest, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部门不存在")
    if dept.leader_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有部门负责人可编辑部门职责")
    dept.responsibility = body.responsibility
    db.commit()
    db.refresh(dept)
    return dept


@router.post("", response_model=DepartmentResponse, status_code=201, summary="Create Department", description="创建部门")
def create_department(body: DepartmentCreateRequest, request: Request, db: Session = Depends(get_db)):
    require_admin(request)  # v4 §十:部门维护仅管理员
    # 现有数据可能跳过序列,显式分配 id 避免主键冲突
    next_id = (db.query(sa_func.max(Department.id)).scalar() or 0) + 1
    dept = Department(id=next_id, **body.model_dump())
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return dept
