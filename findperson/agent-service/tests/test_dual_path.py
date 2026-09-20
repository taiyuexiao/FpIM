"""模块 26:RAG 证据适配 + 双路召回全链路测试。"""
import pytest
import pytest_asyncio

from app.agent.chain import build_orchestrator
from app.contracts.agent_state import (
    AgentState, Intent, IntentState, QueryType, RequestState, UserContext,
)
from app.contracts.evidence import EvidenceType
from app.contracts.mcp import RagHit
from app.core.db import close_pool, health, init_pool
from app.rag.evidence_adapter import RagEvidenceAdapter

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def pool():
    try:
        await init_pool()
    except Exception:
        pytest.skip("数据库不可用")
    if not await health():
        pytest.skip()
    yield
    await close_pool()


def _state(query: str, qt: QueryType | None = None,
           intent: Intent = Intent.FIND_PERSON) -> AgentState:
    s = AgentState(
        request=RequestState(trace_id="t", run_id="r",
                             user_context=UserContext(user_id="p-0002", name="刘旭"),
                             original_query=query, normalized_query=query)
    )
    s.intent = IntentState(intent=intent, query_type=qt)
    return s


# ---------------------------------------------------------------- 适配器(§10.11)

def test_adapter_conversions() -> None:
    """知识证据 → 人员证据:责任=1.0、文章≤0.6、画像≤0.55;部门文档跳过。"""
    adapter = RagEvidenceAdapter()
    hits = [
        RagHit(document_id="responsibility-ra-1", chunk_id="c1",
               document_type="responsibilities", score=0.9, content="x",
               metadata={"owner_person_id": "p-0100"}),
        RagHit(document_id="content-0001", chunk_id="c2",
               document_type="contents", score=0.9, content="x",
               metadata={"author_person_id": "p-0200"}),
        RagHit(document_id="person-p-0300", chunk_id="c3",
               document_type="people", score=0.9, content="x",
               metadata={"section": "同事评价"}),
        RagHit(document_id="department-3", chunk_id="c4",
               document_type="departments", score=0.9, content="x"),
    ]
    evidences = adapter.to_person_evidence(hits)
    assert len(evidences) == 3  # 部门文档跳过
    formal = next(e for e in evidences if e.evidence_type == EvidenceType.FORMAL_ASSIGNMENT)
    assert formal.person_id == "p-0100" and formal.confidence == 1.0  # 与相似度无关
    article = next(e for e in evidences if e.evidence_type == EvidenceType.INFERRED_FROM_ARTICLE)
    assert article.person_id == "p-0200" and article.confidence <= 0.6  # 相似度≠责任人分数
    review = next(e for e in evidences if e.evidence_type == EvidenceType.INFERRED_FROM_REVIEW)
    assert review.person_id == "p-0300"
    # 文章作者绝不是 formal_assignment(§13.1)
    assert article.relation_type == "article_expertise"


# ---------------------------------------------------------------- 双路召回(diagnostic)

async def test_dual_path_diagnostic(pool) -> None:
    """diagnostic:结构化路 + RAG 路并联,两路证据都进融合(§8.1)。"""
    from app.agent.intent import IntentService
    from app.agent.orchestrator import ServiceRegistry
    from app.agent.query_structurer import QueryStructurerService
    from app.contracts.agent_state import UnderstandingState
    from app.core.llm_client import LLMResult

    class StubIntentLLM:
        async def structured_chat(self, messages, *, required_keys, **kw):
            return {"intent": "find_person", "query_type": "diagnostic",
                    "confidence": 0.95, "needs_clarification": False,
                    "clarify_question": ""}, LLMResult(content="{}", tokens=1, model="stub")

    class StubStructurer(QueryStructurerService):
        async def structure(self, query):
            u = UnderstandingState(mentioned_systems=["数据治理"], symptoms=["出问题"])
            u.explicit_terms = ["数据治理"]
            u.field_sources = {"systems:数据治理": "explicit"}
            return u

    services = ServiceRegistry({
        "intent_service": IntentService(StubIntentLLM()),
        "query_structurer": StubStructurer(),
    })
    orch = build_orchestrator(services)
    state = _state("数据治理平台出问题了该找谁?", QueryType.DIAGNOSTIC)
    final = await orch.run(state)
    # 结构化路:概念命中 → leaf_exact 证据
    assert final.retrieval.structured_candidates
    # RAG 路:知识文档 + 人员证据(责任/画像/文章)
    assert final.retrieval.rag_documents
    # 融合排序有结果
    assert final.ranking.ranked_candidates
    node_names = {s.node_name for s in final.trace.spans}
    assert "StructuredRetrievalNode" in node_names
    assert "KnowledgeRetrievalNode" in node_names


