"""backend 分支对接:执行 05_backend_compat.sql + 初始 users 数据。

- users 从 people 复制(id/account/name/phone/department_id/role/contact/self_portrait);
- 所有演示账号初始密码统一为 123456(bcrypt),首次登录后应改密;
- users→people 由 05 的触发器实时同步,backend 写操作自动反映到 Agent 侧。

用法: .\\venv\\Scripts\\python scripts\\align_backend_schema.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
import bcrypt

from app.config import get_settings

DEFAULT_PASSWORD = "123456"


async def main() -> None:
    s = get_settings()
    conn = await asyncpg.connect(host=s.pghost, port=s.pgport, user=s.pguser,
                                 password=s.pgpassword, database=s.pgdatabase)
    try:
        ddl = (Path(__file__).resolve().parent / "ddl" / "05_backend_compat.sql").read_text(encoding="utf-8")
        await conn.execute(ddl)
        print("[align] 05_backend_compat.sql 执行完成")

        password_hash = bcrypt.hashpw(DEFAULT_PASSWORD.encode(), bcrypt.gensalt(rounds=12)).decode()
        rows = await conn.fetch(
            "SELECT id, account, phone, name, department_id, role, contact, self_portrait,"
            "       completeness, status FROM public.people")
        n = 0
        for r in rows:
            await conn.execute(
                "INSERT INTO public.users(id, account, name, password_hash, phone, department_id,"
                " role, contact, self_portrait, completeness, active)"
                " VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)"
                " ON CONFLICT (id) DO NOTHING",
                r["id"], r["account"] or r["id"], r["name"], password_hash,
                (r["phone"] or "")[:20] or None, r["department_id"], r["role"],
                r["contact"], r["self_portrait"], r["completeness"],
                r["status"] == "active")
            n += 1
        print(f"[align] users 初始复制完成: {n} 行(初始密码统一 {DEFAULT_PASSWORD})")

        # domains 回填:名片库「领域标签」取自 Agent 侧 self 标签(每人至多 5 个)
        await conn.execute(
            "UPDATE public.users u SET domains = to_jsonb(sub.tags) FROM ("
            "  SELECT pt.person_id, array_agg(rt.text ORDER BY rt.text) AS tags FROM ("
            "    SELECT DISTINCT person_id, tag_id FROM agent.person_tags"
            "    WHERE is_active AND source='self'"
            "  ) pt JOIN agent.raw_tags rt ON rt.tag_id = pt.tag_id"
            "  GROUP BY pt.person_id"
            ") sub WHERE u.id = sub.person_id AND (u.domains IS NULL OR jsonb_array_length(u.domains) = 0)")
        # 数组截断到 5 个
        await conn.execute(
            "UPDATE public.users SET domains = (SELECT to_jsonb(array_agg(x)) FROM ("
            "  SELECT jsonb_array_elements_text(domains) AS x LIMIT 5) t)"
            " WHERE domains IS NOT NULL AND jsonb_array_length(domains) > 5")
        n_domains = await conn.fetchval(
            "SELECT count(*) FROM public.users WHERE domains IS NOT NULL AND jsonb_array_length(domains) > 0")
        print(f"[align] domains 回填: {n_domains} 人有领域标签")
        print(f"[align] 校验: users={await conn.fetchval('SELECT count(*) FROM public.users')},"
          f" sessions={await conn.fetchval('SELECT count(*) FROM public.sessions')}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
