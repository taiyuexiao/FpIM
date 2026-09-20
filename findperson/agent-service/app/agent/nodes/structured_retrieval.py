"""结构化检索节点(路径 A,V1.2 §8.1/§9)。

按 query_type 执行不同结构化检索:
- contact_lookup:DirectorySearch 单路(不进 ConceptLinker/RAG)
- explicit_responsibility:TagMatcher 一级 + Formal Responsibility(Mock Adapter)
- diagnostic / expert_finding:TagMatcher 两级(含概念泛化)
"""
from __future__ import annotations

from app.agent.orchestrator import AgentNode, ServiceRegistry
from app.contracts.agent_state import AgentState, Intent, QueryType, StateUpdate
from app.retrieval.directory_search import DirectorySearch
from app.retrieval.responsibility import MockResponsibilityRetriever
from app.retrieval.tag_matcher import TagMatcher


class StructuredRetrievalNode(AgentNode):
    """结构化人员与责任检索节点。"""

    name = "StructuredRetrievalNode"
    timeout_ms = 8000
    on_error = "degrade"

    async def execute(self, state: AgentState, services: ServiceRegistry) -> StateUpdate:
        if state.intent.intent != Intent.FIND_PERSON:
            return StateUpdate()
        qt = state.intent.query_type
        update = StateUpdate()
        update.retrieval = state.retrieval.model_copy(deep=True)

        if qt == QueryType.CONTACT_LOOKUP:
            searcher = (services.get("directory_search")
                        if "directory_search" in services.services else DirectorySearch())
            hits = await searcher.search(
                names=state.understanding.mentioned_people or None,
                departments=state.understanding.mentioned_departments or None,
            )
            update.retrieval.structured_candidates = [h.model_dump() for h in hits]
            return update

        # 其余三类走 TagMatcher
        matcher = services.get("tag_matcher") if "tag_matcher" in services.services else TagMatcher()
        expand = qt in (QueryType.DIAGNOSTIC, QueryType.EXPERT_FINDING)
        evidences, expanded = await matcher.match(state.concept.resolved_concepts, expand=expand)
        update.retrieval.structured_candidates = [e.model_dump() for e in evidences]
        if expanded:
            update.concept = state.concept.model_copy(deep=True)
            update.concept.expanded_concepts = expanded

        # explicit_responsibility 附加正式责任检索
        # 正式路径:Knowledge MCP get_responsibility(§9.4);MCP 失败降级 Mock 直读(§18)
        if qt == QueryType.EXPLICIT_RESPONSIBILITY:
            concept_names = [c.get("canonical_name", "") for c in state.concept.resolved_concepts]
            records = []
            if not concept_names:
                # 没有解析出任何领域概念(如"申请 llm key 找谁"):无输入可查正式责任。
                # 这属于正常无输入,不是故障——直接返回空,不标记降级(否则每条此类问题都会挂"降级路径"提示)。
                update.retrieval.responsibility_evidence = records
                return update
            mcp = (services.get("mcp_client")
                   if "mcp_client" in services.services else None)
            if mcp is None:
                from app.mcp_knowledge.client import get_mcp_client
                mcp = get_mcp_client()
            resp = await mcp.get_responsibility(
                concept_names, user_context=state.request.user_context,
                trace_id=state.trace.trace_id)
            if resp.ok:
                records = (resp.data or {}).get("responsibilities", [])
            else:
                # MCP 不可用 → 受控降级到 Mock 直读 Adapter(§18:显式标记)
                retriever = (services.get("responsibility_retriever")
                             if "responsibility_retriever" in services.services
                             else MockResponsibilityRetriever())
                fallback_records = await retriever.get_responsibility(concept_names)
                records = [r.model_dump() for r in fallback_records]
                update.retrieval.degraded_sources.append("mock_responsibility_adapter")
                update.degraded = True
            update.retrieval.responsibility_evidence = records
        return update
