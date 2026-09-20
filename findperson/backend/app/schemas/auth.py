from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """登录请求"""
    account: str = Field(..., min_length=1, max_length=64, description="账号")
    password: str = Field(..., min_length=1, max_length=128, description="密码")


class LoginResponse(BaseModel):
    """登录响应（字段名对齐前端）"""
    token: str
    user: dict


class RegisterRequest(BaseModel):
    """注册请求（管理员创建用户）"""
    account: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)
    phone: str | None = Field(None, max_length=20)
    department_id: int | None = None
    system_role: str = Field("普通成员")


class ChangePasswordRequest(BaseModel):
    """修改密码"""
    old_password: str
    new_password: str = Field(..., min_length=6, max_length=128)