async def test_contact_lookup_still_zero_rag(pool) -> None:
    """contact_lookup:RAG 调用仍为 0(§8.1 基线:contact_lookup RAG 调用率=0)。"""
    orch = build_orchestrator()
    state = _state("王丹的电话是多少", QueryType.CONTACT_LOOKUP)
    final = await orch.run(state)
    assert final.retrieval.rag_documents == []
    assert final.retrieval.rag_person_evidence == []
    node_names = {s.node_name for s in final.trace.spans}
    assert "KnowledgeRetrievalNode" not in node_names


async def test_explicit_responsibility_via_mcp(pool) -> None:
    """explicit_responsibility:正式责任走 MCP get_responsibility(不再经 Mock 主路径)。"""
    orch = build_orchestrator()
    state = _state("谁负责数据治理?", QueryType.EXPLICIT_RESPONSIBILITY)
    final = await orch.run(state)
    assert final.retrieval.responsibility_evidence
    rec = final.retrieval.responsibility_evidence[0]
    assert rec["source_uri"].startswith("public.responsibility_assignments/")
    # MCP 成功路径:不再有 mock 降级标记
    assert "mock_responsibility_adapter" not in final.retrieval.degraded_sources
    assert "mock_responsibility_adapter" not in final.retrieval.degraded_sources
    # 正式责任人排第一
    assert final.ranking.ranked_candidates[0]["has_formal"] is True


# ------------------------------------------------------ 知识类问题并入查人链(架构收敛:查/写双轨)

def _expert_finding_services():
    """意图层 stub:固定判为 find_person/expert_finding,避免真实 LLM 分类波动导致用例不稳定。"""
    from app.agent.intent import IntentService
    from app.agent.orchestrator import ServiceRegistry
    from app.core.llm_client import LLMResult

    class StubIntentLLM:
        async def structured_chat(self, messages, *, required_keys, **kw):
            return {"intent": "find_person", "query_type": "expert_finding",
                    "confidence": 0.95, "needs_clarification": False,
                    "clarify_question": ""}, LLMResult(content="{}", tokens=1, model="stub")

    return ServiceRegistry({"intent_service": IntentService(StubIntentLLM())})


async def test_knowledge_question_as_expert_finding(pool) -> None:
    """知识类问题 → find_person/expert_finding:双路检索、以名片作答、内容证据带来源引用。"""
    orch = build_orchestrator(_expert_finding_services())
    state = _state("智能问数的工作方法是什么?", QueryType.EXPERT_FINDING)
    final = await orch.run(state)
    assert final.retrieval.rag_documents  # RAG 路命中(与原 KnowledgeQANode 同一 MCP 检索)
    assert final.ranking.ranked_candidates  # 以名片作答
    assert final.response.citations  # 内容来源引用并入查人响应
    node_names = {s.node_name for s in final.trace.spans}
    assert "KnowledgeRetrievalNode" in node_names
    assert "KnowledgeQANode" not in node_names  # 已摘除


async def test_knowledge_question_no_evidence_honest(pool) -> None:
    """无完全匹配证据:最多推荐 3 位真实相关人员，并明确非完全匹配。"""
    orch = build_orchestrator(_expert_finding_services())
    state = _state("火星殖民地葡萄栽培技术规范是什么?", QueryType.EXPERT_FINDING)
    final = await orch.run(state)
    assert 1 <= len(final.ranking.ranked_candidates) <= 3
    assert all(c.get("is_related_fallback") for c in final.ranking.ranked_candidates)
    assert "未找到与问题完全匹配" in final.response.final_answer
    assert final.response.citations == []
