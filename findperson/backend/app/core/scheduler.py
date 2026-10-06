"""统计刷新定时任务（P3 ADM-05）

用 FastAPI lifespan 内的后台 asyncio 循环实现，不引入 APScheduler：
- 单 worker 开发环境足够，避免 APScheduler 在多 worker 下的重复执行问题。
- statistics_definitions.refresh_cron 当前种子数据为空，故统一按固定间隔刷新；
  后续若补齐逐条 cron，可在这里按 cron 解析调度。
"""
import asyncio
import contextlib
import logging

from fastapi import FastAPI

from .statistics import refresh_statistics

logger = logging.getLogger(__name__)

_REFRESH_INTERVAL_SECONDS = 3600  # 每小时刷新一次


async def _statistics_loop() -> None:
    while True:
        await asyncio.sleep(_REFRESH_INTERVAL_SECONDS)
        try:
            result = await asyncio.to_thread(refresh_statistics)
            logger.info("statistics refreshed: %s", result)
        except Exception as e:
            logger.warning("statistics refresh failed: %s", e)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时立即刷新一次，保证 statistics_data 有首份快照
    try:
        await asyncio.to_thread(refresh_statistics)
    except Exception as e:
        logger.warning("initial statistics refresh failed: %s", e)

    task = asyncio.create_task(_statistics_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
