"""知识检索节点(V1.2 §8.1 diagnostic/expert_finding 知识路)。

KnowledgeRetrievalNode:diagnostic / expert_finding 时经 MCP search_knowledge
取知识证据,经 RagEvidenceAdapter 转为人员证据;MCP 失败降级(结构化路径仍可用)。
contact_lookup / explicit_responsibility 不执行(§8.1:不执行无意义工具调用)。

架构收敛(查/写双轨):KnowledgeQANode 已删除;知识类问题由意图层映射为
find_person/expert_finding,经本节点取证据后以名片作答。
"""
from __future__ import annotations

import os
import re

from app.agent.orchestrator import AgentNode, ServiceRegistry
from app.contracts.agent_state import AgentState, Intent, QueryType, StateUpdate
from app.contracts.mcp import RagHit
from app.mcp_knowledge.client import KnowledgeMcpClient, get_mcp_client
from app.rag.evidence_adapter import RagEvidenceAdapter

_KNOWLEDGE_QUERY_TYPES = (QueryType.DIAGNOSTIC, QueryType.EXPERT_FINDING)
# 统一双路(chain.py 同款开关):所有查人类型都走 RAG 路
_ALWAYS_DUAL = os.getenv("RETRIEVAL_ALWAYS_DUAL", "1") == "1"

# 问法套话(不是检索词):从词项中滤除,防 ILIKE 整串失配稀释真实关键词
_QUERY_NOISE_TERMS = {
    "找谁", "谁负责", "谁懂", "谁会", "怎么办", "对接", "看看", "这块",
    "哥们", "把把关", "想问下", "请问", "该找谁", "想找", "上线前",
}
_QUERY_NOISE_RE = re.compile(r"(找谁|谁负责|谁懂|谁会|请问|怎么办|老是|一下|这块|哥们|对接|看看|想找|该找谁|把把关)")


class KnowledgeRetrievalNode(AgentNode):
    """知识路检索节点(find_person 双路之 RAG 路)。"""

    name = "KnowledgeRetrievalNode"
    timeout_ms = 8000
    on_error = "degrade"

    async def execute(self, state: AgentState, services: ServiceRegistry) -> StateUpdate:
        if state.intent.intent != Intent.FIND_PERSON:
            return StateUpdate()
        if not _ALWAYS_DUAL and state.intent.query_type not in _KNOWLEDGE_QUERY_TYPES:
            return StateUpdate()  # 旧路由(§8.1):contact_lookup/explicit_responsibility 不走 RAG

        mcp = services.get("mcp_client") if "mcp_client" in services.services else get_mcp_client()
        query = state.request.normalized_query or state.request.original_query
        # 统一双路:所有查人类型都用结构化关键词生成更短的检索式,提升 RAG 召回精度;
        # 词项为空(如寒暄)时回退原问句
        terms = (
            state.understanding.mentioned_systems
            + state.understanding.objects
            + state.understanding.symptoms
            + state.understanding.duty_clues
            + state.understanding.explicit_terms
            + [c.get("canonical_name", "") for c in state.concept.resolved_concepts]
        )
        short = " ".join(dict.fromkeys(t for t in terms if t and t not in _QUERY_NOISE_TERMS)).strip()
        if short:
            query = short
        else:
            # 词项为空或全是套话:剥离套话后按「英文词 + 中文二字组」生成兜底检索式,
            # 避免整句 ILIKE 必败(如「集群老是报警找谁」→「集群 报警」逐词 OR 命中)
            base = _QUERY_NOISE_RE.sub(" ", query)
            grams = re.findall(r"[A-Za-z][A-Za-z0-9]+|[\u4e00-\u9fff]{2}", base)
            if grams:
                query = " ".join(grams)
        update = StateUpdate()
        update.retrieval = state.retrieval.model_copy(deep=True)

        resp = await mcp.search_knowledge(
            query, user_context=state.request.user_context,
            trace_id=state.trace.trace_id, top_k=5,
        )
        if not resp.ok:
            # MCP 失败:路径 A 仍可用,显式降级(§12.2/§21 基线:MCP 不可用时路径 A 可降级 100%)
            update.retrieval.degraded_sources.append("mcp_search_knowledge")
            update.degraded = True
            return update

        hits = [RagHit.model_validate(h) for h in (resp.data or {}).get("hits", [])]
        update.retrieval.rag_documents = [h.model_dump() for h in hits]
        adapter = (services.get("rag_evidence_adapter")
                   if "rag_evidence_adapter" in services.services else RagEvidenceAdapter())
        update.retrieval.rag_person_evidence = [
            e.model_dump() for e in adapter.to_person_evidence(hits)
        ]
        return update

