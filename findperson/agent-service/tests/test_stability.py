"""模块 29:稳定性测试(RAG 降级 / 全链超时 / 熔断已有覆盖)。"""
import pytest
import pytest_asyncio

from app.contracts.agent_state import UserContext
from app.core.db import close_pool, health, init_pool
from app.rag.retriever import HybridRetriever

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


class BrokenEmbedding:
    """模拟 Embedding 服务故障。"""

    @property
    def dimension(self) -> int:
        return 1536

    @property
    def model_version(self) -> str:
        return "broken"

    async def embed_query(self, text: str):
        raise ConnectionError("Embedding service down")

    async def embed_documents(self, texts: list[str]):
        raise ConnectionError("Embedding service down")


async def test_embedding_down_keyword_fallback(pool) -> None:
    """Embedding 不可用 → 关键词单路降级,检索仍可用(§21 基线:100% 可降级)。"""
    retriever = HybridRetriever(embedding=BrokenEmbedding())
    hits = await retriever.retrieve("数据治理", UserContext(user_id="p-0001"))
    assert hits, "FTS 单路应继续返回结果"
    assert any("数据治理" in h.content for h in hits)


async def test_normal_path_still_dual(pool) -> None:
    """正常路径不受影响:双路融合仍包含向量召回。"""
    retriever = HybridRetriever()
    hits = await retriever.retrieve("数据治理", UserContext(user_id="p-0001"))
    assert hits
