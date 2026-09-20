"""Hybrid Retriever(V1.2 §10.9)+ Knowledge QA Pipeline(§10.10)。

检索必须执行:
  权限预过滤
    → FTS/pg_trgm Top20  ‖  pgvector Top20
    → RRF 融合
    → 可选 Reranker(V1 默认关闭,§23)
    → 二次权限校验
    → 按文档/章节去重
    → Top5

RAG 返回知识片段和来源,不生成最终回答(§10.9)。
Knowledge QA:没有检索证据时不得根据 LLM 常识编造内部制度或流程(§10.10)。
"""
from __future__ import annotations

from app.contracts.agent_state import UserContext
from app.contracts.errors import AgentError, ErrorCode
from app.contracts.mcp import RagHit
from app.core import db
from app.core.embedding_client import EmbeddingPort, get_rag_embedding

RRF_K = 60
TOP_N_EACH = 20
TOP_K_FINAL = 5
# 向量腿噪声下限(实测:bge-small-zh 噪声底 asdfgh/你好≈0.51,真实词命中≥0.57)
# 低于下限的向量命中纯粹是「最近邻总存在」的假象,丢弃防垃圾输入配出名片
RAG_VECTOR_MIN_SIM = 0.55


def permission_clause(user_context: UserContext, start_index: int) -> tuple[str, list]:
    """可见性过滤(§10.9 权限预过滤;规则与仓库 knowledge-service 对齐)。

    - 匿名:仅 public;
    - 已认证:public/internal + 本部门 owner 或 allowed_departments 放行的 restricted;
    - 客户端自报部门不作数,department_id 必须来自可信 user_context。
    返回 (SQL 片段, 参数列表),SQL 中占位符从 start_index 开始。
    """
    if not user_context.user_id:
        return "d.visibility = 'public'", []
    dept = user_context.department_id
    if dept is None:
        return "d.visibility IN ('public','internal')", []
    return (
        f"(d.visibility IN ('public','internal')"
        f" OR d.owner_department_id = ${start_index}"
        f" OR d.allowed_departments @> to_jsonb(${start_index}::int))",
        [dept],
    )


def _vec_literal(vec: list[float]) -> str:
    return f"[{','.join(f'{x:.6f}' for x in vec)}]"


