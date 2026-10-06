"""本地伴随程序网关（二期 R3）：用户电脑上的 companion 连上来，Agent 经它搜/取本地文件。

协议（JSON 帧）：
  companion→server: {"type":"hello","deviceName":...}
  server→companion: {"type":"file.search","reqId":N,"query":"xxx"}
  companion→server: {"type":"file.search.result","reqId":N,"files":[{"name","path","size","mtime"}]}
  server→companion: {"type":"file.upload","reqId":N,"path":"..."}
  companion→server: {"type":"file.upload.result","reqId":N,"ok":true,"url","name","size","mime","sha256"}
凭据语义（附件 §7.2）：companion 上传走 REST /im/upload 后回传元数据，真正"已发送"以消息回执为准。
"""
from __future__ import annotations

import asyncio
import time
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..core.security import decode_token

logger = logging.getLogger(__name__)
router = APIRouter()

# owner_id -> {"ws": WebSocket, "deviceName": str, "pending": {reqId: Future}}
_COMPANIONS: dict[str, dict] = {}


def is_online(owner_id: str) -> bool:
    return owner_id in _COMPANIONS


async def _request(owner_id: str, frame: dict, timeout: float = 10.0) -> dict:
    """向在线 companion 发一个请求并等结果；离线或超时抛 TimeoutError。"""
    entry = _COMPANIONS.get(owner_id)
    if not entry:
        raise TimeoutError("companion 离线")
    req_id = str(uuid.uuid4())
    fut: asyncio.Future = asyncio.get_event_loop().create_future()
    entry["pending"][req_id] = fut
    # 短时令牌（04-方案 §3.6）：指令 60s 有效，companion 校验过期即拒
    await entry["ws"].send_json({**frame, "reqId": req_id, "exp": time.time() + 60})
    try:
        return await asyncio.wait_for(fut, timeout=timeout)
    finally:
        entry["pending"].pop(req_id, None)


_main_loop: asyncio.AbstractEventLoop | None = None   # companion_socket accept 时记录


def _run_sync(coro, timeout: float):
    """同步桥：把协程投到 ws 所属主循环执行（uvicorn 循环）。

    ⚠️ 不能自建事件循环执行——ws 对象归 uvicorn 循环所有，跨线程 send/收帧
    都是未定义行为（实测表现为工具回包永久悬挂）。_main_loop 未就绪时
    （companion 从未连接）直接报离线。
    """
    if _main_loop is None:
        raise TimeoutError("companion 离线")
    import concurrent.futures

    fut = asyncio.run_coroutine_threadsafe(coro, _main_loop)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(fut.result, timeout + 5).result()


def search_local_files(owner_id: str, query: str, timeout: float = 10.0) -> dict:
    """同步入口（供同步业务代码调用）：搜本地文件。"""
    return _run_sync(_request(owner_id, {"type": "file.search", "query": query}, timeout), timeout)


def request_tool(owner_id: str, tool_type: str, args: dict,
                 confirmed: bool = False, timeout: float = 45.0) -> dict:
    """同步入口：通用工具执行（fs.list/read/write · shell.exec · file.search/upload）。

    confirmed：用户已确认危险操作（覆盖/删库类命令）——companion 端据此放行。
    """
    frame = {"type": tool_type, "args": args, "confirmed": confirmed}
    import logging
    logging.getLogger(__name__).warning("request_tool 发出: %s loop=%s", tool_type, bool(_main_loop))
    result = _run_sync(_request(owner_id, frame, timeout), timeout)
    logging.getLogger(__name__).warning("request_tool 回包: %s -> %s", tool_type, str(result)[:80])
    return result


def request_local_upload(owner_id: str, path: str, timeout: float = 60.0) -> dict:
    """同步入口：让 companion 把本地文件上传到平台文件库，返回上传元数据。"""
    return _run_sync(_request(owner_id, {"type": "file.upload", "path": path}, timeout), timeout)


@router.websocket("/ws/companion")
async def companion_socket(ws: WebSocket, token: str = ""):
    try:
        payload = decode_token(token)
        owner_id = payload.get("sub")
        if not owner_id:
            await ws.close(code=4401)
            return
    except Exception:  # noqa: BLE001
        await ws.close(code=4401)
        return

    await ws.accept()
    global _main_loop
    _main_loop = asyncio.get_running_loop()   # ws 归属循环；请求必须在其上执行
    entry = {"ws": ws, "deviceName": "", "pending": {}}
    _COMPANIONS[owner_id] = entry
    logger.info("companion 上线 owner=%s", owner_id)
    try:
        while True:
            frame = await ws.receive_json()
            ftype = frame.get("type")
            if ftype == "hello":
                entry["deviceName"] = str(frame.get("deviceName") or "")[:60]
            elif ftype in ("file.search.result", "file.upload.result", "tool.result"):
                fut = entry["pending"].get(str(frame.get("reqId")))
                if fut and not fut.done():
                    fut.set_result(frame)   # 与 _request 同在 uvicorn 主循环，直接回填
    except WebSocketDisconnect:
        pass
    finally:
        _COMPANIONS.pop(owner_id, None)
        logger.info("companion 离线 owner=%s", owner_id)
