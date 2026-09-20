# -*- coding: utf-8 -*-
"""切换 users -> user2 的数据库侧操作(单事务,幂等):
1. 备份 people 现场 -> public._people_backup_pre_user2
2. 触发器换源: users 上 DROP, user2 上新建(同一同步函数)
3. people 从 user2 全量刷新(upsert, 列映射与触发器一致)
4. 发 208 条 person_changed 事件(agent-service 10s 轮询消费 -> OKF重发+RAG增量索引)
"""
import os
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import psycopg2

conn = psycopg2.connect(host="localhost", port=5432, user="postgres",
                        password=os.environ["PGPASSWORD"], dbname="shouwenzeren_newdb")
cur = conn.cursor()

# 1. 备份 people(只在不存在时建, 保留第一现场)
cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name='_people_backup_pre_user2'")
if cur.fetchone()[0] == 0:
    cur.execute("CREATE TABLE public._people_backup_pre_user2 AS SELECT * FROM public.people")
    print("1. people 已备份 -> _people_backup_pre_user2")
else:
    print("1. 备份表已存在, 跳过(保留第一现场)")

# 2. 触发器换源
cur.execute("DROP TRIGGER IF EXISTS trg_users_sync ON public.users")
cur.execute("""CREATE TRIGGER trg_user2_sync AFTER INSERT OR UPDATE ON public.user2
               FOR EACH ROW EXECUTE FUNCTION public.sync_users_to_people()""")
print("2. 触发器: users.trg_users_sync 已DROP, user2.trg_user2_sync 已建")

# 3. people 全量刷新(与 sync_users_to_people 列映射一致)
cur.execute("""
INSERT INTO public.people(id, account, phone, name, department, department_id,
                          role, role_type, contact, self_portrait, completeness,
                          status, updated_at)
SELECT u.id, u.account, u.phone, u.name,
       coalesce(d.name, ''), u.department_id, coalesce(u.role, ''), 'user', u.contact,
       coalesce(u.self_portrait, ''), coalesce(u.completeness, 0),
       CASE WHEN u.active THEN 'active' ELSE 'inactive' END, now()
FROM public.user2 u LEFT JOIN public.departments d ON d.id = u.department_id
ON CONFLICT (id) DO UPDATE SET
    account=EXCLUDED.account, phone=EXCLUDED.phone, name=EXCLUDED.name,
    department=EXCLUDED.department, department_id=EXCLUDED.department_id,
    role=EXCLUDED.role, contact=EXCLUDED.contact, self_portrait=EXCLUDED.self_portrait,
    completeness=EXCLUDED.completeness, status=EXCLUDED.status, updated_at=now()""")
print(f"3. people 全量刷新: {cur.rowcount} 行")

# 4. person_changed 事件(清掉可能残留的 pending, 避免重复消费)
cur.execute("DELETE FROM rag.publish_events WHERE status='pending' AND created_by='user2-switch'")
cur.execute("""INSERT INTO rag.publish_events(event_type, resource_id, status, created_by)
               SELECT 'person_changed', id, 'pending', 'user2-switch' FROM public.user2""")
print(f"4. person_changed 事件: {cur.rowcount} 条 (agent-service 10s 轮询消费)")

# 抽查
cur.execute("SELECT id, name, self_portrait FROM public.people WHERE id='P0001'")
r = cur.fetchone()
print(f"抽查 people.P0001: {r[1]} | self_portrait={r[2]}")

conn.commit()
conn.close()
print("已提交。")
