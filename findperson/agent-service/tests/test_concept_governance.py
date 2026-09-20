"""模块 18:员工侧 RawTag 注册六级链 + Candidate Concept 治理全流程测试。"""
import pytest
import pytest_asyncio

from app.agent.concept_governance import ConceptGovernance, RawTagConceptLinker
from app.contracts.concept import ReviewAction
from app.core.cache import get_cache
from app.core.db import close_pool, execute, fetchrow, fetchval, health, init_pool
from app.core.llm_client import LLMResult

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


class StubLLM:
    def __init__(self, data):
        self._data = data

    async def structured_chat(self, messages, *, required_keys, **kw):
        return self._data, LLMResult(content="{}", tokens=5, model="stub")


async def test_auto_map_high_confidence(pool) -> None:
    """新 RawTag 高置信确定性命中 → 自动映射,不进审核(§7.4)。"""
    linker = RawTagConceptLinker()
    # "数据治理"已存在 exact 映射,已有生效映射应走第三级复用
    result = await linker.register_raw_tag("p-0003", "数据治理")
    assert result["action"] == "reused"  # 已有生效映射,第三级复用
    assert result["concept_id"]
    # 清理测试 person_tag
    await execute("DELETE FROM agent.person_tags WHERE person_tag_id=$1",
                  result["person_tag_id"])


async def test_llm_create_candidate_and_governance(pool) -> None:
    """全流程:新 RawTag → LLM CREATE_CANDIDATE → 审核队列 → 批准转正 → 回填映射(§7.5)。"""
    await get_cache().clear()
    linker = RawTagConceptLinker(llm=StubLLM({
        "decision": "CREATE_CANDIDATE", "suggested_name": "Prompt管理平台",
        "reason": "现有概念无覆盖",
    }))
    result = await linker.register_raw_tag("p-0004", "Prompt平台")
    assert result["action"] == "candidate_created"
    candidate_id = result["candidate_concept_id"]

    # 候选概念隔离:不在正式词典中
    formal = await fetchval(
        "SELECT count(*) FROM agent.concepts WHERE concept_id=$1 AND status IN ('seed','active')",
        candidate_id)
    assert formal == 0

    # 审核:批准转正
    review = await fetchrow(
        "SELECT review_id FROM agent.concept_review_queue"
        " WHERE item_type='candidate_concept' AND status='pending'"
        " AND payload->>'candidate_concept_id'=$1", candidate_id)
    gov = ConceptGovernance()
    resolution = await gov.review(review["review_id"], ReviewAction.APPROVE, operator="admin")
    assert resolution["formal_concept_id"] == candidate_id
    assert resolution["backfilled_mappings"], "转正后应自动回填 RawTag 映射(§7.5)"

    # 转正后:概念 active,映射生效,审核条目 resolved
    status = await fetchval("SELECT status FROM agent.concepts WHERE concept_id=$1", candidate_id)
    assert status == "active"
    n = await fetchval(
        "SELECT count(*) FROM agent.tag_concept_map WHERE concept_id=$1 AND review_status='auto_approved'",
        candidate_id)
    assert n >= 1
    q_status = await fetchval(
        "SELECT status FROM agent.concept_review_queue WHERE review_id=$1", review["review_id"])
    assert q_status == "resolved"

    # 清理
    tag_row = await fetchrow("SELECT tag_id FROM agent.raw_tags WHERE normalized_text='prompt平台'")
    await execute("DELETE FROM agent.person_tags WHERE person_tag_id=$1", result["person_tag_id"])
    await execute("DELETE FROM agent.tag_concept_map WHERE concept_id=$1", candidate_id)
    await execute("DELETE FROM agent.concepts WHERE concept_id=$1", candidate_id)
    if tag_row:
        await execute("DELETE FROM agent.raw_tags WHERE tag_id=$1", tag_row["tag_id"])
    await get_cache().clear()


async def test_llm_output_out_of_candidates_rejected(pool) -> None:
    """LLM 输出候选集合外的 concept_id → 不建映射,进异常队列(§7.4 防线)。"""
    linker = RawTagConceptLinker(llm=StubLLM({
        "decision": "LINK_EXISTING", "concept_id": "concept-not-exists-xyz", "reason": "幻觉",
    }))
    result = await linker.register_raw_tag("p-0005", "一个全新未登录表达xyz")
    assert result["action"] == "review_enqueued"
    assert result["reason"] == "llm_output_out_of_candidates"
    n = await fetchval(
        "SELECT count(*) FROM agent.tag_concept_map WHERE concept_id='concept-not-exists-xyz'")
    assert n == 0  # 非法 ID 未落库(非法 concept_id 生成率=0)
    # 清理
    await execute("DELETE FROM agent.person_tags WHERE person_tag_id=$1", result["person_tag_id"])
    await execute("DELETE FROM agent.raw_tags WHERE normalized_text='一个全新未登录表达xyz'")
    await execute("DELETE FROM agent.concept_review_queue WHERE item_type='anomaly'"
                  " AND payload->>'text'='一个全新未登录表达xyz'")


async def test_ambiguous_goes_to_queue(pool) -> None:
    """LLM AMBIGUOUS → 歧义映射进审核队列,不建映射。"""
    linker = RawTagConceptLinker(llm=StubLLM({"decision": "AMBIGUOUS", "reason": "无法判断"}))
    result = await linker.register_raw_tag("p-0006", "中台那个东西")
    assert result["action"] == "review_enqueued"
    n = await fetchval(
        "SELECT count(*) FROM agent.concept_review_queue"
        " WHERE item_type='ambiguous_mapping' AND status='pending'"
        " AND payload->>'text'='中台那个东西'")
    assert n == 1
    # 清理
    await execute("DELETE FROM agent.person_tags WHERE person_tag_id=$1", result["person_tag_id"])
    await execute("DELETE FROM agent.raw_tags WHERE normalized_text='中台那个东西'")
    await execute("DELETE FROM agent.concept_review_queue WHERE payload->>'text'='中台那个东西'")


async def test_rawtext_preserved(pool) -> None:
    """原始填写文本原样保留,不被 Concept 覆盖(§7.1 红线)。"""
    linker = RawTagConceptLinker(llm=StubLLM({"decision": "AMBIGUOUS", "reason": "x"}))
    result = await linker.register_raw_tag("p-0007", "  AgentOS试验田  ")
    row = await fetchrow("SELECT text, normalized_text FROM agent.raw_tags WHERE tag_id=$1",
                         result["tag_id"])
    assert row["text"] == "AgentOS试验田"          # 原文(仅去首尾空白)保留
    assert row["normalized_text"] == "agentos试验田"
    # 清理
    await execute("DELETE FROM agent.person_tags WHERE person_tag_id=$1", result["person_tag_id"])
    await execute("DELETE FROM agent.raw_tags WHERE tag_id=$1", result["tag_id"])
    await execute("DELETE FROM agent.concept_review_queue WHERE payload->>'text' LIKE '%AgentOS试验田%'")
