"""Agent 桥异步化（04-生产加固技术方案 §2.2）。

问题：handle_im_message 里的 DeepSeek 调用最长 30s，同步挂在
send_message 末尾会拖慢发送主链。
方案：send_message 只做 enqueue（永不阻塞）；常驻 worker 线程池消费，
处理完经既有 hub 广播。enqueue() 是唯一耦合点——多实例阶段把本模块
换成 Redis Stream 消费者，业务代码零改动。
"""
from __future__ import annotations

import logging
import queue
import threading
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

_queue: "queue.Queue[dict]" = queue.Queue(maxsize=2000)
_pool: ThreadPoolExecutor | None = None
_started = False
_lock = threading.Lock()


def enqueue(message: dict) -> None:
    """把落库后的消息投给 Agent 桥（非阻塞；队列满丢弃并告警——Agent 不值得阻塞发送）。"""
    try:
        _queue.put_nowait(message)
    except queue.Full:
        logger.warning("Agent 桥队列已满（2000），丢弃消息桥接 conversation=%s", message.get("conversationId"))


def _worker() -> None:
    from .core.database import SessionLocal
    from .group_agent.integration import handle_im_message

    import time as _t
    from . import metrics

    while True:
        message = _queue.get()
        t0 = _t.time()
        db = SessionLocal()
        status = "ok"
        try:
            handle_im_message(db, message)
            db.commit()
        except Exception:  # noqa: BLE001 - Agent 任何异常不得外溢
            status = "error"
            logger.exception("Agent 桥异步处理失败 conversation=%s", message.get("conversationId"))
            db.rollback()
        except Exception:  # noqa: BLE001 - Agent 任何异常不得外溢
            logger.exception("Agent 桥异步处理失败 conversation=%s", message.get("conversationId"))
            db.rollback()
        finally:
            metrics.incr("fpim_agent_calls_total", {"status": status})
            metrics.observe("fpim_agent_latency_seconds", _t.time() - t0)
            db.close()
            _queue.task_done()


def start_workers(count: int = 2) -> None:
    global _pool, _started
    with _lock:
        if _started:
            return
        _pool = ThreadPoolExecutor(max_workers=count, thread_name_prefix="agent-bridge")
        for _ in range(count):
            _pool.submit(_worker)
        _started = True
        logger.info("Agent 桥 worker 已启动 x%d", count)


def drain(timeout: float = 10.0) -> None:
    """优雅停机：等队列排空。"""
    try:
        _queue.join(timeout=timeout) if hasattr(_queue, "join") else None
    except Exception:  # noqa: BLE001
        pass
