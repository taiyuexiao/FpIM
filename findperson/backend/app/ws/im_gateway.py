"""IM 实时网关（WebSocket）。

协议：JSON 文本帧（不自造二进制协议）。

客户端 → 服务端
  {"type":"send",  "conversationId":1, "msgType":"text", "content":{"text":"..."},
                   "clientMsgId":"uuid", "issueId":12}
  {"type":"read",  "conversationId":1, "seq":42, "issueId":12}
  {"type":"typing","conversationId":1}
  {"type":"ping"}

服务端 → 客户端
  {"type":"ready",   "userId":"P0004"}
  {"type":"ack",     "clientMsgId":"uuid", "message":{...}}   ← 发送方回执（含服务端 id/seq）
  {"type":"message", "message":{...}}                         ← 其他成员收到的新消息
  {"type":"read",    "conversationId":1, "userId":"P0005", "seq":42}
  {"type":"typing",  "conversationId":1, "userId":"P0005"}
  {"type":"presence","userId":"P0005", "online":true}
  {"type":"pong"}
  {"type":"error",   "detail":"...", "clientMsgId":"uuid"}

连接地址：ws://host/api/v1/ws/im?token=<JWT>
（浏览器 WebSocket 无法自定义 Header，因此 token 走 query —— 部署时用 wss 并确保
  反向代理不把 query 写进访问日志，或改用一次性 ticket 换取。）
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import text

from ..core.database import SessionLocal
from ..core.security import decode_token
from ..services import im as im_service

logger = logging.getLogger("app.im")

router = APIRouter()


class Hub:
    """单实例内存连接表。

    多实例部署时这里要换成 Redis pub/sub 广播（架构上已预留：所有投递都走
    `send_to_user` / `send_to_users` 两个方法，替换实现即可）。
    """

    def __init__(self) -> None:
        self._conns: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()
        self._last_seen: dict = {}   # ws -> monotonic
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """记录主事件循环，供同步业务服务安全广播 Agent 回复。"""
        self._loop = loop

    def send_to_users_sync(self, user_ids: list[str], payload: dict) -> None:
        """同步入口广播；若已在主循环则调度任务，否则跨线程投递。"""
        if not self._loop or self._loop.is_closed():
            return
        coro = self.send_to_users(user_ids, payload)
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self._loop:
            self._loop.create_task(coro)
            return
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            future.result(timeout=2)
        except Exception:  # noqa: BLE001 - 广播失败不回滚消息
            logger.warning("群聊 Agent WS 广播失败", exc_info=True)

    def touch(self, ws) -> None:
        """心跳触点：任何收到的帧都刷新该连接活跃时间（04-方案 §3.4）。"""
        self._last_seen[ws] = time.monotonic()

    async def sweep_stale(self, idle_seconds: float = 75.0) -> int:
        """关闭超过 idle_seconds 无任何帧的连接（半开连接治理）。按连接对象精确清理。"""
        now = time.monotonic()
        dead = [ws for ws, last in list(self._last_seen.items()) if now - last > idle_seconds]
        for ws in dead:
            self._last_seen.pop(ws, None)
            try:
                await ws.close(code=4000)
            except Exception:  # noqa: BLE001
                pass
            for user_id, conns in list(self._conns.items()):
                if ws in conns:
                    conns.discard(ws)
                    if not conns:
                        self._conns.pop(user_id, None)
        return len(dead)

    async def ping_all(self) -> None:
        await self.broadcast_all({"type": "ping"})

    async def broadcast_all(self, frame: dict) -> None:
        payload = json.dumps(frame, ensure_ascii=False)
        for user_id, conns in list(self._conns.items()):
            for ws in list(conns):
                try:
                    await ws.send_text(payload)
                except Exception:  # noqa: BLE001
                    pass

    async def add(self, user_id: str, ws: WebSocket) -> None:
        self._last_seen[ws] = time.monotonic()
        async with self._lock:
            self._conns.setdefault(user_id, set()).add(ws)

    async def remove(self, user_id: str, ws: WebSocket) -> bool:
        """移除连接，返回该用户是否已完全离线。"""
        async with self._lock:
            conns = self._conns.get(user_id)
            if not conns:
                return True
            conns.discard(ws)
            if not conns:
                self._conns.pop(user_id, None)
                return True
            return False

    def online(self, user_id: str) -> bool:
        return bool(self._conns.get(user_id))

    async def send_to_user(self, user_id: str, payload: dict) -> None:
        conns = list(self._conns.get(user_id) or ())
        if not conns:
            return
        text = json.dumps(payload, ensure_ascii=False, default=str)
        dead = []
        for ws in conns:
            try:
                await ws.send_text(text)
            except Exception:  # noqa: BLE001 —— 连接已断，稍后清理
                dead.append(ws)
        for ws in dead:
            await self.remove(user_id, ws)

    async def send_to_users(self, user_ids: list[str], payload: dict) -> None:
        for uid in dict.fromkeys(user_ids):
            await self.send_to_user(uid, payload)


hub = Hub()


def broadcast_message_sync(conv_id: int, message: dict, exclude_user_id: str | None = None) -> None:
    """同步服务写入消息后，把消息推给当前会话的在线成员。"""
    members = _load_member_ids(conv_id)
    if exclude_user_id:
        members = [uid for uid in members if uid != exclude_user_id]
    hub.send_to_users_sync(members, {"type": "message", "message": message})


def _load_member_ids(conv_id: int) -> list[str]:
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                "SELECT user_id FROM im.conversation_members "
                "WHERE conversation_id = :cid AND left_at IS NULL"
            ), {"cid": conv_id}).fetchall()
        return [r[0] for r in rows]
    finally:
        db.close()


def _peer_user_ids(user_id: str) -> list[str]:
    """与该用户有共同会话的所有人（用于在线状态广播）。"""
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT DISTINCT m2.user_id
                  FROM im.conversation_members m1
                  JOIN im.conversation_members m2
                    ON m2.conversation_id = m1.conversation_id AND m2.user_id <> m1.user_id
                 WHERE m1.user_id = :uid AND m1.left_at IS NULL AND m2.left_at IS NULL
                """
            ), {"uid": user_id}).fetchall()
        return [r[0] for r in rows]
    finally:
        db.close()


