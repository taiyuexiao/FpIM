"""Knowledge MCP Server(V1.2 §12.1)。

对 Agent 暴露 8 个只读知识工具;Agent 不直连 rag schema 与 OKF 仓库,
一切知识访问经此服务。调用强制携带可信 user_context(无则拒绝),
每次调用写 mcp_call_logs(同一 trace_id 串联,§15.1)。

V1 传输形态:进程内直连(同一接口,后续可替换 stdio/HTTP 传输,§23)。
"""
from __future__ import annotations

import json
import time

from app.contracts.agent_state import UserContext
from app.contracts.errors import AgentError, ErrorCode
from app.contracts.mcp import McpTool, ResponsibilityRecord
from app.core import db
from app.okf.repository import OkfRepository
from app.rag.retriever import HybridRetriever


def _shared_token(a: str, b: str) -> bool:
    """语义兜底防误伤闸:两个字符串需有实质词元重叠(CJK 2-gram 或拉丁词)。
    如 堡垒机 vs 大模型网关与API Key → 无重叠 → 不当作正式责任返回。"""
    import re
    a, b = a.lower(), b.lower()
    latin_a = set(re.findall(r"[a-z0-9+#.]{2,}", a))
    latin_b = set(re.findall(r"[a-z0-9+#.]{2,}", b))
    if latin_a & latin_b:
        return True
    for i in range(len(a) - 1):
        gram = a[i:i + 2]
        if any('一' <= ch <= '鿿' for ch in gram) and gram in b:
            return True
    return False


