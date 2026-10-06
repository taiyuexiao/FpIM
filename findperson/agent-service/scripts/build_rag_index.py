"""从 Published OKF 全量构建 RAG 索引(§10.6 / 阶段 4)。

用法: .\\venv\\Scripts\\python.exe scripts\\build_rag_index.py [--incremental]
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.db import close_pool, init_pool  # noqa: E402
from app.okf.repository import OkfRepository  # noqa: E402
from app.rag.indexer import RagIndexer  # noqa: E402


async def main(incremental: bool = False) -> None:
    await init_pool()
    try:
        repo = OkfRepository()
        docs = await repo.list_published()   # 唯一输入:Published OKF(§10.6)
        print(f"[index] Published OKF: {len(docs)} 份")
        indexer = RagIndexer()
        if incremental:
            result = await indexer.incremental(docs)
        else:
            result = await indexer.rebuild(docs)
        print(f"[index] 完成: {result}")
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main("--incremental" in sys.argv))