# ── 各帧处理（全部同步 DB 操作，用 to_thread 下放线程池，避免阻塞事件循环）──

def _handle_send(user_id: str, frame: dict) -> dict:
    conv_id = int(frame.get("conversationId") or 0)
    db = SessionLocal()
    try:
        msg, created = im_service.send_message(
            db,
            conv_id=conv_id,
            sender_id=user_id,
            msg_type=frame.get("msgType") or "text",
            content=frame.get("content") or {},
            client_msg_id=frame.get("clientMsgId"),
            reply_to_id=frame.get("replyToId"),
            issue_id=frame.get("issueId"),
        )
        return {"message": msg, "created": created}
    finally:
        db.close()


def _handle_read(user_id: str, frame: dict) -> dict:
    conv_id = int(frame.get("conversationId") or 0)
    seq = int(frame.get("seq") or 0)
    db = SessionLocal()
    try:
        result = im_service.mark_read(db, conv_id, user_id, seq)
        # 问题级首次已读留痕（只认责任人，唯一索引兜底不可覆盖）
        issue_id = frame.get("issueId")
        if issue_id:
            im_service.record_issue_read(db, int(issue_id), user_id)
        return {"conversationId": conv_id, "seq": seq, "result": result}
    finally:
        db.close()


from .. import metrics as _metrics

_metrics.register_gauge("fpim_ws_connections", lambda: sum(len(v) for v in hub._conns.values()))

