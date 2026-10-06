"""模块 09:Seed Concept 冷启动 + ConceptRegistry 测试。"""
import pytest
import pytest_asyncio

from app.agent.concept_registry import get_concept_registry
from app.contracts.concept import ConceptStatus
from app.core.db import close_pool, fetchval, health, init_pool

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def pool():
    try:
        await init_pool()
    except Exception:
        pytest.skip("数据库不可用,跳过")
    if not await health():
        pytest.skip("数据库 health 未通过,跳过")
    yield
    await close_pool()


async def test_seed_concepts_created(pool) -> None:
    """Seed Concept 已生成,全部有稳定 ID 与类型(§7.2 验收)。"""
    n = await fetchval("SELECT count(*) FROM agent.concepts WHERE status IN ('seed','active')")
    assert n >= 61
    bad = await fetchval(
        "SELECT count(*) FROM agent.concepts WHERE concept_id IS NULL OR canonical_name = ''"
    )
    assert bad == 0


async def test_all_rawtags_mapped(pool) -> None:
    """全部存量 RawTag 已通过第一级精确映射挂上 Concept(§7.3 第一级)。"""
    unmapped = await fetchval(
        "SELECT count(*) FROM agent.raw_tags rt"
        " WHERE NOT EXISTS (SELECT 1 FROM agent.tag_concept_map m WHERE m.tag_id = rt.tag_id)"
    )
    assert unmapped == 0
    exact = await fetchval(
        "SELECT count(*) FROM agent.tag_concept_map WHERE mapping_type='exact_alias' AND confidence=1.0"
    )
    assert exact >= 61


async def test_registry_loads_and_caches(pool) -> None:
    """Registry 加载正式概念词典,缓存生效;不含 candidate(§7.6 共用 Registry)。"""
    registry = get_concept_registry()
    concepts = await registry.load_concepts(force=True)
    assert len(concepts) >= 61
    assert all(c.status in (ConceptStatus.SEED, ConceptStatus.ACTIVE) for c in concepts.values())
    cached = await registry.load_concepts()
    assert len(cached) == len(concepts)
    mappings = await registry.load_tag_mappings()
    assert len(mappings) >= 61


async def test_registry_rawtag_lookup(pool) -> None:
    """按规范化文本查 RawTag 实体。"""
    registry = get_concept_registry()
    tag = await registry.get_raw_tag_by_text("数据治理")
    if tag is not None:  # 数据治理是存量领域之一
        assert tag.normalized_text == "数据治理"
        assert tag.text  # 原文保留
