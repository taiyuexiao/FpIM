#!/usr/bin/env python3
"""本地执行节点（二期半「腿一」）：让 IM Agent 操作你自己的电脑。

设计立场（用户拍板）：**这是你自己的电脑，权限默认全开，不设审批墙**；
唯一风险是 Agent 误删数据——危险操作（删文件/删库/格式化类）做强提示：
不自动执行，回 needConfirm，由你在 IM 里一句「确认执行」闭环。

能力（经云端短时令牌下发）：
  file.search   找文件（授权目录）
  file.upload   把文件上传到平台（发消息用）
  fs.list / fs.read / fs.write   目录/文件读写
  shell.exec    执行命令（危险命令需确认）

用法：
  pip install websockets requests
  python local_companion.py --root ~ --backend http://<服务器>:8080 --token <JWT>
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import subprocess
import time
from pathlib import Path

try:
    import websockets
    import requests
except ImportError:
    print("请先安装依赖：pip install websockets requests")
    raise SystemExit(1)

# 危险操作识别（做强提示而非拦死——用户确认后执行）
DANGEROUS_PATTERNS = (
    "rm -rf", "rm -fr", "rm -r", " rmdir", "del /", "rd /s", "format ",
    "mkfs", "dd if=", "> /dev/sd", "shutdown", "reboot", "poweroff",
    "drop table", "drop database", "truncate table", "chmod -r 777",
    "kill -9 1", ":(){", "move /y", "del *.",
)
SHELL_TIMEOUT = 30
OUTPUT_CAP = 4000


def _dangerous(cmd: str) -> str | None:
    low = f" {cmd.lower()} "
    for pat in DANGEROUS_PATTERNS:
        if pat in low:
            return pat.strip()
    return None


def search(root: Path, query: str, limit: int = 5) -> list[dict]:
    hits = []
    q = query.lower()
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        try:
            if not p.resolve().is_relative_to(root.resolve()):
                continue
        except (OSError, ValueError):
            continue
        if q in p.name.lower():
            st = p.stat()
            hits.append({"name": p.name, "path": str(p), "size": st.st_size,
                         "mtime": int(st.st_mtime)})
            if len(hits) >= limit:
                break
    return hits


def handle_fs_list(root: Path, args: dict) -> dict:
    path = Path(args.get("path") or ".").expanduser()
    if not path.is_absolute():
        path = root / path
    try:
        resolved = path.resolve()
        # 文件系统工具：默认限制在授权目录内（settings 面可放宽）；仍大权限读
        entries = []
        for child in sorted(resolved.iterdir())[:100]:
            entries.append({"name": child.name, "dir": child.is_dir(),
                            "size": child.stat().st_size if child.is_file() else None})
        return {"ok": True, "entries": entries}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _resolve(root: Path, raw: str) -> Path:
    path = Path(raw or "").expanduser()
    return path if path.is_absolute() else (root / path)


def handle_fs_read(root: Path, args: dict) -> dict:
    try:
        resolved = _resolve(root, str(args.get("path") or "")).resolve()
        if not resolved.is_file():
            return {"ok": False, "error": "文件不存在"}
        text = resolved.read_text(encoding="utf-8", errors="replace")[:20000]
        return {"ok": True, "content": text}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def handle_fs_write(root: Path, args: dict, confirmed: bool) -> dict:
    content = str(args.get("content") or "")
    try:
        resolved = _resolve(root, str(args.get("path") or "")).resolve()
        exists = resolved.exists()
        if exists and not confirmed:
            return {"ok": False, "needConfirm": True,
                    "risk": f"将覆盖已有文件 {resolved.name}"}
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return {"ok": True, "path": str(resolved), "bytes": len(content.encode())}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def handle_shell_exec(root: Path, args: dict, confirmed: bool) -> dict:
    cmd = str(args.get("command") or "").strip()
    if not cmd:
        return {"ok": False, "error": "空命令"}
    danger = _dangerous(cmd)
    if danger and not confirmed:
        return {"ok": False, "needConfirm": True,
                "risk": f"命令含高危操作「{danger}」，可能删除数据"}
    try:
        proc = subprocess.run(cmd, shell=True, cwd=str(root),
                              capture_output=True, text=True,
                              timeout=SHELL_TIMEOUT)
        out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        return {"ok": proc.returncode == 0, "exitCode": proc.returncode,
                "output": out[-OUTPUT_CAP:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"命令超时（>{SHELL_TIMEOUT}s）"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


async def run(root: Path, backend: str, token: str) -> None:
    base = backend.rstrip("/").replace("https://", "wss://").replace("http://", "ws://")
    ws_url = f"{base}/api/v1/ws/companion?token={token}"
    async with websockets.connect(ws_url, max_size=100 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"type": "hello", "deviceName": socket.gethostname()}))
        print(f"[companion] 已连接 {backend} | 授权目录：{root}")
        print("[companion] 能力：file.search/upload · fs.list/read/write · shell.exec")
        print("[companion] 权限：默认执行；危险操作回 needConfirm，由你在 IM 确认")
        async for raw in ws:
            frame = json.loads(raw)
            ftype = frame.get("type")
            req_id = frame.get("reqId")
            exp = frame.get("exp")
            if exp and time.time() > float(exp):
                continue
            print(f"[companion] 收到指令: {ftype} req={req_id}", flush=True)
            confirmed = bool(frame.get("confirmed") or frame.get("args", {}).get("confirmed"))
            args = frame.get("args") or frame   # 兼容旧协议（file.search 平铺字段）
            result: dict
            if ftype == "file.search":
                result = {"files": search(root, str(args.get("query") or ""))}
            elif ftype == "file.upload":
                path = Path(str(args.get("path") or "")).expanduser()
                ok, meta = False, {}
                try:
                    resolved = path.resolve()
                    if resolved.is_file():
                        with open(resolved, "rb") as f:
                            r = requests.post(backend.rstrip("/") + "/api/v1/im/upload",
                                              headers={"Authorization": f"Bearer {token}"},
                                              files={"file": (resolved.name, f)}, timeout=120)
                        if r.ok:
                            meta = r.json()
                            ok = True
                except Exception:  # noqa: BLE001
                    pass
                result = {"ok": ok, **{k: meta.get(k) for k in
                          ("url", "name", "size", "mime", "sha256")}}
            elif ftype == "fs.list":
                result = handle_fs_list(root, args)
            elif ftype == "fs.read":
                result = handle_fs_read(root, args)
            elif ftype == "fs.write":
                result = handle_fs_write(root, args, confirmed)
            elif ftype == "shell.exec":
                result = handle_shell_exec(root, args, confirmed)
                if result.get("needConfirm"):
                    print(f"[companion] ⚠️ 待确认：{args.get('command')}")
            else:
                result = {"ok": False, "error": f"未知指令 {ftype}"}
            await ws.send(json.dumps({"type": "tool.result", "reqId": req_id, **result},
                                     ensure_ascii=False))
            print(f"[companion] 已回包: {ftype} req={req_id} ok={result.get('ok')}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="FpIM 本地执行节点")
    ap.add_argument("--root", required=True, help="工作目录（默认文件操作与命令 cwd）")
    ap.add_argument("--backend", required=True, help="后端地址，如 http://150.158.164.254:8080")
    ap.add_argument("--token", required=True, help="登录 JWT")
    args = ap.parse_args()
    root = Path(args.root).expanduser()
    if not root.is_dir():
        print(f"目录不存在：{root}")
        raise SystemExit(1)
    asyncio.run(run(root, args.backend, args.token))


if __name__ == "__main__":
    main()
