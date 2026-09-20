"""CachePort 与 LocalCache 实现(V1.2 §14.4)。

V1 无 Redis 资源(§23:使用 LocalCache 实现),业务模块只依赖 CachePort 接口,
后续可无缝替换为 Redis 实现。

缓存对象(§14.4):concept dictionary、tag_concept_map、query→concept、
MCP short cache、session state。
"""
from __future__ import annotations

import time
from typing import Any, Protocol


class CachePort(Protocol):
    """缓存抽象端口。业务模块只依赖此接口。"""

    async def get(self, key: str) -> Any | None: ...

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def clear(self) -> None: ...


class LocalCache:
    """进程内缓存:dict + TTL。线程内 asyncio 单线程模型下足够 V1 使用。"""

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float | None]] = {}

    async def get(self, key: str) -> Any | None:
        item = self._store.get(key)
        if item is None:
            return None
        value, expires_at = item
        if expires_at is not None and time.time() > expires_at:
            self._store.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        expires_at = time.time() + ttl_seconds if ttl_seconds else None
        self._store[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)


# 常用缓存键命名,集中管理避免散落各处
class CacheKeys:
    """统一缓存键前缀(§14.4 缓存对象)。"""

    CONCEPT_DICT = "concept:dict"                 # 概念词典全量
    TAG_CONCEPT_MAP = "concept:tcm"               # tag_concept_map 全量
    QUERY_CONCEPT = "concept:q:{query}"           # query→concept 结果
    MCP_SHORT = "mcp:{tool}:{params_hash}"        # MCP 短缓存
    SESSION_STATE = "session:{session_id}"        # 会话状态


_cache: LocalCache | None = None


def get_cache() -> LocalCache:
    """缓存单例。"""
    global _cache
    if _cache is None:
        _cache = LocalCache()
    return _cache
