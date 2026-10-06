"""模块 13:ConceptLinker(前三级)+ PersonConceptEvidence Repository 测试。"""
import pytest
import pytest_asyncio

from app.agent.concept_linker import ConceptCandidateRecall, QueryConceptLinker
from app.retrieval.person_concept_evidence import PersonConceptEvidenceRepository
from app.core.db import close_pool, execute, fetchval, health, init_pool

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def pool():
    try:
        await init_pool()
    except Exception:
        pytest.skip("数据库不可用")
    if not await health():
        pytest.skip()
    # 建 PCE 视图(模块 13 新增)
    from pathlib import Path
    sql = (Path(__file__).resolve().parent.parent
           / "scripts" / "ddl" / "04_agent_views.sql").read_text(encoding="utf-8")
    await execute(sql)
    yield
    await close_pool()


async def test_exact_recall(pool) -> None:
    """第一级:标准名精确召回(§7.3)。"""
    recall = ConceptCandidateRecall()
    candidates = await recall.recall("数据治理")
    assert candidates and candidates[0].candidate_source == "exact"
    assert candidates[0].candidate_score == 1.0
    assert candidates[0].canonical_name == "数据治理"


async def test_case_insensitive_recall(pool) -> None:
    """规范化后大小写/空白不敏感。"""
    recall = ConceptCandidateRecall()
    c1 = await recall.recall("数据治理")
    c2 = await recall.recall("  数据治理 ")
    assert c1 and c2 and c1[0].concept_id == c2[0].concept_id


async def test_linker_resolves_unique(pool) -> None:
    """查询侧链接:唯一高分命中 → resolved;输出结构符合 §7.6。"""
    linker = QueryConceptLinker()
    state = await linker.link(["数据治理"], query="谁负责数据治理?")
    assert len(state.resolved_concepts) == 1
    assert state.resolved_concepts[0]["canonical_name"] == "数据治理"
    assert state.ambiguous is False
    assert state.concept_link_trace  # link_trace 非空
    # 第二次走缓存,结果一致
    state2 = await linker.link(["数据治理"], query="谁负责数据治理?")
    assert state2.resolved_concepts == state.resolved_concepts


async def test_linker_unknown_term(pool) -> None:
    """未登录表达:无候选,不产生虚假 resolved(非法 concept_id 生成率=0)。"""
    linker = QueryConceptLinker()
    state = await linker.link(["一个不存在的随便什么词xyz"], query="x")
    assert state.resolved_concepts == []
    assert state.ambiguous is False


async def test_pce_repository_recall(pool) -> None:
    """PCE:按 concept_id 召回人员,保留原始 RawTag(§9.2 验收)。"""
    repo = PersonConceptEvidenceRepository()
    cid = await fetchval("SELECT concept_id FROM agent.concepts WHERE canonical_name='数据治理'")
    assert cid, "前置:数据治理概念存在"
    evidences = await repo.find_by_concepts([cid])
    assert len(evidences) > 0
    e = evidences[0]
    assert e.relation_type == "self_declared_scope"   # 不得为 responsible_for(§7.9)
    assert e.source_raw_tag                            # 原始 RawTag 保留
    assert e.confidence == 1.0                         # exact_alias 映射


async def test_pce_view_incremental_refresh(pool) -> None:
    """视图实时性:新增映射后证据立即可查(§9.2:增量刷新)。"""
    # 临时插入一个 tag+映射+person_tag,验证视图立即反映,然后清理
    await execute("INSERT INTO agent.raw_tags(tag_id, text, normalized_text)"
                  " VALUES('tag-tmp-1','临时测试领域','临时测试领域') ON CONFLICT DO NOTHING")
    cid = await fetchval("SELECT concept_id FROM agent.concepts WHERE canonical_name='数据治理'")
    await execute(
        "INSERT INTO agent.tag_concept_map(map_id, tag_id, concept_id, mapping_type,"
        " confidence, generated_by, review_status)"
        " VALUES('map-tmp-1','tag-tmp-1',$1,'exact_alias',1.0,'rule','auto_approved')", cid)
    await execute(
        "INSERT INTO agent.person_tags(person_tag_id, person_id, tag_id, source, created_by)"
        " VALUES('pt-tmp-1','p-0001','tag-tmp-1','self','test') ON CONFLICT DO NOTHING")
    repo = PersonConceptEvidenceRepository()
    evidences = await repo.find_by_concepts([cid])
    assert any(e.person_id == "p-0001" and e.source_raw_tag == "临时测试领域" for e in evidences)
    # 清理
    await execute("DELETE FROM agent.person_tags WHERE person_tag_id='pt-tmp-1'")
    await execute("DELETE FROM agent.tag_concept_map WHERE map_id='map-tmp-1'")
    await execute("DELETE FROM agent.raw_tags WHERE tag_id='tag-tmp-1'")
