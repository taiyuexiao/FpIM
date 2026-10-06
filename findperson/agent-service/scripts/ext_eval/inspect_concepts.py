import asyncio, asyncpg, os

async def main():
    conn = await asyncpg.connect(
        host='localhost', port=5432, database='shouwenzeren_ext',
        user='postgres', password=os.environ['PGPASSWORD']
    )
    cols = await conn.fetch(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema='agent' AND table_name='concepts' ORDER BY ordinal_position"
    )
    print("columns:")
    for c in cols:
        print(f"  {c['column_name']} {c['data_type']}")
    rows = await conn.fetch("SELECT * FROM agent.concepts ORDER BY concept_id LIMIT 20")
    print("\nconcepts:")
    for r in rows:
        print(dict(r))
    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())
