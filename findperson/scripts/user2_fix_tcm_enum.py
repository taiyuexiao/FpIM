# -*- coding: utf-8 -*-
"""修复 tag_concept_map.mapping_type='migration' 枚举地雷:
1. 备份 31 行 -> public._tcm_migration_backup
2. UPDATE migration -> exact_alias
"""
import os
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import psycopg2

conn = psycopg2.connect(host="localhost", port=5432, user="postgres",
                        password=os.environ["PGPASSWORD"], dbname="shouwenzeren_newdb")
cur = conn.cursor()

cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name='_tcm_migration_backup'")
if cur.fetchone()[0] == 0:
    cur.execute("CREATE TABLE public._tcm_migration_backup AS "
                "SELECT * FROM agent.tag_concept_map WHERE mapping_type='migration'")
    print(f"备份: {cur.rowcount} 行 -> public._tcm_migration_backup")
else:
    print("备份已存在, 跳过")

cur.execute("UPDATE agent.tag_concept_map SET mapping_type='exact_alias' WHERE mapping_type='migration'")
print(f"修正: {cur.rowcount} 行 migration -> exact_alias")

cur.execute("SELECT mapping_type, count(*) FROM agent.tag_concept_map GROUP BY 1")
print("修正后分布:", dict(cur.fetchall()))

conn.commit()
conn.close()
print("已提交。")
