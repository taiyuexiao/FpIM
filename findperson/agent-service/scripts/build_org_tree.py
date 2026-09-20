"""组织树构建 + 负责人指派 + manager_id 回填(验收#7)。

基于现有 20 个部门的命名前缀补全树结构:
- "X-Y" 形式 → 父部门 X(不存在则创建,如 金融科技部/数据平台部)
- 每个部门指派负责人 = 部门内 id 最小成员;无成员的父部门取第一个子部门负责人
- 回填 users.manager_id:成员→本部门负责人;负责人→父部门负责人(根部门负责人为顶层,无上级)

幂等:已设置的 parent_id/leader_id/manager_id 不覆盖。
用法: ..\\venv\\Scripts\\python.exe scripts\\build_org_tree.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402

from app.config import get_settings  # noqa: E402


async def main() -> None:
    s = get_settings()
    conn = await asyncpg.connect(
        host=s.pghost, port=s.pgport, user=s.pguser, password=s.pgpassword, database=s.pgdatabase,
    )
    try:
        depts = await conn.fetch("SELECT id, name, parent_id, leader_id FROM public.departments ORDER BY id")
        by_name = {d["name"]: dict(d) for d in depts}

        # ---- 1. 补缺失的父部门 ----
        next_id = max(d["id"] for d in depts) + 1
        for d in depts:
            if "-" in d["name"]:
                parent_name = d["name"].split("-", 1)[0]
                if parent_name not in by_name:
                    await conn.execute(
                        "INSERT INTO public.departments(id, name, level, path, status, sort_order)"
                        " VALUES($1,$2,1,$3,'active',$1)",
                        next_id, parent_name, parent_name)
                    by_name[parent_name] = {"id": next_id, "name": parent_name,
                                            "parent_id": None, "leader_id": None}
                    print(f"[dept+] {parent_name} (id={next_id})")
                    next_id += 1

        # ---- 2. 设置 parent_id(按名称前缀,幂等) ----
        for name, d in by_name.items():
            if "-" in name and d["parent_id"] is None:
                parent = by_name.get(name.split("-", 1)[0])
                if parent:
                    await conn.execute(
                        "UPDATE public.departments SET parent_id=$1, level=2 WHERE id=$2",
                        parent["id"], d["id"])
                    d["parent_id"] = parent["id"]
                    print(f"[tree] {name} -> {parent['name']}")

        # ---- 2.5 统一根:所有根部门挂到「总行」下(每个人有上级,仅总行负责人为顶层) ----
        root = by_name.get("总行")
        if not root:
            root_id = await conn.fetchval("SELECT coalesce(max(id),0)+1 FROM public.departments")
            await conn.execute(
                "INSERT INTO public.departments(id, name, level, path, status, sort_order)"
                " VALUES($1,'总行',1,'总行','active',0)", root_id)
            root = {"id": root_id, "name": "总行", "parent_id": None, "leader_id": None}
            by_name["总行"] = root
            print(f"[dept+] 总行 (id={root_id})")
        for name, d in by_name.items():
            if name != "总行" and "-" not in name and d["parent_id"] is None:
                await conn.execute(
                    "UPDATE public.departments SET parent_id=$1 WHERE id=$2", root["id"], d["id"])
                d["parent_id"] = root["id"]
                print(f"[tree] {name} -> 总行")

        # ---- 3. 指派负责人(幂等) ----
        for name, d in sorted(by_name.items(), key=lambda kv: kv[1]["id"]):
            if d["leader_id"]:
                continue
            leader = await conn.fetchval(
                "SELECT id FROM public.users WHERE department_id=$1 AND active ORDER BY id LIMIT 1",
                d["id"])
            if not leader:
                # 无直属成员的父部门:取第一个子部门的负责人
                leader = await conn.fetchval(
                    "SELECT leader_id FROM public.departments"
                    " WHERE parent_id=$1 AND leader_id IS NOT NULL ORDER BY id LIMIT 1",
                    d["id"])
            if leader:
                await conn.execute("UPDATE public.departments SET leader_id=$1 WHERE id=$2",
                                   leader, d["id"])
                d["leader_id"] = leader
                print(f"[leader] {name} -> {leader}")

        # ---- 4. 回填 manager_id(幂等;触发器会同步到 people) ----
        r1 = await conn.execute(
            "UPDATE public.users u SET manager_id = d.leader_id"
            " FROM public.departments d"
            " WHERE u.department_id = d.id AND d.leader_id IS NOT NULL"
            " AND d.leader_id <> u.id AND u.manager_id IS NULL")
        r2 = await conn.execute(
            "UPDATE public.users u SET manager_id = pd.leader_id"
            " FROM public.departments d JOIN public.departments pd ON pd.id = d.parent_id"
            " WHERE u.department_id = d.id AND d.leader_id = u.id"
            " AND pd.leader_id IS NOT NULL AND pd.leader_id <> u.id AND u.manager_id IS NULL")
        print(f"[manager] members: {r1}, leaders: {r2}")

        # ---- 4.5 沿部门链向上找第一个非本人的负责人(父子部门同一负责人的情况) ----
        root_leader = await conn.fetchval(
            "SELECT leader_id FROM public.departments WHERE name='总行'")
        rows = await conn.fetch(
            "SELECT u.id, u.department_id FROM public.users u"
            " WHERE u.manager_id IS NULL AND u.id <> $1", root_leader or '')
        for row in rows:
            dept_id = row["department_id"]
            manager = None
            while dept_id and not manager:
                d = await conn.fetchrow(
                    "SELECT parent_id, leader_id FROM public.departments WHERE id=$1", dept_id)
                if not d:
                    break
                if d["leader_id"] and d["leader_id"] != row["id"] and dept_id != row["department_id"]:
                    manager = d["leader_id"]
                dept_id = d["parent_id"]
            manager = manager or root_leader
            if manager and manager != row["id"]:
                await conn.execute("UPDATE public.users SET manager_id=$1 WHERE id=$2",
                                   manager, row["id"])
                print(f"[manager+] {row['id']} -> {manager}")

        stats = await conn.fetchrow(
            "SELECT count(*) FILTER (WHERE manager_id IS NOT NULL) AS with_manager, count(*) AS total"
            " FROM public.users")
        print(f"[done] {stats['with_manager']}/{stats['total']} 用户已有上级(顶层负责人除外)")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
