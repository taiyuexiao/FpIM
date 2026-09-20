import asyncio, asyncpg, os

async def main():
    conn = await asyncpg.connect(
        host='localhost', port=5432, database='shouwenzeren_ext',
        user='postgres', password=os.environ['PGPASSWORD']
    )
    for pid in ['P0004', 'P0012', 'P0020', 'P0028', 'P0036']:
        rows = await conn.fetch(
            'SELECT rt.text FROM agent.person_tags pt '
            'JOIN agent.raw_tags rt ON rt.tag_id=pt.tag_id '
            'WHERE pt.person_id=$1', pid
        )
        print(pid, [r['text'] for r in rows])
    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())
