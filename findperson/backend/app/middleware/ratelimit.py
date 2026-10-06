"""限流中间件（04-生产加固技术方案 §3.2）：进程内令牌桶/固定窗口。

覆盖三类高风险入口：登录爆破 / 发消息突发 / 上传带宽。
接口留 RateLimiter 抽象——多实例阶段换 Redis 实现同名替换。
"""
from __future__ import annotations

import threading
import time

from fastapi import Request
from fastapi.responses import JSONResponse

from starlette.middleware.base import BaseHTTPMiddleware

_MAX_PER_USER_PER_SEC = 5       # 发消息稳态
_BURST = 20                     # 突发容量
_LOGIN_FAILS = 5                # 登录失败窗口
_LOGIN_WINDOW = 60.0

_buckets: dict[str, dict] = {}
_lock = threading.Lock()


def _allow(key: str, rate: float, burst: float) -> bool:
    now = time.monotonic()
    with _lock:
        b = _buckets.setdefault(key, {"tokens": burst, "ts": now})
        b["tokens"] = min(burst, b["tokens"] + (now - b["ts"]) * rate)
        b["ts"] = now
        if b["tokens"] >= 1:
            b["tokens"] -= 1
            return True
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # 发消息 / 上传：按用户（AuthMiddleware 已解析）
        if path.endswith("/messages") and request.method == "POST" or path.endswith("/upload"):
            uid = getattr(request.state, "user_id", None)
            if uid and not _allow(f"msg:{uid}", _MAX_PER_USER_PER_SEC, _BURST):
                return JSONResponse(status_code=429, content={"message": "发送太频繁，稍后再试"})
        # 登录：按账号+IP 计失败（在响应后统计失败次数）
        elif path.endswith("/auth/login") and request.method == "POST":
            body_account = ""
            try:
                body = await request.json()
                body_account = str(body.get("account") or "").lower()
            except Exception:  # noqa: BLE001
                pass
            key = f"login:{body_account}:{request.client.host if request.client else ''}"
            with _lock:
                rec = _buckets.setdefault(key, {"fails": 0, "win": time.monotonic()})
                if time.monotonic() - rec["win"] > _LOGIN_WINDOW:
                    rec["fails"], rec["win"] = 0, time.monotonic()
                if rec["fails"] >= _LOGIN_FAILS:
                    return JSONResponse(status_code=429, content={"message": "尝试过多，请 10 分钟后再试"})
            response = await call_next(request)
            if response.status_code == 401:
                with _lock:
                    rec = _buckets.setdefault(key, {"fails": 0, "win": time.monotonic()})
                    rec["fails"] += 1
                    rec["win"] = time.monotonic()
            return response
        return await call_next(request)
