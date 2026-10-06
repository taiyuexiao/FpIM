"""OKF Publisher(V1.2 §10.2)。

把业务事实/原始知识转换为 Candidate OKF,经校验链后发布为 Published OKF:
  业务数据或原始知识变化
    → 生成 Candidate OKF
    → YAML Schema 校验
    → Stable ID 校验
    → Source 校验
    → Visibility / Sensitivity 校验
    → 链接完整性校验
    → content_hash 计算
    → Published OKF(写仓库)
    → 触发 RAG 增量索引(模块 23 接管,本模块只发事件)

Publisher 不负责向量召回,也不负责 Agent 推荐排序。
发布失败不能污染当前可查询版本(§10.2 验收):先全部校验通过,再写仓库。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.contracts.errors import AgentError, ErrorCode
from app.contracts.okf import (
    OkfDocument, OkfMetadata, OkfStatus, OkfType, Visibility,
)

_ID_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9-]*$")  # 允许大写(外部系统 ID 如 P0001/A00001)
# OKF 目录(复数)→ 文档 ID 前缀(单数)映射
TYPE_ID_PREFIX = {
    "responsibilities": "responsibility",
    "people": "person",
    "departments": "department",
    "processes": "process",
    "policies": "policy",
    "faqs": "faq",
    "contents": "content",
    "relationships": "relationship",
}
REQUIRED_METADATA_FIELDS = (
    "type", "id", "title", "version", "status", "visibility", "sensitivity",
    "source_type", "source_id", "source_uri", "owner_department_id",
    "updated_at", "content_hash",
)


@dataclass
class PublishResult:
    """单份文档的发布结果。"""

    document_id: str
    published: bool
    version: int = 0
    content_hash: str = ""
    changed: bool = True       # 相对上一版是否有变化(§10.6 增量判断)
    errors: list[str] = field(default_factory=list)


class OkfValidator:
    """OKF 校验链(§10.2 六步)。全部通过才能发布。"""

    def validate(self, doc: OkfDocument, *, known_ids: set[str] | None = None) -> list[str]:
        """返回错误列表(空 = 通过)。"""
        errors: list[str] = []
        meta = doc.metadata

        # 1) YAML Schema 校验:13 必备字段
        for f in REQUIRED_METADATA_FIELDS:
            value = getattr(meta, f, None)
            if value is None or (isinstance(value, str) and not value and f not in ("content_hash",)):
                if f in ("source_uri",):  # source_uri 允许发布前为空,发布时由仓库回填
                    continue
                errors.append(f"schema: 必备字段缺失或为空: {f}")
        if not doc.body.strip():
            errors.append("schema: 正文为空")
        if meta.version < 1:
            errors.append("schema: version 必须 >= 1")

        # 2) Stable ID 校验:小写短横线、带类型前缀、可长期稳定
        if not _ID_RE.match(meta.id):
            errors.append(f"stable_id: 非法 ID 格式: {meta.id}")
        expected_prefix = TYPE_ID_PREFIX[meta.type.value]
        if not meta.id.startswith(expected_prefix + "-"):
            errors.append(f"stable_id: ID 应以 {expected_prefix}- 为前缀: {meta.id}")

        # 3) Source 校验:必须能反查业务来源
        if meta.status == OkfStatus.PUBLISHED:
            if not meta.source_type or not meta.source_id:
                errors.append("source: Published OKF 必须具有 source_type/source_id")

        # 4) Visibility / Sensitivity 校验
        if meta.visibility not in tuple(Visibility):
            errors.append(f"visibility: 非法值: {meta.visibility}")
        if not (0 <= meta.sensitivity <= 3):
            errors.append(f"sensitivity: 必须在 0~3: {meta.sensitivity}")

        # 5) 链接完整性校验:extra 中声明的 related_okf_ids 必须存在
        if known_ids is not None:
            for rid in doc.extra.get("related_okf_ids", []):
                if rid not in known_ids:
                    errors.append(f"link: 引用的 OKF 不存在: {rid}")
        return errors


class OkfPublisher:
    """OKF 发布器:构建 Candidate → 校验 → 写仓库。"""

    def __init__(self, repository, validator: OkfValidator | None = None) -> None:
        self._repo = repository          # OkfRepository(模块 20)
        self._validator = validator or OkfValidator()

    async def publish(self, doc: OkfDocument) -> PublishResult:
        """发布单份文档。校验失败不污染仓库(§10.2 验收)。"""
        meta = doc.metadata
        # content_hash 计算(校验链最后一步前置:hash 参与 schema 完整性)
        meta.content_hash = meta.compute_hash(doc.body)

        known_ids = await self._repo.list_published_ids()
        errors = self._validator.validate(doc, known_ids=known_ids)
        if errors:
            return PublishResult(document_id=meta.id, published=False, errors=errors)

        # 增量判断:与仓库中旧版 content_hash 相同则跳过(§10.6)
        old = await self._repo.get_latest(meta.id)
        if old and old.metadata.content_hash == meta.content_hash:
            return PublishResult(document_id=meta.id, published=True,
                                 version=old.metadata.version,
                                 content_hash=meta.content_hash, changed=False)

        meta.status = OkfStatus.PUBLISHED
        meta.version = (old.metadata.version + 1) if old else 1
        path = await self._repo.write(doc)
        return PublishResult(document_id=meta.id, published=True,
                             version=meta.version,
                             content_hash=meta.content_hash, changed=True,
                             errors=[] if path else ["repository: 写入失败"])
