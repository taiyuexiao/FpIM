"""WS 一次性票据存储（04-方案 §2.3）——签发与校验共用同一张表。

bug 教训（group-agent 同类问题）：ticket 在 api/v1/im.py 签发、在 ws/im_gateway.py
校验，两边各自建了独立 dict → 校验侧永远是空表 → 线上"一直重连中"。
统一收敛到本模块。
"""
from __future__ import annotations

import secrets
import threading
import time

_TTL = 60
_store: dict[str, tuple[str, float]] = {}
_lock = threading.Lock()


def issue(user_id: str) -> tuple[str, int]:
    now = time.time()
    with _lock:
        for t in [k for k, (_, exp) in _store.items() if exp < now]:
            _store.pop(t, None)
        ticket = secrets.token_urlsafe(32)
        _store[ticket] = (user_id, now + _TTL)
    return ticket, _TTL


def consume(ticket: str) -> str | None:
    """一次性：校验通过即作废。返回 user_id 或 None。"""
    with _lock:
        hit = _store.pop(ticket or "", None)
    if hit and hit[1] >= time.time():
        return hit[0]
    return None
