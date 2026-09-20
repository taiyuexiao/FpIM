import asyncio, asyncpg, os

async def main():
    conn = await asyncpg.connect(
        host='localhost', port=5432, database='shouwenzeren_ext',
        user='postgres', password=os.environ['PGPASSWORD']
    )
    cols = await conn.fetch(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema='rag' AND table_name='rag_index_pointer'"
    )
    print("rag_index_pointer columns:", [dict(c) for c in cols])
    ptr_rows = await conn.fetch("SELECT * FROM rag.rag_index_pointer")
    print("pointer rows:", [dict(r) for r in ptr_rows])
    current = ptr_rows[0].get('current_version') or ptr_rows[0].get('index_version')
    print(f"current version = {current}")
    if current != 1:
        print("deleting version 1...")
        await conn.execute("DELETE FROM rag.rag_chunks WHERE index_version=1")
        await conn.execute("DELETE FROM rag.rag_documents WHERE index_version=1")
        await conn.execute("DELETE FROM rag.rag_index_jobs WHERE index_version=1")
        print("done")
    for q in [
        "SELECT count(*) FROM rag.rag_chunks",
        "SELECT count(*) FROM rag.rag_documents",
        "SELECT count(*) FROM rag.rag_documents WHERE status='active' AND index_version=$1",
    ]:
        if "$1" in q:
            n = await conn.fetchval(q, current)
        else:
            n = await conn.fetchval(q)
        print(f"{q} -> {n}")
    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())
