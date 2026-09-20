import asyncio, asyncpg, os

async def main():
    conn = await asyncpg.connect(
        host='localhost', port=5432, database='shouwenzeren_ext',
        user='postgres', password=os.environ['PGPASSWORD']
    )
    ptr = await conn.fetchval("SELECT active_version FROM rag.rag_index_pointer LIMIT 1")
    print(f"active_version={ptr}")
    for q in [
        ("people", "SELECT count(*) FROM public.people"),
        ("contents", "SELECT count(*) FROM public.contents"),
        ("departments", "SELECT count(*) FROM public.departments"),
        ("concepts", "SELECT count(*) FROM agent.concepts"),
        ("okf_docs active", f"SELECT count(*) FROM rag.rag_documents WHERE status='active' AND index_version={ptr}"),
        ("chunks", f"SELECT count(*) FROM rag.rag_chunks WHERE index_version={ptr}"),
        ("null embeddings", f"SELECT count(*) FROM rag.rag_chunks WHERE index_version={ptr} AND embedding IS NULL"),
    ]:
        try:
            n = await conn.fetchval(q[1])
            print(f"{q[0]}={n}")
        except Exception as e:
            print(f"{q[0]}: {e}")
    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())