class HybridRetriever:
    """FTS/pg_trgm + pgvector 双路召回 + RRF 融合检索器。"""

    def __init__(self, embedding: EmbeddingPort | None = None) -> None:
        self._emb = embedding or get_rag_embedding()

    async def retrieve(
        self,
        query: str,
        user_context: UserContext,
        *,
        filters: dict | None = None,
        top_k: int = TOP_K_FINAL,
    ) -> list[RagHit]:
        """混合检索主入口。"""
        version = await self._active_version()
        if version == 0:
            raise AgentError(ErrorCode.RAG_ERROR, "RAG 索引尚未构建", degraded=True)

        # ---- 权限预过滤参数(§10.9 第一步:敏感级别 + 可见性) ----
        max_sensitivity = user_context.sensitivity_level
        perm_sql, perm_params = permission_clause(user_context, 4)
        limit_idx = 4 + len(perm_params)

        # ---- 路 1:FTS Top20 ----
        # 中文场景 pg_trgm 的 % 阈值(默认 0.3)会误杀短词命中(CJK 短串 trigram 少),
        # 因此采用 ILIKE 子串命中 + 低阈值 trgm 双通道,similarity 仅用于排序(§10.9)。
        # 多词检索式(链路把理解词项拼成空格分隔短句)按词 OR 匹配:
        # 整串 ILIKE 对拼接式必败(没有文档包含整串),逐词子串命中才符合
        #「任一词项相关即召回」的语义;单词查询保持原整串 ILIKE 行为。
        terms = [t for t in query.split() if len(t) >= 2]
        fts_params: list = [query, version, max_sensitivity, *perm_params]
        next_idx = limit_idx
        # 标题参与匹配:标题短、信号集中,trgm 在长 chunk 上被稀释时(尤其错别字/变体)
        # 标题 ILIKE 仍能命中;标题命中权重 ×2 排在内容命中之前
        title_expr = "COALESCE(c.metadata->>'title','')"
        if len(terms) > 1:
            content_conds, title_conds = [], []
            for t in terms:
                content_conds.append(f"c.content ILIKE '%' || ${next_idx} || '%'")
                title_conds.append(f"{title_expr} ILIKE '%' || ${next_idx} || '%'")
                fts_params.append(t)
                next_idx += 1
            match_sql = ("(" + " OR ".join(content_conds + title_conds)
                         + " OR similarity(c.content, $1) > 0.15"
                         + f" OR similarity({title_expr}, $1) > 0.15)")
            title_sum = " + ".join(f"({c})::int" for c in title_conds)
            content_sum = " + ".join(f"({c})::int" for c in content_conds)
            order_sql = f"(({title_sum}) * 2 + ({content_sum})) DESC, sim DESC"
        else:
            match_sql = (f"(c.content ILIKE '%' || $1 || '%' OR {title_expr} ILIKE '%' || $1 || '%'"
                         f" OR similarity(c.content, $1) > 0.15 OR similarity({title_expr}, $1) > 0.15)")
            order_sql = (f"({title_expr} ILIKE '%' || $1 || '%')::int * 2"
                         " + (c.content ILIKE '%' || $1 || '%')::int DESC, sim DESC")
        fts_rows = await db.fetch(
            "SELECT c.chunk_id, c.document_id, c.content, c.section_path, c.metadata,"
            "       similarity(c.content, $1) AS sim"
            " FROM rag.rag_chunks c"
            " JOIN rag.rag_documents d ON d.document_id = c.document_id"
            "      AND d.index_version = c.index_version"
            f" WHERE c.index_version = $2 AND d.status = 'active'"
            "   AND d.sensitivity <= $3"
            f"   AND {perm_sql}"
            f"   AND {match_sql}"
            f" ORDER BY {order_sql} LIMIT ${next_idx}",
            *fts_params, TOP_N_EACH,
        )

        # ---- 路 2:pgvector Top20(1536 维 RAG 向量空间) ----
        # Embedding 不可用时降级为关键词单路(§21 基线:Embedding 不可用时关键词检索可降级 100%)
        vec_rows = []
        try:
            vec = _vec_literal(await self._emb.embed_query(query))
            vec_rows = await db.fetch(
                "SELECT c.chunk_id, c.document_id, c.content, c.section_path, c.metadata,"
                "       1 - (c.embedding <=> $1::vector) AS sim"
                " FROM rag.rag_chunks c"
                " JOIN rag.rag_documents d ON d.document_id = c.document_id"
                "      AND d.index_version = c.index_version"
                f" WHERE c.index_version = $2 AND d.status = 'active'"
                "   AND d.sensitivity <= $3"
                f"   AND {perm_sql}"
                f"   AND (1 - (c.embedding <=> $1::vector)) >= {RAG_VECTOR_MIN_SIM}"
                f" ORDER BY c.embedding <=> $1::vector LIMIT ${limit_idx}",
                vec, version, max_sensitivity, *perm_params, TOP_N_EACH,
            )
        except Exception:  # noqa: BLE001 —— Embedding 故障:向量路降级,FTS 路继续
            import logging
            logging.getLogger(__name__).warning(
                "Embedding 不可用,RAG 降级为关键词单路检索")

        # ---- RRF 融合(§10.9) ----
        fused = self._rrf(fts_rows, vec_rows)

        # ---- 二次权限校验 + 按文档/章节去重(§10.9) ----
        results: list[RagHit] = []
        seen: set[str] = set()
        for row in fused:
            raw_meta = row["metadata"]
            if isinstance(raw_meta, str):  # asyncpg 默认把 jsonb 读成字符串
                import json as _json
                meta = _json.loads(raw_meta)
            else:
                meta = raw_meta or {}
            if int(meta.get("sensitivity", 0)) > max_sensitivity:
                continue  # 二次权限校验(防御性,正常预过滤已拦)
            dedup_key = f"{row['document_id']}#{row['section_path']}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            results.append(RagHit(
                document_id=row["document_id"],
                chunk_id=row["chunk_id"],
                document_type=str(meta.get("okf_type", "")),
                score=round(float(row["rrf_score"]), 6),
                content=row["content"],
                source_uri=str(meta.get("source_uri", "")),
                version=int(meta.get("okf_version", 1)),
                metadata=meta,
            ))
            if len(results) >= top_k:
                break

        # 检索日志(§17 rag_query_logs);失败不阻断
        try:
            await db.execute(
                "INSERT INTO rag.rag_query_logs(trace_id, query, hits)"
                " VALUES($1,$2,$3)",
                "standalone", query,
                __import__("json").dumps([r.model_dump() for r in results],
                                          ensure_ascii=False, default=str),
            )
        except Exception:  # noqa: BLE001
            pass
        return results

    def _rrf(self, fts_rows, vec_rows) -> list[dict]:
        """Reciprocal Rank Fusion:score = Σ 1/(k+rank)。"""
        scores: dict[str, dict] = {}

        def _add(rows, weight: float) -> None:
            for rank, row in enumerate(rows, 1):
                cid = row["chunk_id"]
                if cid not in scores:
                    scores[cid] = {"chunk_id": cid, "document_id": row["document_id"],
                                   "content": row["content"],
                                   "section_path": row["section_path"],
                                   "metadata": row["metadata"], "rrf_score": 0.0}
                scores[cid]["rrf_score"] += weight / (RRF_K + rank)

        # FTS 腿权重 2.0:关键词精确命中(如标题含 HarnessEval)必须压过
        # 纯向量近邻( embedding 空间漂移产生的语义邻居),否则文章类强命中
        # 会被人员画像的向量近邻挤掉(实测 HarnessEval case)
        _add(fts_rows, 2.0)
        _add(vec_rows, 1.0)
        return sorted(scores.values(), key=lambda r: r["rrf_score"], reverse=True)

    async def _active_version(self) -> int:
        return await db.fetchval("SELECT active_version FROM rag.rag_index_pointer WHERE id=1") or 0


class KnowledgeQAService:
    """Knowledge QA Pipeline(§10.10):检索 → 证据校验 → grounded answer。"""

    def __init__(self, retriever: HybridRetriever | None = None) -> None:
        self._retriever = retriever or HybridRetriever()

    async def answer(self, query: str, user_context: UserContext) -> dict:
        """知识问答:返回 {facts, citations, has_evidence}。

        没有检索证据时不得编造(§10.10):has_evidence=False,由 AnswerBuilder
        组织诚实的空答。最终自然语言组织归 AnswerBuilder/Hermes,RAG 不生成最终回答。
        """
        hits = await self._retriever.retrieve(query, user_context)
        if not hits:
            return {"facts": [], "citations": [], "has_evidence": False}
        citations = [
            {"document_id": h.document_id, "chunk_id": h.chunk_id,
             "version": h.version, "source_uri": h.source_uri,
             "content": h.content[:200]}
            for h in hits
        ]
        return {
            "facts": [h.content for h in hits],
            "citations": citations,
            "has_evidence": True,
        }
