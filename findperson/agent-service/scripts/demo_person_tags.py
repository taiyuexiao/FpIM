"""打印指定人员的负责领域标签(raw_tags)与部门角色。"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.db import close_pool, fetch, init_pool  # noqa: E402

NAMES = ["宋超", "田桂兰", "何丽", "唐丹丹", "林宁", "佘阳", "刘欢", "倪刚"]


async def main() -> None:
    await init_pool()
    rows = await fetch(
        "SELECT p.id, p.name, p.department, p.role,"
        "       string_agg(rt.text, '、' ORDER BY rt.text) AS tags"
        " FROM public.people p"
        " LEFT JOIN agent.person_tags pt ON pt.person_id = p.id AND pt.is_active"
        " LEFT JOIN agent.raw_tags rt ON rt.tag_id = pt.tag_id"
        " WHERE p.name = ANY($1)"
        " GROUP BY p.id, p.name, p.department, p.role"
        " ORDER BY p.name",
        NAMES)
    for r in rows:
        print(f"{r['name']}({r['id']})|{r['department']}|{r['role']}")
        print(f"   负责领域: {r['tags']}")
    await close_pool()


asyncio.run(main())
