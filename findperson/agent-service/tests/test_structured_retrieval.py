"""模块 14:TagMatcher / Directory Search / StructuredRetrievalNode 测试。"""
import pytest
import pytest_asyncio

from app.agent.nodes.structured_retrieval import StructuredRetrievalNode
from app.agent.orchestrator import ServiceRegistry
from app.contracts.agent_state import (
    AgentState, ConceptState, Intent, IntentState, QueryType,
    RequestState, UnderstandingState, UserContext,
)
from app.contracts.evidence import EvidenceType
from app.core.db import close_pool, execute, fetchval, health, init_pool
from app.retrieval.directory_search import DirectorySearch
from app.retrieval.tag_matcher import TagMatcher

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


def _state(qt: QueryType, query: str = "") -> AgentState:
    s = AgentState(
        request=RequestState(trace_id="t", run_id="r",
                             user_context=UserContext(user_id="p-0001"),
                             original_query=query, normalized_query=query)
    )
    s.intent = IntentState(intent=Intent.FIND_PERSON, query_type=qt)
    return s


async def test_directory_search_by_name(pool) -> None:
    """contact_lookup:按姓名查通讯录,detail 带联系方式(§9.1)。"""
    hits = await DirectorySearch().search(names=["王丹"])
    assert len(hits) == 1
    assert hits[0].evidence_type == EvidenceType.DIRECTORY_MATCH
    assert hits[0].detail["contact"]
    assert hits[0].detail["department"] == "数据管理与应用部"


async def test_tag_matcher_leaf_exact(pool) -> None:
    """一级匹配:resolved concept → leaf_exact 证据,保留原始 RawTag(§9.3)。"""
    cid = await fetchval("SELECT concept_id FROM agent.concepts WHERE canonical_name='数据治理'")
    matcher = TagMatcher()
    evidences, expanded = await matcher.match(
        [{"concept_id": cid, "canonical_name": "数据治理"}], expand=False)
    assert len(evidences) > 0
    assert all(e.detail["match_level"] == "leaf_exact" for e in evidences)
    assert all(e.relation_type == "self_declared_scope" for e in evidences)
    assert evidences[0].detail["source_raw_tag"]
    assert expanded == []


async def test_tag_matcher_generalized(pool) -> None:
    """二级匹配:concept_relations 泛化,降权且带 relation_path(§7.7/§9.3)。"""
    cid = await fetchval("SELECT concept_id FROM agent.concepts WHERE canonical_name='数据治理'")
    cid2 = await fetchval("SELECT concept_id FROM agent.concepts WHERE canonical_name='数据仓库'")
    if cid2 is None:
        pytest.skip("数据仓库概念不存在")
    # 临时关系:数据仓库 narrower_than 数据治理
    await execute(
        "INSERT INTO agent.concept_relations(relation_id, src_concept_id, dst_concept_id, relation_type)"
        " VALUES('rel-tmp-1',$1,$2,'narrower_than') ON CONFLICT DO NOTHING", cid2, cid)
    try:
        matcher = TagMatcher()
        evidences, expanded = await matcher.match(
            [{"concept_id": cid, "canonical_name": "数据治理"}], expand=True)
        assert any(e["concept_id"] == cid2 for e in expanded)
        gen = [e for e in evidences if e.detail["match_level"] == "concept_generalized"]
        if gen:
            assert gen[0].confidence <= 0.8 + 1e-9  # 泛化降权
            assert gen[0].relation_path             # 关系路径可写 Trace
    finally:
        await execute("DELETE FROM agent.concept_relations WHERE relation_id='rel-tmp-1'")


async def test_node_contact_lookup_no_rag(pool) -> None:
    """contact_lookup 只走 DirectorySearch,RAG 调用为 0(§8.1 验收)。"""
    state = _state(QueryType.CONTACT_LOOKUP, "王丹电话多少")
    state.understanding = UnderstandingState(mentioned_people=["王丹"])
    node = StructuredRetrievalNode()
    update = await node.execute(state, ServiceRegistry())
    assert len(update.retrieval.structured_candidates) == 1
    assert update.retrieval.rag_documents == []       # 零 RAG
    assert update.retrieval.responsibility_evidence == []


async def test_node_explicit_responsibility_via_mcp(pool) -> None:
    """explicit_responsibility:正式责任走 MCP get_responsibility(§9.4 正式路径)。"""
    cid = await fetchval("SELECT concept_id FROM agent.concepts WHERE canonical_name='数据治理'")
    state = _state(QueryType.EXPLICIT_RESPONSIBILITY, "谁负责数据治理?")
    state.concept = ConceptState(resolved_concepts=[
        {"concept_id": cid, "canonical_name": "数据治理"}])
    node = StructuredRetrievalNode()
    update = await node.execute(state, ServiceRegistry())
    assert len(update.retrieval.structured_candidates) > 0
    assert len(update.retrieval.responsibility_evidence) > 0
    rec = update.retrieval.responsibility_evidence[0]
    assert rec["owner_department"] and rec["escalation_path"] and rec["version"] >= 1
    # MCP 成功路径:无降级标记
    assert update.degraded is False


async def test_node_responsibility_fallback_to_mock(pool) -> None:
    """MCP 不可用 → 受控降级 Mock 直读,显式标记(§18/§21 基线:路径 A 可降级 100%)。"""
    from app.contracts.mcp import McpResponse, McpTool

    class FailingMcp:
        async def get_responsibility(self, names, *, user_context, trace_id):
            return McpResponse(ok=False, tool=McpTool.GET_RESPONSIBILITY,
                               error="MCP_ERROR", degraded=True, trace_id=trace_id)

    cid = await fetchval("SELECT concept_id FROM agent.concepts WHERE canonical_name='数据治理'")
    state = _state(QueryType.EXPLICIT_RESPONSIBILITY, "谁负责数据治理?")
    state.concept = ConceptState(resolved_concepts=[
        {"concept_id": cid, "canonical_name": "数据治理"}])
    node = StructuredRetrievalNode()
    update = await node.execute(state, ServiceRegistry({"mcp_client": FailingMcp()}))
    assert update.degraded is True
    assert "mock_responsibility_adapter" in update.retrieval.degraded_sources
    assert len(update.retrieval.responsibility_evidence) > 0
