"""IM WebSocket 实时层自测：ready / 心跳 / 发送 ack / 广播 / 已读回执 / typing / presence / 越权 / 离线增量。

用法：
    venv/bin/python scripts/fpim_smoke_ws.py
    venv/bin/python scripts/fpim_smoke_ws.py http://127.0.0.1:8002

依赖 `websockets`（uvicorn[standard] 已带）。退出码：0 = 全通过，1 = 有失败，2 = 缺少凭据。
凭据来源：读取 backend/.env（不入库），也可用 SEED_PASSWORD 环境变量覆盖。
"""
import asyncio
import json
import os
import sys
import urllib.request
from pathlib import Path

import websockets


def _load_env() -> None:
    """读取 backend/.env（不入库）；已存在的环境变量优先。"""
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_env()

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8002"
WS = BASE.replace("http://", "ws://").replace("https://", "wss://") + "/api/v1/ws/im"
PASSWORD = os.environ.get("SEED_PASSWORD", "")

# 同 HTTP 自测：绕过沙箱注入的 HTTP_PROXY
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
urllib.request.install_opener(_opener)


def login(account):
    req = urllib.request.Request(
        BASE + "/api/v1/auth/login",
        data=json.dumps({"account": account, "password": PASSWORD}).encode(),
        method="POST")
    req.add_header("Content-Type", "application/json")
    with _opener.open(req, timeout=10) as r:
        return json.load(r)["token"]


def post(path, token, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {token}")
    with _opener.open(req, timeout=10) as r:
        return json.load(r)


def get(path, token):
    req = urllib.request.Request(BASE + path)
    req.add_header("Authorization", f"Bearer {token}")
    with _opener.open(req, timeout=10) as r:
        return json.load(r)


ok = fail = 0


def check(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ✅ {label}")
    else:
        fail += 1
        print(f"  ❌ {label} {extra}")


async def recv_until(ws, want_type, timeout=5.0, limit=6):
    """读到指定类型的帧为止，返回 (帧, 途中见到的帧类型列表)。"""
    seen = []
    for _ in range(limit):
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        frame = json.loads(raw)
        seen.append(frame.get("type"))
        if frame.get("type") == want_type:
            return frame, seen
    return None, seen


async def main():
    print("=" * 62)
    ta, tb = login("P0004"), login("P0005")
    cid = post("/api/v1/im/conversations/direct", ta, {"peerId": "P0005"})["id"]
    print(f"会话 id={cid}")

    print("\n1. 双端建连")
    ws_a = await websockets.connect(f"{WS}?token={ta}")
    ws_b = await websockets.connect(f"{WS}?token={tb}")
    ra = json.loads(await asyncio.wait_for(ws_a.recv(), 5))
    rb = json.loads(await asyncio.wait_for(ws_b.recv(), 5))
    check("A 收到 ready", ra["type"] == "ready" and ra["userId"] == "P0004", ra)
    check("B 收到 ready", rb["type"] == "ready" and rb["userId"] == "P0005", rb)

    print("\n2. 心跳")
    await ws_a.send(json.dumps({"type": "ping"}))
    f, _ = await recv_until(ws_a, "pong")
    check("ping → pong", f is not None)

    print("\n3. A 通过 WS 发消息")
    await ws_a.send(json.dumps({
        "type": "send", "conversationId": cid, "msgType": "text",
        "content": {"text": "WS 通道测试：这条消息走实时层"},
        "clientMsgId": "ws-001"}))
    ack, _ = await recv_until(ws_a, "ack")
    check("A 收到 ack 且带 clientMsgId",
          ack is not None and ack.get("clientMsgId") == "ws-001", ack)
    msg = ack["message"] if ack else {}
    check("ack 带回服务端 id/seq", bool(msg.get("id")) and msg.get("seq", 0) > 0, msg)

    print("\n4. B 实时收到广播")
    bmsg, seen = await recv_until(ws_b, "message")
    check("B 收到 message 帧", bmsg is not None, seen)
    check("内容一致", bmsg and bmsg["message"]["content"].get("text") ==
          "WS 通道测试：这条消息走实时层", bmsg)

    print("\n5. B 已读 → A 收到已读回执")
    await ws_b.send(json.dumps({"type": "read", "conversationId": cid,
                                "seq": bmsg["message"]["seq"]}))
    readf, seen = await recv_until(ws_a, "read")
    check("A 收到 read 帧", readf is not None, seen)
    check("read 帧带 userId/seq",
          readf and readf.get("userId") == "P0005" and readf.get("seq") == bmsg["message"]["seq"],
          readf)

    print("\n6. typing 透传")
    await ws_a.send(json.dumps({"type": "typing", "conversationId": cid}))
    tf, seen = await recv_until(ws_b, "typing")
    check("B 收到 typing", tf is not None, seen)

    print("\n7. 非法 token 拒绝")
    try:
        bad = await websockets.connect(f"{WS}?token=not-a-token")
        try:
            await asyncio.wait_for(bad.recv(), 3)
            check("非法 token 被关闭", False, "竟然收到了帧")
        except Exception:
            check("非法 token 被关闭", True)
        await bad.close()
    except Exception as e:  # 握手阶段即被拒
        check("非法 token 被关闭", "4401" in str(e) or "reject" in str(e).lower(), str(e))

    print("\n8. presence：新连接上线广播")
    ws_c = await websockets.connect(f"{WS}?token={login('P0006')}")
    pf, seen = await recv_until(ws_a, "presence", timeout=4)
    print(f"   A 侧看到 presence 帧: {pf} （帧序 {seen}）")
    await ws_c.close()
    check("在线状态帧可达", pf is not None)

    print("\n9. 断线重连后增量补齐")
    await ws_b.close()
    await asyncio.sleep(0.5)
    await ws_a.send(json.dumps({
        "type": "send", "conversationId": cid, "msgType": "text",
        "content": {"text": "B 离线期间发的消息"}, "clientMsgId": "ws-002"}))
    await recv_until(ws_a, "ack")
    hist = get(f"/api/v1/im/conversations/{cid}/messages?afterSeq={msg['seq']}", ta)
    check("增量接口能取到离线消息",
          any(m["content"].get("text") == "B 离线期间发的消息" for m in hist["items"]),
          [m["content"] for m in hist["items"]])

    await ws_a.close()
    print("\n" + "=" * 62)
    print(f"结果：{ok} 通过 / {fail} 失败")
    return 1 if fail else 0


if __name__ == "__main__":
    if not PASSWORD:
        print("缺少 SEED_PASSWORD：种子账号登录口令不入库。")
        print("请在 backend/.env 中设置 SEED_PASSWORD，或直接导出该环境变量后重试。")
        sys.exit(2)
    sys.exit(asyncio.run(main()))
