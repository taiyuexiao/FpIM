"""模块 24:Hybrid Retriever + Knowledge QA 测试。"""
import pytest
import pytest_asyncio

from app.contracts.agent_state import UserContext
from app.core.db import close_pool, health, init_pool
from app.rag.retriever import HybridRetriever, KnowledgeQAService

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


def _ctx(level: int = 0) -> UserContext:
    return UserContext(user_id="p-0001", name="王丹", sensitivity_level=level)


async def test_fts_recall(pool) -> None:
    """关键词检索:数据治理相关 chunk 被召回(§10.9 FTS 路)。"""
    retriever = HybridRetriever()
    hits = await retriever.retrieve("数据治理", _ctx())
    assert hits, "应召回到数据治理相关知识"
    assert any("数据治理" in h.content for h in hits)


async def test_vector_recall_semantic(pool) -> None:
    """语义检索:换一种说法也能召回(向量路补强)。

    仅在真实语义 Embedding(openai_compatible/fastembed)下有效;
    mock 向量只有词汇重叠信号,无语义泛化能力,跳过。
    """
    from app.config import get_settings
    s = get_settings()
    if s.embedding_use_mock or s.embedding_provider == "mock":
        pytest.skip("mock Embedding 无语义能力,跳过语义召回测试")
    retriever = HybridRetriever()
    hits = await retriever.retrieve("问题需要转交和逐级上报", _ctx())
    assert hits
    # 责任文档含转办条件/升级路径,应被召回
    assert any(h.document_type == "responsibilities" for h in hits)


async def test_hit_contract(pool) -> None:
    """命中结构:document_id/chunk_id/score/source_uri/version 齐全(§10.9 产出)。"""
    retriever = HybridRetriever()
    hits = await retriever.retrieve("数据治理", _ctx())
    h = hits[0]
    assert h.document_id and h.chunk_id
    assert h.score > 0
    assert h.source_uri and h.version >= 1


async def test_topk_and_dedup(pool) -> None:
    """Top5 截断 + 按文档/章节去重(§10.9)。"""
    retriever = HybridRetriever()
    hits = await retriever.retrieve("数据", _ctx(), top_k=5)
    assert len(hits) <= 5
    keys = [f"{h.document_id}#{h.chunk_id.rsplit('-c',1)[-1]}" for h in hits]
    assert len(set((h.document_id, h.chunk_id) for h in hits)) == len(hits)


async def test_knowledge_qa_with_evidence(pool) -> None:
    """Knowledge QA:有证据时返回 facts + citations(§10.10)。"""
    qa = KnowledgeQAService()
    result = await qa.answer("数据治理相关事务谁负责?", _ctx())
    assert result["has_evidence"] is True
    assert result["facts"] and result["citations"]
    c = result["citations"][0]
    assert c["document_id"] and c["version"] >= 1 and c["source_uri"]


async def test_knowledge_qa_no_evidence_no_fabrication(pool) -> None:
    """Knowledge QA:无证据时 has_evidence=False,不编造(§10.10 红线)。"""
    qa = KnowledgeQAService()
    result = await qa.answer("火星殖民地葡萄栽培技术规范", _ctx())
    # 无证据或证据极弱时不得返回编造内容
    if not result["has_evidence"]:
        assert result["facts"] == [] and result["citations"] == []
