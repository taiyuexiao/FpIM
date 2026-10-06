"""模块 16:AnswerBuilder + /agent/chat SSE 全链路集成测试。

阶段 1 验收案例(V1.2 §19):
员工A 填 AgentOS,员工B 填 Agent平台,用户问「谁负责智能体平台?」
→ 通过统一 Concept 同时召回 A、B。
"""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.agent.answer_builder import AnswerBuilder, _identity_of
from app.agent.chain import build_orchestrator
from app.agent.intent import IntentService
from app.agent.orchestrator import ServiceRegistry
from app.contracts.agent_state import (
    AgentState, Intent, IntentState, QueryType, RequestState, UserContext,
)
from app.core.db import close_pool, execute, fetchval, health, init_pool
from app.core.llm_client import LLMResult
from app.main import app

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


def _state(query: str, qt: QueryType | None = None) -> AgentState:
    s = AgentState(
        request=RequestState(trace_id="t", run_id="r",
                             user_context=UserContext(user_id="p-0001", name="王丹"),
                             original_query=query, normalized_query=query)
    )
    s.intent = IntentState(intent=Intent.FIND_PERSON, query_type=qt)
    return s


# ---------------------------------------------------------------- 阶段 1 验收案例

@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def acceptance_data(pool):
    """构造验收数据:员工A=AgentOS、员工B=Agent平台,统一 Concept=智能体平台。

    V2 数据集可能已含同名 Concept/RawTag(normalized_text 唯一约束),
    因此插入后按文本反查真实 ID,避免外键指向不存在的行。
    """
    await execute("INSERT INTO agent.concepts(concept_id, canonical_name, concept_type, status)"
                  " VALUES('concept-acc-1','智能体平台','platform','active') ON CONFLICT DO NOTHING")
    cid = await fetchval("SELECT concept_id FROM agent.concepts"
                         " WHERE canonical_name='智能体平台' ORDER BY valid_from LIMIT 1")
    await execute("INSERT INTO agent.raw_tags(tag_id, text, normalized_text)"
                  " VALUES('tag-acc-1','AgentOS','agentos') ON CONFLICT DO NOTHING")
    await execute("INSERT INTO agent.raw_tags(tag_id, text, normalized_text)"
                  " VALUES('tag-acc-2','Agent平台','agent平台') ON CONFLICT DO NOTHING")
    tag1 = await fetchval("SELECT tag_id FROM agent.raw_tags WHERE normalized_text='agentos'")
    tag2 = await fetchval("SELECT tag_id FROM agent.raw_tags WHERE normalized_text='agent平台'")
    await execute("INSERT INTO agent.tag_concept_map(map_id, tag_id, concept_id, mapping_type,"
                  " confidence, generated_by, review_status)"
                  " VALUES('map-acc-1',$1,$2,'exact_alias',1.0,'rule','auto_approved'),"
                  "        ('map-acc-2',$3,$2,'exact_alias',1.0,'rule','auto_approved')"
                  " ON CONFLICT DO NOTHING", tag1, cid, tag2)
    await execute("INSERT INTO agent.person_tags(person_tag_id, person_id, tag_id, source, created_by)"
                  " VALUES('pt-acc-1','p-0001',$1,'self','test'),"
                  "        ('pt-acc-2','p-0002',$2,'self','test') ON CONFLICT DO NOTHING", tag1, tag2)
    # 缓存失效:套件内其他测试已预热 Registry/查询缓存,必须清掉才能看到新数据
    from app.core.cache import get_cache
    await get_cache().clear()
    yield {"concept_id": cid, "tag1": tag1, "tag2": tag2}
    for sql, args in (
        ("DELETE FROM agent.person_tags WHERE person_tag_id IN ('pt-acc-1','pt-acc-2')", ()),
        ("DELETE FROM agent.tag_concept_map WHERE map_id IN ('map-acc-1','map-acc-2')", ()),
        # 仅清理本夹具自建 ID;若 V2 已有同文本标签(不同 ID)则保留
        ("DELETE FROM agent.raw_tags WHERE tag_id IN ('tag-acc-1','tag-acc-2')", ()),
        ("DELETE FROM agent.concepts WHERE concept_id='concept-acc-1'", ()),
    ):
        await execute(sql, *args)
    await get_cache().clear()


