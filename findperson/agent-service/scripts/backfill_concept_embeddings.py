"""回填 Concept 向量(1024 维,独立向量空间,§10.8)。

为 agent.concepts 中 embedding 为空的 seed/active 概念计算 Mock Embedding。
模型版本写入 embedding_model,符合「索引模型版本化,不跨模型混写」(§23)。

用法: .\\venv\\Scripts\\python.exe scripts\\backfill_concept_embeddings.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.core.embedding_client import get_concept_embedding  # noqa: E402


async def main() -> None:
    s = get_settings()
    emb = get_concept_embedding()
    conn = await asyncpg.connect(
        host=s.pghost, port=s.pgport, user=s.pguser, password=s.pgpassword, database=s.pgdatabase,
    )
    try:
        rows = await conn.fetch(
            "SELECT concept_id, canonical_name, description FROM agent.concepts"
            " WHERE embedding IS NULL AND status IN ('seed','active')"
        )
        print(f"[backfill] 待回填概念: {len(rows)}")
        texts = [f"{r['canonical_name']} {r['description']}".strip() for r in rows]
        vectors = await emb.embed_documents(texts)
        async with conn.transaction():
            for r, vec in zip(rows, vectors):
                await conn.execute(
                    "UPDATE agent.concepts SET embedding=$1::vector, embedding_model=$2"
                    " WHERE concept_id=$3",
                    f"[{','.join(f'{x:.6f}' for x in vec)}]", emb.model_version, r["concept_id"],
                )
        n = await conn.fetchval(
            "SELECT count(*) FROM agent.concepts WHERE embedding IS NOT NULL"
        )
        print(f"[backfill] 完成,已向量化的概念: {n} (模型 {emb.model_version}, {emb.dimension} 维)")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
