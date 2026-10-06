"""Chunker(V1.2 §10.7)。

按 document_type 使用独立切片策略:
  责任事项 → 定义/职责/步骤/条件/时限/依据/转办(按小标题行切)
  人物     → 正式职责、自画像、项目经历、评价正文分别切(按段落)
  流程     → 完整阶段
  制度     → 条款
  FAQ      → 一问一答
  文章     → Markdown section
  关系     → 单条或小组关系叙述

文章章节 > 500 中文字符时继续按句子切分,保留 overlap。
Chunk 保留来源和 section_path,不能丢失权限和版本元数据。
"""
from __future__ import annotations

import re

from app.contracts.okf import OkfDocument, RagChunk

MAX_SECTION_CHARS = 500
OVERLAP_CHARS = 50
# 大致估算中文字符 token 数(V1 够用;真实 tokenizer 后续接入)
def _token_count(text: str) -> int:
    return len(text)


_SENTENCE_SPLIT = re.compile(r"(?<=[。!?;!?;])\s*")
_SECTION_HEADER = re.compile(r"^(#{1,6}\s+.+|[^\n]{0,30}:)\s*$", re.MULTILINE)


def _split_long_text(text: str, *, max_chars: int = MAX_SECTION_CHARS,
                     overlap: int = OVERLAP_CHARS) -> list[str]:
    """长文本按句子续切,保留 overlap(§10.7)。"""
    if len(text) <= max_chars:
        return [text]
    sentences = _SENTENCE_SPLIT.split(text)
    chunks: list[str] = []
    current = ""
    for s in sentences:
        if current and len(current) + len(s) > max_chars:
            chunks.append(current)
            current = current[-overlap:] + s if overlap else s
        else:
            current += s
    if current.strip():
        chunks.append(current)
    return chunks


def _split_by_markdown_sections(body: str) -> list[tuple[str, str]]:
    """按 Markdown 标题/小标题行切分,返回 (section_path, content) 列表。"""
    sections: list[tuple[str, str]] = []
    current_title = "正文"
    current: list[str] = []
    for line in body.splitlines():
        if re.match(r"^#{1,6}\s", line) or re.match(r"^[^\n:：]{2,30}[:：]$", line.strip()):
            if current:
                sections.append((current_title, "\n".join(current).strip()))
            current_title = line.strip().lstrip("#").strip().rstrip(":：")
            current = []
        else:
            current.append(line)
    if current:
        sections.append((current_title, "\n".join(current).strip())
    )
    return [(t, c) for t, c in sections if c]


class Chunker:
    """OKF 文档切片器。每种 document_type 独立策略,可独立单测(§10.7 验收)。"""

    def chunk(self, doc: OkfDocument) -> list[RagChunk]:
        """按类型切片,返回带完整元数据的 RagChunk 列表。"""
        doc_type = doc.metadata.type.value
        if doc_type == "responsibilities":
            sections = self._chunk_responsibility(doc)
        elif doc_type == "people":
            sections = self._chunk_person(doc)
        else:
            sections = self._split_generic(doc)

        chunks: list[RagChunk] = []
        index = 0
        for section_path, content in sections:
            for piece in _split_long_text(content):
                if not piece.strip():
                    continue
                chunks.append(RagChunk(
                    chunk_id=f"{doc.metadata.id}-c{index:03d}",
                    document_id=doc.metadata.id,
                    section_path=section_path,
                    content=piece.strip(),
                    metadata=self._chunk_metadata(doc, section_path),
                    token_count=_token_count(piece),
                ))
                index += 1
        return chunks

    # ---------------- 类型策略 ----------------

    def _chunk_responsibility(self, doc: OkfDocument) -> list[tuple[str, str]]:
        """责任事项:首段定义 + 按「- 字段:」行逐条切(定义/职责/条件/时限/转办/升级)。"""
        sections: list[tuple[str, str]] = []
        lines = doc.body.splitlines()
        definition: list[str] = []
        for line in lines:
            if line.strip().startswith("- "):
                key = line.strip()[2:].split(":", 1)[0].split(":", 1)[0]
                sections.append((key, line.strip()[2:]))
            else:
                definition.append(line)
        if any(d.strip() for d in definition):
            sections.insert(0, ("定义", "\n".join(definition).strip()))
        return sections

    def _chunk_person(self, doc: OkfDocument) -> list[tuple[str, str]]:
        """人物:按段落标题分别切(正式职责/自我介绍/同事评价)。"""
        return _split_by_markdown_sections(doc.body)

    def _split_generic(self, doc: OkfDocument) -> list[tuple[str, str]]:
        """流程/制度/FAQ/文章/部门/关系:Markdown section 切分。"""
        sections = _split_by_markdown_sections(doc.body)
        if not sections:
            sections = [("正文", doc.body)]
        return sections

    def _chunk_metadata(self, doc: OkfDocument, section_path: str) -> dict:
        """Chunk 元数据:权限与版本信息一个都不能丢(§10.7 验收)。"""
        meta = doc.metadata
        return {
            "okf_type": meta.type.value,
            "title": meta.title,
            "okf_version": meta.version,
            "content_hash": meta.content_hash,
            "source_uri": meta.source_uri,
            "owner_department_id": meta.owner_department_id,
            "visibility": meta.visibility.value,
            "sensitivity": meta.sensitivity,
            "section": section_path,
            **({"author_person_id": doc.extra["author_person_id"]}
               if doc.extra.get("author_person_id") else {}),
            **({"owner_person_id": doc.extra["owner_person_id"]}
               if doc.extra.get("owner_person_id") else {}),
        }
