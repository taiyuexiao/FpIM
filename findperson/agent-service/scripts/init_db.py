"""初始化数据库 shouwenzeren_v2:建库、扩展、三 schema、执行 DDL。

可重复执行(全部 IF NOT EXISTS)。
用法: .\\venv\\Scripts\\python.exe scripts\\init_db.py
"""
import asyncio
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402

DDL_DIR = Path(__file__).resolve().parent / "ddl"
DDL_FILES = ["01_public.sql", "02_agent.sql", "03_rag.sql", "04_agent_views.sql"]


async def main() -> None:
    s = get_settings()

    # 1) 连到默认 postgres 库建库
    admin = await asyncpg.connect(
        host=s.pghost, port=s.pgport, user=s.pguser, password=s.pgpassword, database="postgres",
    )
    try:
        exists = await admin.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", s.pgdatabase)
        if not exists:
            await admin.execute(f'CREATE DATABASE "{s.pgdatabase}"')
            print(f"[init_db] 创建数据库 {s.pgdatabase}")
        else:
            print(f"[init_db] 数据库 {s.pgdatabase} 已存在")
    finally:
        await admin.close()

    # 2) 连新库:扩展 + schema + DDL
    conn = await asyncpg.connect(
        host=s.pghost, port=s.pgport, user=s.pguser, password=s.pgpassword, database=s.pgdatabase,
    )
    try:
        for ext in ("vector", "pg_trgm"):
            await conn.execute(f"CREATE EXTENSION IF NOT EXISTS {ext}")
            print(f"[init_db] 扩展 {ext} 就绪")
        for schema in ("agent", "rag"):
            await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
            print(f"[init_db] schema {schema} 就绪")
        for name in DDL_FILES:
            sql = (DDL_DIR / name).read_text(encoding="utf-8")
            await conn.execute(sql)
            print(f"[init_db] 执行 {name} 完成")
        # 验证核心表
        for fq in ("public.people", "public.responsibility_assignments",
                   "agent.concepts", "agent.raw_tags", "rag.rag_documents", "rag.rag_chunks"):
            await conn.fetchval(f"SELECT count(*) FROM {fq}")
        print("[init_db] 全部核心表校验通过")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
