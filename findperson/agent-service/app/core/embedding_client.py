"""Embedding Client(V1.2 §14.2 / §10.8)。

提供 embed_query / embed_documents / model_version / dimension。
Concept(512 维,Agent 内部空间)与 RAG(1536 维,与 knowledge-service 对齐)
是两个独立向量空间,使用不同配置实例,不得跨空间比较。

RAG provider:
- openai_compatible:行内 OpenAI 兼容服务(生产,text-embedding-v4 1536 维)
- fastembed       :本地 ONNX 模型(开发档,模型维度须与配置一致)
- mock            :离线确定性 Mock(链路验证用,不代表检索质量)
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from app.config import get_settings


class EmbeddingPort(Protocol):
    """Embedding 抽象端口(§14.2)。"""

    @property
    def dimension(self) -> int: ...

    @property
    def model_version(self) -> str: ...

    async def embed_query(self, text: str) -> list[float]: ...

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...


_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+|[一-鿿]")


def _tokenize(text: str) -> list[str]:
    """中英文混合的极简分词:英文按词,中文按单字+相邻二字组。"""
    tokens: list[str] = []
    for m in _TOKEN_RE.finditer(text.lower()):
        t = m.group(0)
        tokens.append(t)
    # 中文二字组,提升中文短语的区分度
    chars = [c for c in text if "一" <= c <= "鿿"]
    tokens.extend("".join(chars[i : i + 2]) for i in range(len(chars) - 1))
    return tokens


@dataclass
class MockEmbedding:
    """确定性 Mock Embedding。

    原理:每个 token 经 sha256 映射到 K 个维度位置加分,再 L2 归一化。
    词汇重叠越多的文本,余弦相似度越高 —— 足以支撑候选召回的开发与评测。
    """

    _dimension: int
    _model_version: str
    _scatter: int = 8  # 每个 token 撒布的维度数

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_version(self) -> str:
        return self._model_version

    def _embed(self, text: str) -> list[float]:
        vec = np.zeros(self._dimension, dtype=np.float32)
        for token in _tokenize(text):
            digest = hashlib.sha256(f"{self._model_version}:{token}".encode()).digest()
            for i in range(self._scatter):
                pos = int.from_bytes(digest[i * 4 : i * 4 + 4], "little") % self._dimension
                sign = 1.0 if digest[(i * 4 + 3) % len(digest)] % 2 == 0 else -1.0
                vec[pos] += sign
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        return vec.tolist()

    async def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """余弦相似度。同一向量空间内才能比较(§10.8)。"""
    va, vb = np.asarray(a), np.asarray(b)
    if va.shape != vb.shape:
        raise ValueError(f"向量维度不一致,不得跨空间比较: {va.shape} vs {vb.shape}")
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)


# ---------------------------------------------------------------- 真实实现(OpenAI 兼容,text-embedding-v4 1536 维)

class OpenAICompatibleEmbedding:
    """行内 OpenAI 兼容 Embedding 服务客户端(httpx 异步 + 重试 + 维度校验)。

    与仓库 knowledge-service 的契约一致:POST {base_url}/embeddings,
    payload {model, input, dimensions};生产环境 RAG 空间固定 1536 维。
    """

    def __init__(self, model_name: str, dimension: int, *, base_url: str, api_key: str,
                 timeout: float = 90.0, max_attempts: int = 4) -> None:
        if not base_url or not api_key:
            raise ValueError("openai_compatible Embedding 需要 EMBEDDING_BASE_URL 与 EMBEDDING_API_KEY")
        self._model_name = model_name
        self._dimension = dimension
        self._url = base_url.rstrip("/") + "/embeddings"
        self._api_key = api_key
        self._timeout = timeout
        self._max_attempts = max_attempts

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_version(self) -> str:
        return self._model_name

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text]))[0]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        # 服务端对单批 input 数量有限制,按 8 条一批拆分
        results: list[list[float]] = []
        for start in range(0, len(texts), 8):
            results.extend(await self._embed(texts[start : start + 8]))
        return results

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        import asyncio
        import random

        import httpx

        from app.contracts.errors import AgentError, ErrorCode

        payload = {"model": self._model_name, "input": texts, "dimensions": self._dimension}
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(
                        self._url,
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        json=payload,
                    )
                if resp.status_code != 200:
                    # 4xx(除限流)重试无意义,直接失败
                    if resp.status_code not in (408, 409, 429) and resp.status_code < 500:
                        raise AgentError(ErrorCode.RAG_ERROR,
                                         f"Embedding HTTP {resp.status_code}: {resp.text[:300]}")
                    raise httpx.HTTPStatusError("retryable", request=resp.request, response=resp)
                data = resp.json()
                vectors = [item["embedding"] for item in sorted(data["data"], key=lambda i: i["index"])]
                if len(vectors) != len(texts) or any(len(v) != self._dimension for v in vectors):
                    raise AgentError(ErrorCode.RAG_ERROR,
                                     f"Embedding 返回维度/数量异常: 期望 {len(texts)}x{self._dimension}")
                return vectors
            except AgentError:
                raise
            except Exception as e:  # noqa: BLE001 —— 网络/限流/5xx 重试
                last_error = e
                if attempt < self._max_attempts:
                    await asyncio.sleep(min(10.0, 1.5 * (2 ** (attempt - 1))) + random.uniform(0, 0.3))
        raise AgentError(ErrorCode.RAG_ERROR,
                         f"Embedding 请求重试 {self._max_attempts} 次仍失败: {last_error}")


# ---------------------------------------------------------------- 真实实现(fastembed)

class FastembedEmbedding:
    """fastembed 真实 Embedding 实现(ONNX Runtime,无需 PyTorch)。"""

    def __init__(self, model_name: str, dimension: int, *, model_path: str = "") -> None:
        import os

        from fastembed import TextEmbedding
        self._model_name = model_name
        self._dimension = dimension
        kwargs = {}
        if model_path and os.path.isdir(model_path):
            kwargs = {"specific_model_path": model_path, "local_files_only": True}
        self._emb = TextEmbedding(model_name=model_name, **kwargs)

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_version(self) -> str:
        return self._model_name

    async def embed_query(self, text: str) -> list[float]:
        return list(self._emb.embed([text]))[0].tolist()

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._emb.embed(texts)]


# ---------------------------------------------------------------- 工厂

def get_rag_embedding() -> EmbeddingPort:
    """RAG 向量空间实例(生产 1536 维,与仓库 knowledge-service 对齐)。"""
    s = get_settings()
    provider = "mock" if s.embedding_use_mock else s.embedding_provider
    if provider == "openai_compatible":
        return OpenAICompatibleEmbedding(
            s.rag_embedding_model, s.rag_embedding_dim,
            base_url=s.embedding_base_url, api_key=s.embedding_api_key,
        )
    if provider == "fastembed":
        return FastembedEmbedding(
            s.rag_embedding_model, s.rag_embedding_dim,
            model_path=s.embedding_model_path,
        )
    return MockEmbedding(s.rag_embedding_dim, s.rag_embedding_model)


def get_concept_embedding() -> EmbeddingPort:
    """Concept 向量空间实例(Agent 内部空间,默认 512 维 bge-small-zh)。"""
    s = get_settings()
    if s.embedding_use_mock:
        return MockEmbedding(s.concept_embedding_dim, s.concept_embedding_model)
    return FastembedEmbedding(
        s.concept_embedding_model, s.concept_embedding_dim,
        model_path=s.embedding_model_path,
    )
