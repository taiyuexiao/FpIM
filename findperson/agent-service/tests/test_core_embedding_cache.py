"""模块 07:Embedding Client + CachePort 测试。"""
import asyncio

import pytest

from app.core.cache import CacheKeys, LocalCache, get_cache
from app.core.embedding_client import (
    cosine_similarity, get_concept_embedding, get_rag_embedding,
)


async def test_embedding_dimensions() -> None:
    """RAG 1536 维(对齐 knowledge-service)、Concept 512 维(内部空间),两个独立空间(§10.8)。"""
    rag = get_rag_embedding()
    concept = get_concept_embedding()
    assert rag.dimension == 1536
    assert concept.dimension == 512
    assert rag.model_version != concept.model_version
    v = await rag.embed_query("Dify平台运维")
    assert len(v) == 1536


async def test_embedding_deterministic() -> None:
    """Mock Embedding 确定性:同一文本同一向量。"""
    emb = get_rag_embedding()
    v1 = await emb.embed_query("智能体平台")
    v2 = await emb.embed_query("智能体平台")
    assert v1 == v2


async def test_embedding_semantic_signal() -> None:
    """词汇重叠越多相似度越高:AgentOS/Agent平台 应比 完全无关文本 更接近 智能体平台。"""
    emb = get_concept_embedding()
    base = await emb.embed_query("智能体平台")
    near = await emb.embed_query("AgentOS 智能体开发平台")
    far = await emb.embed_query("银行柜面业务办理流程")
    assert cosine_similarity(base, near) > cosine_similarity(base, far)


async def test_cross_space_comparison_rejected() -> None:
    """跨向量空间比较直接报错(§10.8 红线)。"""
    rag = get_rag_embedding()
    concept = get_concept_embedding()
    a = await rag.embed_query("x")
    b = await concept.embed_query("x")
    with pytest.raises(ValueError):
        cosine_similarity(a, b)


async def test_cache_set_get_ttl() -> None:
    """LocalCache 读写与 TTL 过期。"""
    cache = LocalCache()
    await cache.set("k1", {"v": 1})
    assert await cache.get("k1") == {"v": 1}
    await cache.set("k2", "temp", ttl_seconds=1)
    assert await cache.get("k2") == "temp"
    await asyncio.sleep(1.1)
    assert await cache.get("k2") is None


async def test_cache_delete_and_singleton() -> None:
    """删除与全局单例。"""
    cache = LocalCache()
    await cache.set("k", 1)
    await cache.delete("k")
    assert await cache.get("k") is None
    assert get_cache() is get_cache()


def test_cache_keys_format() -> None:
    """缓存键模板可用。"""
    assert CacheKeys.QUERY_CONCEPT.format(query="谁负责Dify") == "concept:q:谁负责Dify"
