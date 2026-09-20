"""认证路由：登录 / 注册 / 改密"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.security import hash_password, verify_password, create_token
from ...models.user import User
from ...schemas.auth import LoginRequest, LoginResponse, RegisterRequest, ChangePasswordRequest

router = APIRouter(prefix="/auth", tags=["认证"])


def _user_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "account": user.account,
        "name": user.name,
        "phone": user.phone,
        "systemRole": user.system_role,
        "department": user.department.name if user.department else None,
        "departmentId": user.department_id,
        "role": user.role,
        "contact": user.contact,
        "domains": user.domains or [],
        "selfPortrait": user.self_portrait,
        "completeness": user.completeness,
        "recommendedCount": user.recommended_count,
        "active": user.active,
        "managerId": user.manager_id,
    }


@router.post("/login", response_model=LoginResponse, summary="Login", description="账号密码登录")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    # 登录按用户 id 匹配，大小写不敏感、去首尾空格；不再接受手机号/account
    # 两边都 upper()：种子账号是 PXXXX，register 生成的 id 是小写 hex，单边 upper 会对不上
    account = body.account.strip()
    user = db.query(User).filter(func.upper(User.id) == account.upper()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")
    if not user.active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已停用,请联系管理员")
    token = create_token(user.id, user.system_role)
    return {"token": token, "user": _user_to_dict(user)}


@router.post("/register", summary="Register", description="管理员创建用户")
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.account == body.account).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="账号已存在")
    user = User(
        account=body.account,
        name=body.name,
        password_hash=hash_password(body.password),
        phone=body.phone,
        department_id=body.department_id,
        system_role=body.system_role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "account": user.account, "name": user.name}


@router.post("/change-password", summary="Change Password", description="修改自己的密码")
def change_password(body: ChangePasswordRequest, request: Request, db: Session = Depends(get_db)):
    from ...middleware.deps import get_current_user
    user = get_current_user(request, db)
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="原密码不正确")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"message": "密码已修改"}
