from pydantic import BaseModel, Field, ConfigDict


class ReviewCreateRequest(BaseModel):
    """为他⼈打标签（支持 camelCase 别名以兼容前端）"""
    personId: str = Field(..., min_length=1, max_length=32)
    tag: str = Field(..., min_length=1, max_length=64)

    model_config = {"populate_by_name": True}


class ReviewResponse(BaseModel):
    """标签记录（字段名对齐前端 camelCase）"""
    id: str
    personId: str = Field(..., alias="personId")
    personName: str | None = Field(None, alias="personName")
    reviewerId: str = Field(..., alias="reviewerId")
    reviewer: str | None = Field(None, alias="reviewer")
    tag: str = Field(..., alias="tag")
    date: str | None = Field(None, alias="date")
    status: str = Field("approved", alias="status")  # pending/approved/ignored(信任分级)

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class PersonTagSummary(BaseModel):
    """某⼈的标签汇总"""
    person_id: str
    tags: list[str]
    tag_count: int
