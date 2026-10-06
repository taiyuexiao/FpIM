from datetime import date, datetime
from pydantic import BaseModel, Field


class ContentCreateRequest(BaseModel):
    """创建 / 提交内容"""
    title: str = Field(..., min_length=1, max_length=256)
    tags: list[str] = []
    summary: str = Field(default="", max_length=2000)  # 默认允许为空(未明确要求不填;可在右侧栏手动补)
    body: str | None = None
    status: str | None = None  # 前端传中文，如"待审核"


class ContentUpdateRequest(BaseModel):
    """更新内容（前端传完整记录，含 status / auditTrail / pinned 等）"""
    title: str | None = Field(None, min_length=1, max_length=256)
    tags: list[str] | None = None
    summary: str | None = None
    body: str | None = None
    status: str | None = None
    pinned: bool | None = None
    publishedAt: str | None = None
    auditTrail: list | None = None
    publishedSnapshot: dict | None = None

    model_config = {"populate_by_name": True}


class ContentAuditRequest(BaseModel):
    """审核操作"""
    action: str = Field(..., pattern=r"^(approve|reject)$")
    reason: str | None = None


class ContentResponse(BaseModel):
    """内容详情（字段名对齐前端 camelCase）"""
    id: str
    ownerId: str = Field(..., alias="ownerId")
    ownerName: str | None = Field(None, alias="ownerName")
    title: str
    tags: list | None = None
    summary: str
    body: str | None = None
    status: str
    version: int
    pinned: bool
    publishedAt: date | None = Field(None, alias="publishedAt")
    submittedAt: datetime | None = Field(None, alias="submittedAt")
    auditTrail: list | None = Field(None, alias="auditTrail")
    publishedSnapshot: dict | None = Field(None, alias="publishedSnapshot")
    weeklyQueryCount: int = Field(0, alias="weeklyQueryCount")
    weeklyRecommendCount: int = Field(0, alias="weeklyRecommendCount")
    createdAt: datetime | None = Field(None, alias="createdAt")
    updatedAt: datetime | None = Field(None, alias="updatedAt")

    model_config = {"from_attributes": True, "populate_by_name": True}


class ContentBrief(BaseModel):
    """内容列表项（字段名对齐前端 camelCase）"""
    id: str
    ownerId: str = Field(..., alias="ownerId")
    ownerName: str | None = Field(None, alias="ownerName")
    title: str
    tags: list | None = None
    summary: str
    body: str | None = None
    status: str
    version: int
    pinned: bool
    publishedAt: date | None = Field(None, alias="publishedAt")
    submittedAt: datetime | None = Field(None, alias="submittedAt")
    auditTrail: list | None = Field(None, alias="auditTrail")
    createdAt: datetime | None = Field(None, alias="createdAt")
    updatedAt: datetime | None = Field(None, alias="updatedAt")

    model_config = {"from_attributes": True, "populate_by_name": True}
