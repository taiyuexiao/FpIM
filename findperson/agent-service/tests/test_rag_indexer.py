"""模块 23:RAG Indexer 测试(增量规则 + 版本原子切换 + Smoke Test)。"""
import pytest
import pytest_asyncio

from app.contracts.okf import OkfDocument, OkfMetadata, OkfStatus, OkfType, Visibility
from app.core.db import close_pool, fetchrow, fetchval, health, init_pool
from app.okf.builders import build_content_doc
from app.rag.indexer import RagIndexer

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


def _content_doc(doc_id: str, body: str, version: int = 1) -> OkfDocument:
    doc = build_content_doc(
        {"id": doc_id, "title": f"测试文档{doc_id}", "body": body,
         "owner_id": "p-0001", "tags": ["测试"]},
        owner_name="王丹", owner_department_id=3)
    doc.metadata.status = OkfStatus.PUBLISHED
    doc.metadata.version = version
    doc.metadata.content_hash = doc.metadata.compute_hash(doc.body)
    return doc


async def test_incremental_add_replace_skip(pool) -> None:
    """增量规则:新增/正文替换/未变跳过(§10.6)。"""
    indexer = RagIndexer()
    version = await indexer.current_version()
    assert version >= 1, "先运行 scripts/build_rag_index.py"

    doc = _content_doc("test-inc-1", "这是增量新增的测试文档,内容是数据平台巡检。")
    # build_content_doc 会加 content- 前缀,最终 document_id = content-test-inc-1
    r1 = await indexer.incremental([doc])
    assert r1["added"] == 1

    doc2 = _content_doc("test-inc-1", "这是增量新增的测试文档,内容改为数据平台月度巡检。", version=2)
    r2 = await indexer.incremental([doc2])
    assert r2["replaced"] == 1

    r3 = await indexer.incremental([doc2])  # 内容未变
    assert r3["skipped"] == 1

    content = await fetchval(
        "SELECT content FROM rag.rag_chunks WHERE document_id='content-test-inc-1'"
        " AND index_version=$1 LIMIT 1", version)
    assert "月度巡检" in content


async def test_invalidate(pool) -> None:
    """删除/废止:旧索引失效(§10.6)。"""
    indexer = RagIndexer()
    n = await indexer.invalidate(["content-test-inc-1"])
    assert n == 1
    status = await fetchval(
        "SELECT status FROM rag.rag_documents WHERE document_id='content-test-inc-1'"
        " ORDER BY updated_at DESC LIMIT 1")
    assert status == "invalidated"


async def test_rebuild_atomic_switch(pool) -> None:
    """全量重建:新版本 + Smoke Test + 原子切换 + job 记录(§10.6)。"""
    from app.okf.repository import OkfRepository
    from pathlib import Path
    repo = OkfRepository(Path(__file__).resolve().parent.parent / "knowledge-okf")
    docs = await repo.list_published()
    indexer = RagIndexer()
    before = await indexer.current_version()
    result = await indexer.rebuild(docs)
    assert result["index_version"] == before + 1
    assert result["documents"] == 374 and result["smoke"]["ok"]
    after = await indexer.current_version()
    assert after == before + 1  # 指针已原子切换
    job = await fetchrow("SELECT status, job_type FROM rag.rag_index_jobs WHERE job_id=$1",
                         result["job_id"])
    assert job["status"] == "published" and job["job_type"] == "full_rebuild"


async def test_embedding_model_versioned(pool) -> None:
    """索引模型版本化:chunk 记录 embedding_model(§23)。"""
    model = await fetchval("SELECT DISTINCT embedding_model FROM rag.rag_chunks LIMIT 1")
    assert model and model.startswith("mock-rag-embedding")
