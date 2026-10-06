"""publish_events 消费者:业务变更 → OKF 重发布 → RAG 增量索引。

backend 在内容发布/变更/删除、人员资料/画像变更后写 rag.publish_events(pending);
本模块轮询消费:
- content_published/content_changed → 重建该内容 OKF + RagIndexer.incremental
- content_deleted               → RagIndexer.invalidate
- person_changed                → 重建该人员 OKF(含同事评价聚合正文) + incremental

消费失败标记 failed 不阻塞后续事件;轮询间隔 10s。
"""
from __future__ import annotations

import asyncio
import json
import logging

from app.core import db
from app.okf.builders import build_content_doc, build_person_profile_doc
from app.okf.publisher import OkfPublisher
from app.okf.repository import OkfRepository
from app.rag.indexer import RagIndexer

logger = logging.getLogger(__name__)

POLL_INTERVAL_S = 10
_BATCH = 20


async def _build_content_okf(content_id: str):
    row = await db.fetchrow(
        "SELECT c.*, p.name AS owner_name, p.department_id AS owner_dept_id"
        " FROM public.contents c LEFT JOIN public.people p ON p.id = c.owner_id"
        " WHERE c.id=$1", content_id)
    if not row:
        return None
    return build_content_doc(dict(row), owner_name=row["owner_name"] or "",
                             owner_department_id=row["owner_dept_id"])


async def _build_person_okf(person_id: str):
    row = await db.fetchrow("SELECT * FROM public.people WHERE id=$1", person_id)
    if not row:
        return None
    # 同事评价聚合正文(§10.4 白名单允许,低权重)
    tags = await db.fetch(
        "SELECT tag_name FROM public.peer_reviews WHERE person_id=$1", person_id)
    reviews_text = "、".join(sorted({r["tag_name"] for r in tags}))
    return build_person_profile_doc(dict(row), reviews_text=reviews_text)


async def process_pending_events() -> dict:
    """消费一批 pending 事件,返回统计。供轮询任务与手工触发复用。"""
    events = await db.fetch(
        "SELECT id, event_type, resource_id FROM rag.publish_events"
        " WHERE status='pending' ORDER BY id LIMIT $1", _BATCH)
    stats = {"consumed": 0, "failed": 0}
    if not events:
        return stats
    publisher = OkfPublisher(OkfRepository())
    indexer = RagIndexer()
    for event in events:
        try:
            etype, rid = event["event_type"], event["resource_id"]
            if etype in ("content_published", "content_changed"):
                doc = await _build_content_okf(rid)
                if doc is None:
                    await indexer.invalidate([f"content-{rid}"])
                else:
                    await publisher.publish(doc)
                    latest = await publisher._repo.get_latest(doc.metadata.id)
                    await indexer.incremental([latest or doc])
            elif etype == "content_deleted":
                await indexer.invalidate([f"content-{rid}"])
            elif etype == "person_changed":
                doc = await _build_person_okf(rid)
                if doc is not None:
                    await publisher.publish(doc)
                    latest = await publisher._repo.get_latest(doc.metadata.id)
                    await indexer.incremental([latest or doc])
            await db.execute(
                "UPDATE rag.publish_events SET status='consumed' WHERE id=$1", event["id"])
            stats["consumed"] += 1
        except Exception as e:  # noqa: BLE001 —— 单事件失败不阻塞队列
            logger.warning("publish_event %s 消费失败: %s", event["id"], e)
            await db.execute(
                "UPDATE rag.publish_events SET status='failed' WHERE id=$1", event["id"])
            stats["failed"] += 1
    return stats


async def run_event_consumer(stop: asyncio.Event) -> None:
    """后台轮询任务(main.py startup 启动,shutdown 置 stop)。"""
    # 启动时把上轮失败事件重新入队一次(覆盖服务重启窗口/瞬时异常);
    # 本轮再失败仍标 failed,避免持久错误死循环
    try:
        reset = await db.execute(
            "UPDATE rag.publish_events SET status='pending' WHERE status='failed'")
        if reset and reset != "UPDATE 0":
            logger.info("publish_events 失败事件重入队: %s", reset)
    except Exception as e:  # noqa: BLE001
        logger.warning("publish_events 失败事件重入队异常: %s", e)
    while not stop.is_set():
        try:
            stats = await process_pending_events()
            if stats["consumed"] or stats["failed"]:
                logger.info("publish_events 消费: %s", json.dumps(stats))
        except Exception as e:  # noqa: BLE001 —— 轮询异常下轮重试
            logger.warning("publish_events 轮询异常: %s", e)
        try:
            await asyncio.wait_for(stop.wait(), timeout=POLL_INTERVAL_S)
        except asyncio.TimeoutError:
            pass
