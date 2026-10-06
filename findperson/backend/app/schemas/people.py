from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class DepartmentBrief(BaseModel):
    """部门简要信息"""
    id: int
    name: str

    model_config = {"from_attributes": True}


class PersonResponse(BaseModel):
    """人员详情响应(camelCase 序列化对齐前端;populate_by_name 保持内部 snake_case 构造可用)"""
    id: str
    account: str
    name: str
    phone: str | None = None
    email: str | None = None
    system_role: str = Field(alias="systemRole")
    department_id: int | None = Field(default=None, alias="departmentId")
    # 前端以字符串消费部门(与 auth/me 返回一致);ORM Department 对象在 validator 中转 name
    department: str | None = None
    role: str | None = None
    contact: str | None = None
    domains: list | None = None
    self_portrait: str | None = Field(default=None, alias="selfPortrait")
    completeness: int
    recommended_count: int = Field(alias="recommendedCount")
    active: bool
    manager_id: str | None = Field(default=None, alias="managerId")  # 直接上级人员 ID
    last_login_at: datetime | None = Field(default=None, alias="lastLoginAt")
    created_at: datetime | None = Field(default=None, alias="createdAt")

    model_config = {"from_attributes": True, "populate_by_name": True}

    @field_validator("department", mode="before")
    @classmethod
    def _dept_to_name(cls, v):
        if v is None or isinstance(v, str):
            return v
        return getattr(v, "name", None)


class PersonCreateRequest(BaseModel):
    """新增成员(管理员)"""
    name: str = Field(min_length=1, max_length=64)
    account: str | None = Field(None, max_length=64)
    password: str | None = Field(None, min_length=6, max_length=64)
    phone: str | None = Field(None, max_length=20)
    departmentId: int | None = None
    role: str | None = Field(None, max_length=128)
    contact: str | None = Field(None, max_length=64)
    systemRole: str | None = None
    active: bool | None = None
    managerId: str | None = None

    model_config = {"populate_by_name": True}


class PersonUpdateRequest(BaseModel):
    """更新人员信息（可选字段全部可空，支持 camelCase 别名以兼容前端）"""
    phone: str | None = Field(None, max_length=20)
    name: str | None = Field(None, min_length=1, max_length=64)
    departmentId: int | None = None
    role: str | None = Field(None, max_length=128)
    contact: str | None = Field(None, max_length=64)
    domains: list[str] | None = None
    selfPortrait: str | None = None
    systemRole: str | None = None
    active: bool | None = None
    managerId: str | None = None  # 直接上级(管理员可改)

    model_config = {"populate_by_name": True}
