"""概念体系契约(V1.2 §7):RawTag / PersonTag / Concept / 映射 / 关系 / 审核 / 人员概念证据。

对应阶段 0 冻结清单:RawTag Schema、PersonTag Schema、Concept Schema、
TagConceptMap Schema、Concept Review Schema。
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- 枚举

class ConceptType(str, Enum):
    """概念类型(V1.2 §7.2 建议值)。"""

    SYSTEM = "system"
    PLATFORM = "platform"
    SERVICE = "service"
    PROJECT = "project"
    PRODUCT = "product"
    FRAMEWORK = "framework"
    TOOLKIT = "toolkit"
    CAPABILITY = "capability"
    DUTY = "duty"
    SYMPTOM = "symptom"
    DOMAIN = "domain"
    RESOURCE = "resource"


class ConceptStatus(str, Enum):
    """概念状态。Candidate 与正式 Concept 严格隔离(V1.2 §7.5)。"""

    SEED = "seed"            # 冷启动种子
    CANDIDATE = "candidate"  # 候选,待人工审核
    ACTIVE = "active"        # 正式
    DEPRECATED = "deprecated"


class MappingType(str, Enum):
    """映射类型(V1.2 §7.4)。禁止把语义相近全部处理成 alias。"""

    EXACT_ALIAS = "exact_alias"
    NEAR_ALIAS = "near_alias"
    INSTANCE_OF = "instance_of"
    NARROWER_THAN = "narrower_than"
    BROADER_THAN = "broader_than"
    RELATED_TO = "related_to"
    AMBIGUOUS = "ambiguous"


class LinkDecision(str, Enum):
    """LLM 受约束消歧的可选输出(V1.2 §7.4)。"""

    LINK_EXISTING = "LINK_EXISTING"
    CREATE_CANDIDATE = "CREATE_CANDIDATE"
    AMBIGUOUS = "AMBIGUOUS"
    REJECT = "REJECT"


class RelationType(str, Enum):
    """Concept 关系白名单(V1.2 §7.7)。"""

    NARROWER_THAN = "narrower_than"
    BROADER_THAN = "broader_than"
    RELATED_TO = "related_to"
    CALLS = "calls"
    DEPENDS_ON = "depends_on"
    RUNS_ON = "runs_on"
    LIMITED_BY = "limited_by"
    COMPONENT_OF = "component_of"
    ROUTES_TO = "routes_to"


class ReviewAction(str, Enum):
    """Candidate Concept 审核动作(V1.2 §7.5)。"""

    APPROVE = "approve"              # 批准为正式 Concept
    MERGE = "merge"                  # 合并到已有 Concept
    RENAME_APPROVE = "rename_approve"  # 改名后批准
    AS_ALIAS = "as_alias"            # 降级为 Alias
    REJECT = "reject"


class TagSource(str, Enum):
    """标签来源(V1.2 §7.1:自填/他人评价/管理员录入保存在 person_tags 关系层)。"""

    SELF = "self"
    PEER_REVIEW = "peer_review"
    ADMIN = "admin"


# ---------------------------------------------------------------- 核心模型

class RawTag(BaseModel):
    """原始负责领域标签(§7.1):员工自由填写的原文,系统不得用 Concept 覆盖。"""

    tag_id: str
    text: str                 # 用户原始文本,原样保留
    normalized_text: str      # 规范化文本(去空白/小写),同一规范化文本只对应一个 RawTag
    created_at: float = Field(default_factory=time.time)

    @staticmethod
    def normalize(text: str) -> str:
        """规范化:压缩空白并统一小写,用于判重。"""
        return " ".join(text.split()).lower()


class PersonTag(BaseModel):
    """人—标签关系(§7.1/§7.3)。"""

    person_tag_id: str
    person_id: str
    tag_id: str
    source: TagSource = TagSource.SELF
    created_by: str = ""      # 谁填写的(自填=本人,评价=评价人)
    is_active: bool = True
    created_at: float = Field(default_factory=time.time)


class Concept(BaseModel):
    """Canonical Concept(§7.2 Schema)。员工语言与用户语言的统一语义接口。"""

    concept_id: str
    canonical_name: str
    concept_type: ConceptType = ConceptType.DOMAIN
    description: str = ""
    scope_department_id: int | None = None
    status: ConceptStatus = ConceptStatus.ACTIVE
    embedding_model: str = ""
    version: int = 1
    valid_from: float = Field(default_factory=time.time)
    valid_to: float | None = None
    # Candidate Concept 专有(§7.5)
    suggested_name: str = ""
    source_tags: list[str] = Field(default_factory=list)


class ConceptAlias(BaseModel):
    """已确认的标准别名(§7.3 第二级召回)。"""

    alias_id: str
    concept_id: str
    alias: str                # 规范化后的别名文本
    created_at: float = Field(default_factory=time.time)


class TagConceptMap(BaseModel):
    """RawTag → Concept 映射(§7.4 产出)。必须带 mapping_type 与置信度。"""

    map_id: str
    tag_id: str
    concept_id: str
    mapping_type: MappingType
    confidence: float
    generated_by: str         # rule / llm / human
    review_status: str = "auto_approved"  # auto_approved / pending / approved / rejected
    reason: str = ""
    created_at: float = Field(default_factory=time.time)


class ConceptRelation(BaseModel):
    """Concept 间关系(§7.7)。只说明概念间关系,不证明某人正式负责。"""

    relation_id: str
    src_concept_id: str
    dst_concept_id: str
    relation_type: RelationType
    created_at: float = Field(default_factory=time.time)


class ConceptReviewItem(BaseModel):
    """审核队列条目(§7.5):低置信映射、歧义映射、Candidate Concept、异常。"""

    review_id: str
    item_type: str            # low_confidence_mapping / ambiguous_mapping / candidate_concept / anomaly
    payload: dict[str, Any] = Field(default_factory=dict)
    status: str = "pending"   # pending / resolved / rejected
    resolution: dict[str, Any] | None = None
    created_at: float = Field(default_factory=time.time)
    resolved_at: float | None = None


class PersonConceptEvidence(BaseModel):
    """人员—概念证据(§9.2):低成本、确定性的结构化召回索引。

    relation_type 不得命名为 responsible_for —— 自填负责领域不是正式组织责任(§7.9)。
    """

    person_id: str
    concept_id: str
    relation_type: str = "self_declared_scope"
    evidence_type: str = "explicit_self_tag"
    source_type: str = "raw_tag"
    source_id: str = ""
    source_raw_tag: str = ""  # 保留原始 RawTag 用于解释(§9.2 验收)
    confidence: float = 0.0
    verification_status: str = "active"


class ConceptCandidate(BaseModel):
    """候选概念召回结果(§7.3 统一 Candidate 输出)。"""

    concept_id: str
    candidate_source: str     # exact / alias / historical / pg_trgm / vector
    candidate_score: float
    matched_text: str = ""
    canonical_name: str = ""
