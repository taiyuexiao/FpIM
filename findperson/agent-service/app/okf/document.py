"""OKF 文档的序列化与解析:YAML frontmatter + Markdown 正文。

OKF 是治理后的正式知识发布物(V1.2 §10.1):元数据 13 必备字段在 frontmatter,
正文用 Markdown 表达人和模型都容易理解的知识。
"""
from __future__ import annotations

import re

import yaml

from app.contracts.okf import OkfDocument, OkfMetadata, OkfStatus, OkfType, Visibility

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def to_markdown(doc: OkfDocument) -> str:
    """OkfDocument → frontmatter + 正文的 Markdown 文本。"""
    meta = doc.metadata
    data = {
        "type": meta.type.value,
        "id": meta.id,
        "title": meta.title,
        "version": meta.version,
        "status": meta.status.value,
        "visibility": meta.visibility.value,
        "sensitivity": meta.sensitivity,
        "source_type": meta.source_type,
        "source_id": meta.source_id,
        "source_uri": meta.source_uri,
        "owner_department_id": meta.owner_department_id,
        "updated_at": meta.updated_at,
        "content_hash": meta.content_hash,
    }
    if doc.extra:
        data["extra"] = doc.extra
    fm = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    return f"---\n{fm}---\n\n{doc.body.strip()}\n"


def from_markdown(text: str) -> OkfDocument:
    """解析 OKF Markdown 文件,还原 OkfDocument。"""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError("缺少 YAML frontmatter,不是合法 OKF 文档")
    data = yaml.safe_load(m.group(1))
    body = text[m.end():].strip()
    extra = data.pop("extra", {}) or {}
    meta = OkfMetadata(
        type=OkfType(data["type"]),
        id=data["id"],
        title=data["title"],
        version=int(data["version"]),
        status=OkfStatus(data["status"]),
        visibility=Visibility(data["visibility"]),
        sensitivity=int(data["sensitivity"]),
        source_type=data.get("source_type", ""),
        source_id=data.get("source_id", ""),
        source_uri=data.get("source_uri", ""),
        owner_department_id=data.get("owner_department_id"),
        updated_at=float(data.get("updated_at", 0)),
        content_hash=data.get("content_hash", ""),
    )
    return OkfDocument(metadata=meta, body=body, extra=extra)