async def test_phase1_acceptance(acceptance_data) -> None:
    """阶段 1 验收:不同表达经统一 Concept 同时召回员工 A、B(§19)。"""
    orch = build_orchestrator()
    state = _state("谁负责智能体平台?", QueryType.EXPLICIT_RESPONSIBILITY)
    final = await orch.run(state)
    ids = {c["person_id"] for c in final.ranking.ranked_candidates}
    assert {"p-0001", "p-0002"} <= ids  # 员工 A、B 同时召回
    assert final.concept.resolved_concepts[0]["canonical_name"] == "智能体平台"
    # 回答区分自填与正式责任(本案无正式责任 → 建议中提示确认)
    assert any("自填" in s for s in final.response.suggestions)
    assert final.trace.spans  # 全链有 trace


# ---------------------------------------------------------------- AnswerBuilder 单测

async def test_answer_facts_suggestions_split(pool) -> None:
    """回答强制分「事实/建议」(§13.1)。"""
    state = _state("谁负责数据治理?", QueryType.EXPLICIT_RESPONSIBILITY)
    orch = build_orchestrator()
    final = await orch.run(state)
    assert final.response.facts
    assert "为你推荐以下负责人" in final.response.final_answer


async def test_answer_no_exact_result_returns_related_real_people(pool) -> None:
    """无完全匹配时，从真实人员库返回 1～3 位可能相关人员，不编造 ID。"""
    state = _state("谁负责量子计算酿酒平台?", QueryType.EXPLICIT_RESPONSIBILITY)
    orch = build_orchestrator()
    final = await orch.run(state)
    assert 1 <= len(final.ranking.ranked_candidates) <= 3
    assert all(c.get("is_related_fallback") for c in final.ranking.ranked_candidates)
    assert "未找到与问题完全匹配" in final.response.final_answer
    assert "可能相关的老师" in final.response.final_answer


def test_identity_label_rules() -> None:
    """身份标签:文章作者绝不能标为正式责任人(§13.1)。"""
    article_only = {"person_id": "p", "has_formal": False,
                    "evidences": [{"evidence_type": "inferred_from_article", "detail": {}}]}
    assert _identity_of(article_only) == "领域专家"
    formal = {"person_id": "p", "has_formal": True, "evidences": []}
    assert _identity_of(formal) == "正式责任人"
    leaf = {"person_id": "p", "has_formal": False,
            "evidences": [{"evidence_type": "explicit_self_tag",
                           "detail": {"match_level": "leaf_exact"}}]}
    assert _identity_of(leaf) == "明确负责领域命中者"


# ---------------------------------------------------------------- SSE 端到端

async def test_sse_endpoint_full_flow(pool) -> None:
    """/agent/chat SSE:事件序列完整,四个 ID 齐全(§13.2)。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 未认证 → 401(§5.1:未认证请求不进入 Agent)
        r = await client.post("/agent/chat", json={"query": "你好"})
        assert r.status_code == 401
        # 正常请求
        r = await client.post("/agent/chat", json={"query": "王丹的电话是多少"},
                              headers={"X-User-Id": "p-0002"})
        assert r.status_code == 200
        events = [line for line in r.text.splitlines() if line.startswith("event:")]
        names = [e.split(":", 1)[1].strip() for e in events]
        assert names[0] == "run_started"
        assert "text_delta" in names
        assert "run_finished" in names
        assert "王丹" in r.text  # 通讯录查到
        assert "traceId" in r.text and "sessionId" in r.text
