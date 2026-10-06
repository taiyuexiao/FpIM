"""PostgreSQL 数据访问基础能力(V1.2 §14.3)。

全项目唯一的数据库入口:连接池、事务、超时、health、repository 基础。
禁止各业务模块自行维护数据库连接。
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg

from app.config import get_settings
from app.contracts.errors import AgentError, ErrorCode

_pool: asyncpg.Pool | None = None


async def init_pool(min_size: int = 2, max_size: int = 10) -> asyncpg.Pool:
    """初始化连接池(应用启动时调用一次)。"""
    global _pool
    if _pool is None:
        s = get_settings()
        try:
            _pool = await asyncpg.create_pool(
                host=s.pghost,
                port=s.pgport,
                database=s.pgdatabase,
                user=s.pguser,
                password=s.pgpassword,
                min_size=min_size,
                max_size=max_size,
                command_timeout=30,
            )
        except Exception as e:  # noqa: BLE001 —— 统一转成内部错误
            raise AgentError(ErrorCode.INTERNAL_ERROR, f"数据库连接池初始化失败: {e}") from e
    return _pool


async def close_pool() -> None:
    """关闭连接池(应用关闭/测试结束时调用)。"""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    """获取已初始化的连接池。未初始化时抛内部错误而不是隐式建连。"""
    if _pool is None:
        raise AgentError(ErrorCode.INTERNAL_ERROR, "数据库连接池未初始化,请先调用 init_pool()")
    return _pool


@asynccontextmanager
async def connection() -> AsyncIterator[asyncpg.Connection]:
    """借出一条连接(自动归还)。"""
    pool = get_pool()
    async with pool.acquire() as conn:
        yield conn


@asynccontextmanager
async def transaction() -> AsyncIterator[asyncpg.Connection]:
    """借出一条连接并开启事务(提交/回滚自动管理)。"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            yield conn


async def health() -> bool:
    """数据库健康检查(§14.3 health 要求)。"""
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return True
    except Exception:  # noqa: BLE001
        return False


async def fetch(query: str, *args: Any) -> list[asyncpg.Record]:
    """查询多行。"""
    async with connection() as conn:
        return await conn.fetch(query, *args)


async def fetchrow(query: str, *args: Any) -> asyncpg.Record | None:
    """查询单行。"""
    async with connection() as conn:
        return await conn.fetchrow(query, *args)


async def fetchval(query: str, *args: Any) -> Any:
    """查询单值。"""
    async with connection() as conn:
        return await conn.fetchval(query, *args)


async def execute(query: str, *args: Any) -> str:
    """执行写语句。"""
    async with connection() as conn:
        return await conn.execute(query, *args)
