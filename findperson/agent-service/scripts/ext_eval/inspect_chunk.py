import asyncio, asyncpg, json, os

async def main():
    conn = await asyncpg.connect(
        host='localhost', port=5432, database='shouwenzeren_ext',
        user='postgres', password=os.environ['PGPASSWORD']
    )
    ptr = await conn.fetchval("SELECT active_version FROM rag.rag_index_pointer WHERE id=1")
    rows = await conn.fetch(
        "SELECT chunk_id, document_id, section_path, metadata, LEFT(content, 100) AS content "
        "FROM rag.rag_chunks WHERE index_version=$1 AND content ILIKE '%环境部署%' LIMIT 5",
        ptr
    )
    for r in rows:
        print('---')
        print('chunk_id', r['chunk_id'])
        print('document_id', r['document_id'])
        print('section_path', r['section_path'])
        print('metadata', json.dumps(r['metadata'], ensure_ascii=False) if isinstance(r['metadata'], dict) else r['metadata'])
        print('content', r['content'])
    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())
