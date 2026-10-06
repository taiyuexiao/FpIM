# -*- coding: utf-8 -*-
"""把 user2.domains 全量同步进 agent 标签体系(raw_tags/person_tags/concept 映射)。
逐人提交, 单人失败不阻塞; 输出报告。复用 backend tag_sync 同一机制(幂等,只加不删)。
"""
import os
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

sys.path.insert(0, r"C:\python\pycharm\shouwenzeren\agent-service")
sys.path.insert(0, r"C:\python\pycharm\shouwenzeren\_repo_push\backend")

import psycopg2
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.services import tag_sync
from app.services.tag_sync import sync_person_domain_tags

# agent-service /agent/tags/link 端点当前挂死(已探测25s超时), 这里把 URL 指向废弃端口
# 让 _link_via_agent 立即连接失败(<1s), 走 tag_sync 设计好的兜底路径: 自动建 seed concept
tag_sync.settings.AGENT_SERVICE_URL = "http://127.0.0.1:9"

PW = os.environ["PGPASSWORD"]

# 取 user2 的 domains
conn = psycopg2.connect(host="localhost", port=5432, user="postgres", password=PW, dbname="shouwenzeren_newdb")
cur = conn.cursor()
cur.execute("SELECT id, name, domains FROM public.user2 ORDER BY id")
people = [(r[0], r[1], r[2] or []) for r in cur.fetchall()]
conn.close()
print(f"待同步: {len(people)} 人")

engine = create_engine(f"postgresql+psycopg2://postgres:{PW}@localhost:5432/shouwenzeren_newdb")
Session = sessionmaker(bind=engine)

ok, failed = 0, []
for pid, name, domains in people:
    sess = Session()
    try:
        sync_person_domain_tags(sess, person_id=pid, domains=list(domains))
        sess.commit()
        ok += 1
    except Exception as e:
        sess.rollback()
        failed.append((pid, name, str(e)[:120]))
    finally:
        sess.close()
    if ok % 50 == 0:
        print(f"  进度 {ok}/{len(people)}")

print(f"\n同步完成: 成功 {ok} 人, 失败 {len(failed)} 人")
for f in failed[:10]:
    print("  失败:", f)

# 验证: agent.person_tags 现状
conn = psycopg2.connect(host="localhost", port=5432, user="postgres", password=PW, dbname="shouwenzeren_newdb")
cur = conn.cursor()
cur.execute("SELECT count(DISTINCT person_id) FROM agent.person_tags WHERE is_active")
print("agent.person_tags 覆盖人数:", cur.fetchone()[0])
cur.execute("""SELECT rt.text FROM agent.person_tags pt JOIN agent.raw_tags rt ON rt.tag_id=pt.tag_id
               WHERE pt.person_id='P0001' AND pt.is_active""")
print("刘成彦的标签:", [r[0] for r in cur.fetchall()])
conn.close()

with open(r"C:\python\pycharm\shouwenzeren\_newdb\sync_user2_tags_report.txt", "w", encoding="utf-8") as f:
    f.write(f"成功 {ok} 人, 失败 {len(failed)} 人\n" + "\n".join(str(x) for x in failed))
