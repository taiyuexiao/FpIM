from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models.user import User


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """从请求状态中提取当前用户（需先经过 AuthMiddleware）"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # 04-方案 §3.1：token 版本比对（改密/登出递增后旧 token 立即失效）
    ver = getattr(request.state, "token_ver", 0)
    if (user.token_version or 0) != (ver or 0):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态已失效，请重新登录")

    return user


def require_admin(request: Request):
    """要求管理员角色"""
    role = getattr(request.state, "user_role", "")
    if role != "管理员":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
