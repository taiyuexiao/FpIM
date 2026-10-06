"""人员证据契约(V1.2 §12.1 PersonEvidence 统一证据模型)。

不同来源的证据保留各自语义,不能只剩一个浮点数。
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class EvidenceType(str, Enum):
    """证据类型(V1.2 §12.1)。"""

    FORMAL_ASSIGNMENT = "formal_assignment"        # 正式责任(OKF ResponsibilityItem)
    EXPLICIT_SELF_TAG = "explicit_self_tag"        # 精确自填负责领域
    INFERRED_FROM_PROFILE = "inferred_from_profile"  # 画像推断
    INFERRED_FROM_REVIEW = "inferred_from_review"    # 评价叙述推断
    INFERRED_FROM_ARTICLE = "inferred_from_article"  # 文章作者专业证据
    DIRECTORY_MATCH = "directory_match"            # 通讯录匹配


class PersonEvidence(BaseModel):
    """统一人员证据模型(V1.2 §12.1 字段)。"""

    person_id: str
    concept_id: str | None = None
    relation_type: str          # formal_assignment / self_declared_scope / article_expertise / ...
    evidence_type: EvidenceType
    source_type: str            # raw_tag / okf_responsibility / okf_profile / okf_content / directory
    source_id: str = ""
    confidence: float = 0.0
    verification_status: str = "active"
    freshness: float | None = None     # 证据时间戳
    relation_path: list[str] = Field(default_factory=list)  # concept 扩展路径,可写 Trace
    # 保留原始证据用于解释与分层
    detail: dict = Field(default_factory=dict)
