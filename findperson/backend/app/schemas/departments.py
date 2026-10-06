from datetime import datetime
from pydantic import BaseModel, Field


class DepartmentCreateRequest(BaseModel):
    """创建部门"""
    name: str = Field(..., min_length=1, max_length=64)
    level: int = Field(..., ge=1)
    parent_id: int | None = None
    leader_id: str | None = None
    responsibility: str | None = None
    sort_order: int = 0


class DepartmentUpdateRequest(BaseModel):
    """更新部门"""
    name: str | None = Field(None, min_length=1, max_length=64)
    leader_id: str | None = None
    responsibility: str | None = None
    status: str | None = None
    sort_order: int | None = None


class ResponsibilityUpdateRequest(BaseModel):
    """部门职责更新（仅部门负责人可编辑）"""
    responsibility: str | None = None


class DepartmentResponse(BaseModel):
    """部门详情"""
    id: int
    name: str
    level: int
    parent_id: int | None = None
    leader_id: str | None = None
    path: list | None = None
    responsibility: str | None = None
    status: str
    sort_order: int
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class DepartmentTreeNode(BaseModel):
    """部门树节点"""
    id: int
    name: str
    level: int
    parent_id: int | None = None
    leader_id: str | None = None
    leader_name: str | None = None
    responsibility: str | None = None
    status: str
    sort_order: int
    children: list["DepartmentTreeNode"] = []
    member_count: int = 0

    model_config = {"from_attributes": True}
