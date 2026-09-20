"""模块 17:第四级 pg_trgm + 第五级 Concept Vector 召回测试。"""
import pytest
import pytest_asyncio

from app.agent.concept_linker import ConceptCandidateRecall, QueryConceptLinker
from app.core.db import close_pool, health, init_pool

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


async def test_trgm_recall(pool) -> None:
    """第四级:pg_trgm 召回名称近似概念(§7.3),分数不进入自动确认区。"""
    recall = ConceptCandidateRecall()
    candidates = await recall.recall("数据治理工作")
    assert candidates, "trgm 应召回近似概念"
    trgm_hits = [c for c in candidates if c.candidate_source == "pg_trgm"]
    assert trgm_hits, "应包含 pg_trgm 召回"
    assert "数据治理" in trgm_hits[0].canonical_name
    assert trgm_hits[0].candidate_score < 0.9  # trgm 只出候选,不自动映射(§7.3)


async def test_vector_recall(pool) -> None:
    """第五级:Concept Vector 召回(独立 1024 维空间),只出候选(§7.3/§10.8)。"""
    recall = ConceptCandidateRecall()
    candidates = await recall.recall("数据仓库建模与指标管理")
    vector_hits = [c for c in candidates if c.candidate_source == "vector"]
    assert vector_hits, "向量应召回相关概念"
    assert all(c.candidate_score <= 0.85 for c in vector_hits)  # 上限封顶
    # 召回的概念应与数据领域相关
    names = [c.canonical_name for c in vector_hits]
    assert any("数据" in n for n in names)


async def test_deterministic_short_circuit(pool) -> None:
    """前三级命中即短路,不走 trgm/vector(§7.3 顺序)。"""
    recall = ConceptCandidateRecall()
    candidates = await recall.recall("数据治理")
    assert candidates[0].candidate_source == "exact"
    assert all(c.candidate_source in ("exact", "alias", "historical") for c in candidates)


async def test_fuzzy_resolve_requires_char_overlap(pool) -> None:
    """模糊归一防线:纯语义近邻不自动归一,兼有字符重叠才放行。

    HarnessEval → AI基础研发 这类纯语义近邻(无字符重叠)必须拒绝;
    首问必达 → 首问必答平台 这类错别字(有字符重叠)允许归一。
    其余确定性级别(exact/alias/historical/prefix/subseq/contains)不受影响。
    """
    linker = QueryConceptLinker()
    # 纯语义近邻:不得归一
    state = await linker.link(["HarnessEval"], query="谁负责HarnessEval?")
    assert state.resolved_concepts == []
    # 错别字:允许经受控模糊通道归一
    state2 = await linker.link(["首问必达"], query="首问必达怎么用?")
    fuzzy_ok = {"vector_fuzzy", "pg_trgm_fuzzy"}
    deterministic = {"exact", "alias", "historical", "prefix", "subseq", "contains"}
    assert all(r["source"] in (deterministic | fuzzy_ok) for r in state2.resolved_concepts)
    if any(r["source"] in fuzzy_ok for r in state2.resolved_concepts):
        assert any(r["canonical_name"] == "首问必答平台" for r in state2.resolved_concepts)


async def test_max_level_3_compatible(pool) -> None:
    """max_level=3 时不走 trgm/vector 模糊层(向后兼容);v2 确定性级别(prefix/contains/subseq)仍生效。"""
    recall = ConceptCandidateRecall()
    candidates = await recall.recall("数据治理工作", max_level=3)
    assert all(c.candidate_source not in ("pg_trgm", "vector") for c in candidates)
