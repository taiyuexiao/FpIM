"""OKF 契约(V1.2 §10.1 OKF 知识模型 + §11.3 Chunk 输出)。

OKF 是治理后的正式知识发布物;RAG 索引是它的派生物。
"""
from __future__ import annotations

import hashlib
import time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class OkfType(str, Enum):
    """知识类型(§10.1 目录:knowledge-okf/ 下 8 类)。"""

    RESPONSIBILITY = "responsibilities"
    PEOPLE = "people"
    DEPARTMENT = "departments"
    PROCESS = "processes"
    POLICY = "policies"
    FAQ = "faqs"
    CONTENT = "contents"
    RELATIONSHIP = "relationships"


class OkfStatus(str, Enum):
    """发布状态。"""

    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


class Visibility(str, Enum):
    """可见范围。"""

    INTERNAL = "internal"        # 全员可见
    DEPARTMENT = "department"    # 所属部门可见
    RESTRICTED = "restricted"    # 受限


class OkfMetadata(BaseModel):
    """Published OKF 必备元数据(V1.2 §10.1 的 13 个字段)。"""

    type: OkfType
    id: str                       # 唯一稳定 ID
    title: str
    version: int = 1
    status: OkfStatus = OkfStatus.DRAFT
    visibility: Visibility = Visibility.INTERNAL
    sensitivity: int = 0          # 敏感级别,权限过滤用
    source_type: str = ""         # 业务来源类型,如 public.responsibility_assignments
    source_id: str = ""           # 业务来源主键
    source_uri: str = ""          # 反查业务来源的 URI
    owner_department_id: int | None = None
    updated_at: float = Field(default_factory=time.time)
    content_hash: str = ""

    def compute_hash(self, body: str) -> str:
        """按正文计算 content_hash(§10.2 校验链的一步;§10.6 增量判断用)。"""
        return hashlib.sha256(body.encode("utf-8")).hexdigest()


class OkfDocument(BaseModel):
    """一份 OKF 文档 = 元数据(frontmatter)+ Markdown 正文。"""

    metadata: OkfMetadata
    body: str                     # Markdown 正文,人和模型都容易理解
    extra: dict[str, Any] = Field(default_factory=dict)  # 类型专有字段(如责任时限、转办条件)


class RagChunk(BaseModel):
    """RAG 切片输出(§10.7 Chunker 输出字段)。"""

    chunk_id: str
    document_id: str
    section_path: str = ""
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    token_count: int = 0