class KnowledgeMcpServer:
    """知识 MCP 服务。8 个只读工具。"""

    def __init__(self, retriever: HybridRetriever | None = None,
                 repository: OkfRepository | None = None) -> None:
        self._retriever = retriever or HybridRetriever()
        self._repo = repository or OkfRepository()

    async def call(self, tool: McpTool, params: dict, *,
                   user_context: UserContext | None, trace_id: str) -> dict:
        """统一入口:权限校验 → 路由 → 日志。"""
        start = time.time()
        if user_context is None:
            raise AgentError(ErrorCode.AUTH_ERROR, "MCP 调用必须携带可信 user_context(§12.1)")
        handler = getattr(self, f"_{tool.value}", None)
        if handler is None:
            raise AgentError(ErrorCode.MCP_ERROR, f"未知 MCP 工具: {tool}")
        ok, result, error = True, None, None
        try:
            result = await handler(params, user_context)
        except AgentError as e:
            ok, error = False, e
            result = e.to_payload(trace_id).model_dump()
        latency = round((time.time() - start) * 1000, 2)
        # 调用日志(失败不阻断业务)
        try:
            await db.execute(
                "INSERT INTO agent.mcp_call_logs(trace_id, tool, params, ok, latency_ms)"
                " VALUES($1,$2,$3,$4,$5)",
                trace_id, tool.value, json.dumps(params, ensure_ascii=False, default=str),
                ok, latency)
        except Exception:  # noqa: BLE001
            pass
        if not ok:
            raise error
        return result

    # ---------------- 8 个工具 ----------------

    async def _search_knowledge(self, params: dict, ctx: UserContext) -> dict:
        """知识检索:knowledge_qa 的主入口(§10.10)。"""
        query = params.get("query", "").strip()
        if not query:
            raise AgentError(ErrorCode.INPUT_ERROR, "search_knowledge 缺少 query")
        hits = await self._retriever.retrieve(query, ctx, top_k=int(params.get("top_k", 5)))
        return {"hits": [h.model_dump() for h in hits], "has_evidence": bool(hits)}

    async def _get_document(self, params: dict, ctx: UserContext) -> dict:
        """按 ID 取 Published OKF 文档(含版本与来源)。"""
        doc_id = params.get("document_id", "")
        doc = await self._repo.get_latest(doc_id)
        if doc is None:
            raise AgentError(ErrorCode.RAG_ERROR, f"文档不存在: {doc_id}")
        return {"metadata": doc.metadata.model_dump(), "body": doc.body, "extra": doc.extra}

    async def _get_responsibility(self, params: dict, ctx: UserContext) -> dict:
        """正式责任查询(§9.4):按概念名/标题检索 Published ResponsibilityItem。"""
        names = params.get("concept_names") or ([params["concept_name"]] if params.get("concept_name") else [])
        if not names:
            raise AgentError(ErrorCode.INPUT_ERROR, "get_responsibility 缺少 concept_name(s)")
        records: list[ResponsibilityRecord] = []
        # 责任文档确定性标题匹配(责任文档量小,精确优先;§9.4 正式责任查询必须可靠)
        published = await self._repo.list_published()
        resp_docs = [d for d in published if d.metadata.type.value == "responsibilities"]
        matched = [d for d in resp_docs
                   if any(n in d.metadata.title or n in d.body for n in names)]
        # 标题未命中时回退混合检索(语义兜底;防误伤闸:标题与查询名须有实质词元重叠)
        if not matched:
            for name in names:
                hits = await self._retriever.retrieve(name, ctx, top_k=10)
                for h in hits:
                    if h.document_type == "responsibilities":
                        doc = await self._repo.get_latest(h.document_id)
                        if doc and doc not in matched and _shared_token(name, doc.metadata.title):
                            matched.append(doc)
        for doc in matched:
            e = doc.extra
            records.append(ResponsibilityRecord(
                responsibility_id=doc.metadata.id,
                title=doc.metadata.title,
                intake_department=e.get("intake_department", ""),
                owner_department=e.get("owner_department", ""),
                owner_person_id=e.get("owner_person_id", ""),
                owner_role=e.get("owner_role", ""),
                time_limit=e.get("time_limit", ""),
                transfer_condition=e.get("transfer_condition", ""),
                escalation_path=e.get("escalation_path", ""),
                source_uri=doc.metadata.source_uri,
                version=doc.metadata.version,
            ))
        # 按 document_id 去重
        seen, unique = set(), []
        for r in records:
            if r.responsibility_id not in seen:
                seen.add(r.responsibility_id)
                unique.append(r)
        return {"responsibilities": [r.model_dump() for r in unique]}

    async def _get_person_profile(self, params: dict, ctx: UserContext) -> dict:
        """人员画像(PersonProfile OKF,§10.4 边界已过滤动态标签)。"""
        person_id = params.get("person_id", "")
        doc = await self._repo.get_latest(f"person-{person_id}")
        if doc is None:
            raise AgentError(ErrorCode.RAG_ERROR, f"人员画像不存在: {person_id}")
        return {"metadata": doc.metadata.model_dump(), "body": doc.body}

    async def _get_process(self, params: dict, ctx: UserContext) -> dict:
        """流程知识检索。"""
        name = params.get("name", "").strip()
        if not name:
            raise AgentError(ErrorCode.INPUT_ERROR, "get_process 缺少 name")
        hits = await self._retriever.retrieve(name, ctx, top_k=3)
        process_hits = [h for h in hits if h.document_type == "processes"]
        return {"processes": [h.model_dump() for h in process_hits],
                "note": "当前知识库暂无流程类文档" if not process_hits else ""}

    async def _find_related_knowledge(self, params: dict, ctx: UserContext) -> dict:
        """相关知识:以文档标题为查询,召回同类型其他文档。"""
        doc_id = params.get("document_id", "")
        doc = await self._repo.get_latest(doc_id)
        if doc is None:
            raise AgentError(ErrorCode.INPUT_ERROR, f"文档不存在: {doc_id}")
        hits = await self._retriever.retrieve(doc.metadata.title, ctx, top_k=6)
        related = [h for h in hits if h.document_id != doc_id][:5]
        return {"related": [h.model_dump() for h in related]}

    async def _list_sources(self, params: dict, ctx: UserContext) -> dict:
        """来源清单:Published OKF 按类型统计。"""
        ids = await self._repo.list_published_ids()
        by_type: dict[str, int] = {}
        for i in ids:
            prefix = i.split("-", 1)[0]
            by_type[prefix] = by_type.get(prefix, 0) + 1
        return {"total": len(ids), "by_type": by_type, "ids": sorted(ids)}

    async def _knowledge_health(self, params: dict, ctx: UserContext) -> dict:
        """知识健康度:发布数、索引版本、chunk 数、模型版本。"""
        ids = await self._repo.list_published_ids()
        version = await db.fetchval("SELECT active_version FROM rag.rag_index_pointer WHERE id=1")
        n_docs = await db.fetchval(
            "SELECT count(*) FROM rag.rag_documents WHERE index_version=$1 AND status='active'",
            version)
        n_chunks = await db.fetchval(
            "SELECT count(*) FROM rag.rag_chunks WHERE index_version=$1", version)
        model = await db.fetchval(
            "SELECT DISTINCT embedding_model FROM rag.rag_chunks WHERE index_version=$1", version)
        return {
            "published_okf": len(ids), "active_index_version": version,
            "indexed_documents": n_docs, "indexed_chunks": n_chunks,
            "embedding_model": model,
            "ok": len(ids) == (n_docs or 0),
        }
