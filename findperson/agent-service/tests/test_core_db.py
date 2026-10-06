"""模块 05:DB 基础能力测试(连真实 shouwenzeren_v2)。

运行前需先执行 scripts/init_db.py。DB 不可用时整组跳过。
"""
import pytest
import pytest_asyncio

from app.core.db import close_pool, fetchval, health, init_pool

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def pool():
    try:
        await init_pool()
    except Exception:
        pytest.skip("数据库不可用,跳过 DB 测试")
    if not await health():
        pytest.skip("数据库 health 未通过,跳过 DB 测试")
    yield
    await close_pool()


async def test_health(pool) -> None:
    """连接池 health 通过(§14.3)。"""
    assert await health() is True


async def test_three_schemas_exist(pool) -> None:
    """public/agent/rag 三 schema 存在(§17)。"""
    schemas = await fetchval(
        "SELECT count(*) FROM information_schema.schemata WHERE schema_name IN ('public','agent','rag')"
    )
    assert schemas == 3


async def test_core_tables_exist(pool) -> None:
    """核心表已建好。"""
    for fq in ("public.people", "public.responsibility_assignments",
               "agent.raw_tags", "agent.concepts", "agent.concept_review_queue",
               "rag.rag_documents", "rag.rag_chunks", "rag.rag_index_pointer"):
        count = await fetchval(f"SELECT count(*) FROM {fq}")
        assert count is not None and count >= 0


async def test_two_vector_spaces(pool) -> None:
    """Concept 512 维(内部空间)与 RAG 1536 维(对齐 knowledge-service)两个独立向量空间(§10.8)。"""
    concept_dim = await fetchval(
        "SELECT atttypmod FROM pg_attribute WHERE attrelid='agent.concepts'::regclass AND attname='embedding'"
    )
    rag_dim = await fetchval(
        "SELECT atttypmod FROM pg_attribute WHERE attrelid='rag.rag_chunks'::regclass AND attname='embedding'"
    )
    assert concept_dim == 512
    assert rag_dim == 1536


async def test_trgm_indexes(pool) -> None:
    """pg_trgm 索引已建立(§7.3 第四级召回、§10.9 FTS 用)。"""
    n = await fetchval("SELECT count(*) FROM pg_indexes WHERE indexdef ILIKE '%gin_trgm_ops%'")
    assert n >= 3
