"""RAG Indexer(V1.2 §10.6)。

只消费 Published OKF(§11.1 红线:原则上不直接消费业务表)。
变化判断:id + version + content_hash。
更新规则:
  新增        → 新增 rag_document + chunks
  正文修改    → 替换对应 chunks
  权限元数据变化 → 更新 metadata/filter
  删除/废止   → 旧索引失效
  全量 rebuild → new index_version → 完整验证(Smoke Test)→ 原子切换(rag_index_pointer)

索引模型版本化(§23):embedding_model 写入每个 chunk,不跨模型混写。
"""
from __future__ import annotations

import json
import time

from app.contracts.errors import AgentError, ErrorCode
from app.contracts.okf import OkfDocument
from app.core import db
from app.core.embedding_client import EmbeddingPort, get_rag_embedding
from app.rag.chunker import Chunker


def _vec_literal(vec: list[float]) -> str:
    return f"[{','.join(f'{x:.6f}' for x in vec)}]"


class RagIndexer:
    """RAG 索引器。"""

    def __init__(self, embedding: EmbeddingPort | None = None,
                 chunker: Chunker | None = None) -> None:
        self._emb = embedding or get_rag_embedding()
        self._chunker = chunker or Chunker()

    # ---------------- 全量重建(新版本 + 冒烟 + 原子切换)----------------

    async def rebuild(self, docs: list[OkfDocument]) -> dict:
        """全量重建到新 index_version,Smoke Test 通过后原子切换。"""
        if not docs:
            raise AgentError(ErrorCode.RAG_ERROR, "没有 Published OKF 可索引")
        job_id = f"job-{int(time.time() * 1000):x}"
        new_version = (await self._current_version()) + 1
        n_chunks = 0
        await db.execute(
            "INSERT INTO rag.rag_index_jobs(job_id, job_type, index_version, status)"
            " VALUES($1,'full_rebuild',$2,'running')", job_id, new_version)
        try:
            async with db.transaction() as conn:
                for doc in docs:
                    n_chunks += await self._write_document(conn, doc, new_version)
            await db.execute(
                "UPDATE rag.rag_index_jobs SET status='smoke_test', stats=$1 WHERE job_id=$2",
                json.dumps({"documents": len(docs), "chunks": n_chunks}), job_id)

            smoke = await self._smoke_test(new_version, expected_docs=len(docs))
            if not smoke["ok"]:
                await db.execute(
                    "UPDATE rag.rag_index_jobs SET status='failed', stats=$1 WHERE job_id=$2",
                    json.dumps(smoke), job_id)
                raise AgentError(ErrorCode.RAG_ERROR, f"索引 Smoke Test 失败: {smoke}")

            # 原子切换(§10.6)
            await db.execute(
                "UPDATE rag.rag_index_pointer SET active_version=$1, updated_at=now() WHERE id=1",
                new_version)
            await db.execute(
                "UPDATE rag.rag_index_jobs SET status='published', published_at=now() WHERE job_id=$1",
                job_id)
            return {"index_version": new_version, "documents": len(docs),
                    "chunks": n_chunks, "smoke": smoke, "job_id": job_id}
        except AgentError:
            raise
        except Exception as e:  # noqa: BLE001
            await db.execute(
                "UPDATE rag.rag_index_jobs SET status='failed' WHERE job_id=$1", job_id)
            raise AgentError(ErrorCode.RAG_ERROR, f"索引构建失败: {e}") from e

    # ---------------- 增量更新(§10.6 更新规则)----------------

    async def incremental(self, docs: list[OkfDocument]) -> dict:
        """对变更文档做增量更新(在当前生效版本上)。"""
        version = await self._current_version()
        if version == 0:
            return await self.rebuild(docs)
        stats = {"added": 0, "replaced": 0, "metadata_only": 0, "invalidated": 0, "skipped": 0}
        async with db.transaction() as conn:
            for doc in docs:
                meta = doc.metadata
                old = await conn.fetchrow(
                    "SELECT content_hash, okf_version FROM rag.rag_documents"
                    " WHERE document_id=$1 AND index_version=$2 AND status='active'",
                    meta.id, version)
                if old is None:
                    await self._write_document(conn, doc, version)     # 新增
                    stats["added"] += 1
                elif old["content_hash"] != meta.content_hash:
                    await self._replace_document(conn, doc, version)   # 正文修改
                    stats["replaced"] += 1
                elif old["okf_version"] != meta.version:
                    await conn.execute(                                # 仅元数据变化
                        "UPDATE rag.rag_documents SET okf_version=$1, visibility=$2,"
                        " sensitivity=$3, updated_at=now()"
                        " WHERE document_id=$4 AND index_version=$5",
                        meta.version, meta.visibility.value, meta.sensitivity,
                        meta.id, version)
                    stats["metadata_only"] += 1
                else:
                    stats["skipped"] += 1
        # OKF 中已不存在的文档:同步作废(否则孤儿文档会留在索引里被检索到)
        current = await db.fetch(
            "SELECT document_id FROM rag.rag_documents"
            " WHERE index_version=$1 AND status='active'", version)
        incoming = {d.metadata.id for d in docs}
        stale = [r["document_id"] for r in current if r["document_id"] not in incoming]
        if stale:
            stats["invalidated"] = await self.invalidate(stale)
        return {"index_version": version, **stats}

    async def invalidate(self, document_ids: list[str]) -> int:
        """删除/废止:旧索引失效(§10.6)。"""
        version = await self._current_version()
        result = await db.execute(
            "UPDATE rag.rag_documents SET status='invalidated', updated_at=now()"
            " WHERE document_id = ANY($1) AND index_version=$2 AND status='active'",
            document_ids, version)
        return int(result.split()[-1])

    # ---------------- 内部 ----------------

    async def _write_document(self, conn, doc: OkfDocument, version: int) -> int:
        meta = doc.metadata
        await conn.execute(
            "INSERT INTO rag.rag_documents(document_id, index_version, okf_type, title,"
            " okf_version, content_hash, source_uri, owner_department_id, visibility,"
            " sensitivity, status)"
            " VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'active')"
            " ON CONFLICT (document_id, index_version) DO UPDATE SET"
            " okf_version=EXCLUDED.okf_version, content_hash=EXCLUDED.content_hash,"
            " status='active', updated_at=now()",
            meta.id, version, meta.type.value, meta.title, meta.version,
            meta.content_hash, meta.source_uri, meta.owner_department_id,
            meta.visibility.value, meta.sensitivity)
        chunks = self._chunker.chunk(doc)
        vectors = await self._emb.embed_documents([c.content for c in chunks])
        for chunk, vec in zip(chunks, vectors):
            await conn.execute(
                "INSERT INTO rag.rag_chunks(chunk_id, index_version, document_id,"
                " section_path, content, metadata, token_count, embedding, embedding_model)"
                " VALUES($1,$2,$3,$4,$5,$6,$7,$8::vector,$9)"
                " ON CONFLICT (chunk_id, index_version) DO UPDATE SET"
                " content=EXCLUDED.content, metadata=EXCLUDED.metadata,"
                " embedding=EXCLUDED.embedding",
                chunk.chunk_id, version, chunk.document_id, chunk.section_path,
                chunk.content, json.dumps(chunk.metadata, ensure_ascii=False),
                chunk.token_count, _vec_literal(vec), self._emb.model_version)
        return len(chunks)

    async def _replace_document(self, conn, doc: OkfDocument, version: int) -> None:
        """正文修改:替换对应 chunks(§10.6)。"""
        await conn.execute(
            "DELETE FROM rag.rag_chunks WHERE document_id=$1 AND index_version=$2",
            doc.metadata.id, version)
        await self._write_document(conn, doc, version)

    async def _smoke_test(self, version: int, *, expected_docs: int) -> dict:
        """索引发布前验证(§10.6):文档数、chunk 覆盖、向量完整、样例可查。"""
        n_docs = await db.fetchval(
            "SELECT count(*) FROM rag.rag_documents WHERE index_version=$1 AND status='active'",
            version)
        n_chunks = await db.fetchval(
            "SELECT count(*) FROM rag.rag_chunks WHERE index_version=$1", version)
        no_vec = await db.fetchval(
            "SELECT count(*) FROM rag.rag_chunks WHERE index_version=$1 AND embedding IS NULL",
            version)
        no_chunk_docs = await db.fetchval(
            "SELECT count(*) FROM rag.rag_documents d WHERE d.index_version=$1"
            " AND NOT EXISTS (SELECT 1 FROM rag.rag_chunks c"
            "                WHERE c.document_id=d.document_id AND c.index_version=$1)",
            version)
        sample = await db.fetchval(
            "SELECT count(*) FROM rag.rag_chunks WHERE index_version=$1"
            " AND content ILIKE '%负责%' LIMIT 1", version)
        ok = (n_docs == expected_docs and n_chunks >= n_docs
              and no_vec == 0 and no_chunk_docs == 0 and (sample or 0) > 0)
        return {"ok": ok, "documents": n_docs, "chunks": n_chunks,
                "null_embeddings": no_vec, "docs_without_chunks": no_chunk_docs}

    async def _current_version(self) -> int:
        return await db.fetchval("SELECT active_version FROM rag.rag_index_pointer WHERE id=1") or 0

    async def current_version(self) -> int:
        """对外:当前生效索引版本。"""
        return await self._current_version()
