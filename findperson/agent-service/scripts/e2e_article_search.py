"""E2E:新文章 待审核(不可检索) -> 审核通过(触发索引) -> 谁懂数据流芯片 命中作者。"""
import asyncio
import json
import re
import sys
import time
import urllib.request

sys.path.insert(0, r"C:\python\pycharm\shouwenzeren\agent-service")
from app.core import db

API = "http://127.0.0.1:8001"
AGENT = "http://127.0.0.1:8100"
OUT = []


def log(s):
    OUT.append(s)
    print(s)


def req(base, url, payload=None, token=None, method=None, raw=False):
    r = urllib.request.Request(
        base + url,
        data=json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})},
        method=method or ("POST" if payload is not None else "GET"))
    body = urllib.request.urlopen(r, timeout=180).read()
    return body.decode("utf-8") if raw else json.loads(body)


async def main():
    await db.init_pool()
    token = req(API, "/api/v1/auth/login",
                {"account": "123312312313", "password": "123456"})["token"]

    # 已有已发布的数据流芯片文章则复用,跳过创建/审核
    exist = await db.fetchrow(
        "SELECT id FROM public.contents WHERE title LIKE '%数据流芯片%' AND status='published' LIMIT 1")
    if exist:
        cid = exist["id"]
        log(f"1-3. 复用已发布文章 {cid}")
    else:
        # 1. 创建待审核文章
        c = req(API, "/api/v1/contents", {
            "title": "数据流芯片研发实践",
            "tags": ["数据流芯片"],
            "summary": "数据流芯片研发的经验总结",
            "body": "数据流芯片是一种按数据流动驱动计算的架构。我们在研发中完成了指令映射、片上网络调度和功耗优化，本文记录流图划分与验证流程。",
            "status": "待审核",
        }, token)
        cid = c["id"]
        log(f"1. 创建文章 {cid} status={c['status']}")

        ev = await db.fetchval(
            "SELECT count(*) FROM rag.publish_events WHERE resource_id=$1", cid)
        doc = await db.fetchval(
            "SELECT count(*) FROM rag.rag_documents WHERE document_id=$1", f"content-{cid}")
        log(f"2. 待审核态: 事件数={ev}(期望0) 索引={doc}(期望0)")

        # 2. 审核通过
        req(API, f"/api/v1/contents/{cid}/audit", {"action": "approve"}, token)
        ev2 = await db.fetchval(
            "SELECT count(*) FROM rag.publish_events WHERE resource_id=$1 AND status='pending'", cid)
        log(f"3. 审核后: pending 事件={ev2}(期望1)")

    # 3. 等消费者索引(10s 轮询)
    indexed = False
    meta = None
    for _ in range(8):
        await asyncio.sleep(5)
        row = await db.fetchrow(
            "SELECT metadata FROM rag.rag_chunks WHERE document_id=$1 LIMIT 1", f"content-{cid}")
        if row:
            indexed = True
            meta = row["metadata"]
            if isinstance(meta, str):
                meta = json.loads(meta)
            break
    log(f"4. 索引完成={indexed} author={((meta or {}).get('author_person_id'))}(期望 p-0001)")

    # 4. AGUI 问「谁懂数据流芯片」
    sess = req(AGENT, "/api/agui/sessions", {"title": "e2e-article", "userId": "p-0001"})
    text = req(AGENT, f"/api/agui/sessions/{sess['sessionId']}/messages", {
        "message": {"id": f"u-{time.time()}", "role": "user", "text": "谁懂数据流芯片"},
        "context": {"userId": "p-0001", "assistantMessageId": "a-e2e-1"}}, raw=True)
    names = list(dict.fromkeys(re.findall(r'"name":\s*"([^"]+)"', text)))
    answer = "".join(re.findall(r'"delta":\s*"((?:[^"\\]|\\.)*)"', text))
    hit = "茅泽婉" in names or "茅泽婉" in answer
    log(f"5. 问答命中茅泽婉={hit} names={names[:6]}")
    log(f"   回答片段: {answer[:150]}")

    with open("_e2e.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))
    await db.close_pool()

asyncio.run(main())