@router.websocket("/ws/im")
async def im_socket(ws: WebSocket, token: str = Query(default=""), ticket: str = Query(default="")):
    # ── 鉴权（04-方案 §2.3）：优先一次性 ticket；?token= 兼容一个版本期后移除 ──
    from . import tickets as _tickets

    user_id = _tickets.consume(ticket) if ticket else None
    if not user_id and token:
        try:
            payload = decode_token(token)
            user_id = payload.get("sub")
        except Exception:  # noqa: BLE001
            user_id = None
    if not user_id:
        await ws.close(code=4401)
        return

    await ws.accept()
    await hub.add(user_id, ws)
    logger.info("IM 上线: %s", user_id)

    # 通知有共同会话的人：我上线了
    asyncio.create_task(hub.send_to_users(
        _peer_user_ids(user_id), {"type": "presence", "userId": user_id, "online": True}))

    try:
        await ws.send_text(json.dumps({"type": "ready", "userId": user_id}, ensure_ascii=False))

        while True:
            raw = await ws.receive_text()
            hub.touch(ws)   # 04-方案 §3.4：任何帧刷新活跃（pong 亦然）
            try:
                frame = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_text(json.dumps(
                    {"type": "error", "detail": "非法 JSON 帧"}, ensure_ascii=False))
                continue

            ftype = frame.get("type")

            if ftype == "ping":
                await ws.send_text('{"type":"pong"}')
                continue

            if ftype == "send":
                try:
                    data = await asyncio.to_thread(_handle_send, user_id, frame)
                except PermissionError as exc:
                    await ws.send_text(json.dumps(
                        {"type": "error", "detail": str(exc),
                         "clientMsgId": frame.get("clientMsgId")}, ensure_ascii=False))
                    continue
                except Exception as exc:  # noqa: BLE001
                    logger.exception("IM 发消息失败")
                    await ws.send_text(json.dumps(
                        {"type": "error", "detail": f"发送失败: {exc}",
                         "clientMsgId": frame.get("clientMsgId")}, ensure_ascii=False))
                    continue

                msg = data["message"]
                # 回执给自己（带 clientMsgId，客户端据此把"发送中"置为"已发送"）
                await ws.send_text(json.dumps(
                    {"type": "ack", "clientMsgId": frame.get("clientMsgId"),
                     "message": msg}, ensure_ascii=False, default=str))
                # 广播给会话其他成员
                members = await asyncio.to_thread(_load_member_ids, msg["conversationId"])
                await hub.send_to_users(
                    [m for m in members if m != user_id],
                    {"type": "message", "message": msg})
                continue

            if ftype == "read":
                try:
                    data = await asyncio.to_thread(_handle_read, user_id, frame)
                except Exception:  # noqa: BLE001
                    logger.exception("IM 已读失败")
                    continue
                members = await asyncio.to_thread(_load_member_ids, data["conversationId"])
                await hub.send_to_users(
                    [m for m in members if m != user_id],
                    {"type": "read", "conversationId": data["conversationId"],
                     "userId": user_id, "seq": data["seq"], "result": data["result"]})
                continue

            if ftype == "typing":
                conv_id = int(frame.get("conversationId") or 0)
                members = await asyncio.to_thread(_load_member_ids, conv_id)
                await hub.send_to_users(
                    [m for m in members if m != user_id],
                    {"type": "typing", "conversationId": conv_id, "userId": user_id})
                continue

            if ftype in ("ping", "pong"):
                continue   # 客户端心跳帧：touch 已在收帧处完成
            await ws.send_text(json.dumps(
                {"type": "error", "detail": f"未知帧类型: {ftype}"}, ensure_ascii=False))

    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.exception("IM 连接异常")
    finally:
        fully_offline = await hub.remove(user_id, ws)
        logger.info("IM 下线: %s (完全离线=%s)", user_id, fully_offline)
        if fully_offline:
            asyncio.create_task(hub.send_to_users(
                _peer_user_ids(user_id),
                {"type": "presence", "userId": user_id, "online": False}))
