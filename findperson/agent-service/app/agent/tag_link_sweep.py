"""未映射标签清扫(tag_link_sweep):新标签落库后的 LLM 概念归并执行器。

设计(§7.4 常态化):
- 写侧(backend tag_sync)只做 raw_tag/person_tag 落库,不再同步建概念;
- 本任务每 30s 扫一遍「无概念映射的 raw_tag」,逐个走 RawTagConceptLinker.link_tag:
  精确复用 → 五级召回 → 高置信自动映射 → 第六级 LLM 受约束消歧
  → 能挂已有概念就挂(LINK_EXISTING),确认是新事物才建新 seed 概念(CREATE_CANDIDATE);
- 与发布事件消费同模式:单条失败不阻塞,30s 轮询。
"""
from __future__ import annotations

import asyncio
import logging

from app.agent.concept_governance import RawTagConceptLinker
from app.core import db

logger = logging.getLogger(__name__)

POLL_INTERVAL_S = 30
_BATCH = 5


async def sweep_once() -> dict:
    """处理一批未映射 raw_tag,返回统计。"""
    rows = await db.fetch(
        "SELECT tag_id, text FROM agent.raw_tags"
        " WHERE tag_id NOT IN (SELECT tag_id FROM agent.tag_concept_map)"
        " ORDER BY created_at LIMIT $1", _BATCH)
    stats = {"linked": 0, "failed": 0}
    if not rows:
        return stats
    linker = RawTagConceptLinker()
    for r in rows:
        try:
            result = await linker.link_tag(r["text"])
            stats["linked"] += 1
            logger.info("tag_link_sweep 归并: %s -> %s", r["text"], result.get("action"))
        except Exception as e:  # noqa: BLE001 —— 单条失败不阻塞队列
            stats["failed"] += 1
            logger.warning("tag_link_sweep 失败: %s %s", r["text"], e)
    return stats


async def run_tag_link_sweep(stop: asyncio.Event) -> None:
    """后台轮询任务(main.py startup 启动,shutdown 置 stop)。"""
    while not stop.is_set():
        try:
            stats = await sweep_once()
            if stats["linked"] or stats["failed"]:
                logger.info("tag_link_sweep 本轮: %s", stats)
        except Exception as e:  # noqa: BLE001 —— 轮询异常下轮重试
            logger.warning("tag_link_sweep 轮询异常: %s", e)
        try:
            await asyncio.wait_for(stop.wait(), timeout=POLL_INTERVAL_S)
        except asyncio.TimeoutError:
            pass
