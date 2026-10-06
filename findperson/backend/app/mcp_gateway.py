"""MCP 工具网关（二期半「腿二」）：Model Context Protocol 客户端。

接入任意 MCP server（stdio 传输），把其工具注册为 Agent 可调用工具
（命名 `mcp__<server>__<tool>`）。配置方式（.env）：

  MCP_SERVERS={"filesystem": {"command": "npx", "args": ["-y",
      "@modelcontextprotocol/server-filesystem", "/data/fpim/files"]}}

未配置或 `mcp` 包缺失时优雅降级（Agent 只带内置工具）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

_servers_cfg: dict = {}
_sessions: dict = {}          # name -> {"session": ..., "cm": ...}
_specs: list[dict] = []       # OpenAI tools 规格（缓存）
_specs_loaded = False
_pool: ThreadPoolExecutor | None = None


def configure(servers_json: str) -> None:
    global _servers_cfg
    try:
        _servers_cfg = json.loads(servers_json or "{}")
    except json.JSONDecodeError:
        _servers_cfg = {}


def _get_pool() -> ThreadPoolExecutor:
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mcp")
    return _pool


async def _boot_async():
    """启动时连接各 MCP server 并拉取工具清单。"""
    global _specs, _specs_loaded
    if not _servers_cfg:
        _specs_loaded = True
        return
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError:
        logger.warning("mcp 包未安装，跳过 MCP 工具（pip install mcp）")
        _specs_loaded = True
        return

    for name, cfg in _servers_cfg.items():
        try:
            params = StdioServerParameters(command=cfg.get("command", ""),
                                           args=cfg.get("args", []))
            cm = stdio_client(params)
            read, write = await cm.__aenter__()
            session = ClientSession(read, write)
            await session.__aenter__()
            await session.initialize()
            tools = await session.list_tools()
            _sessions[name] = {"session": session, "cm": cm}
            for t in tools.tools:
                _specs.append({"type": "function", "function": {
                    "name": f"mcp__{name}__{t.name}",
                    "description": f"[MCP:{name}] {t.description or t.name}",
                    "parameters": t.inputSchema or {"type": "object", "properties": {}},
                }})
            logger.info("MCP server %s 接入：%d 个工具", name, len(tools.tools))
        except Exception:  # noqa: BLE001
            logger.exception("MCP server %s 接入失败", name)
    _specs_loaded = True


def ensure_ready() -> None:
    """同步幂等启动（build_brain 调用前）。"""
    global _specs_loaded
    if _specs_loaded:
        return
    try:
        fut = asyncio.run_coroutine_threadsafe(_boot_async(), _get_loop())
        fut.result(timeout=20)
    except Exception:  # noqa: BLE001
        logger.exception("MCP 初始化失败（继续仅用内置工具）")
        _specs_loaded = True


_loop = None
_loop_thread = None


def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop, _loop_thread
    if _loop is None:
        _loop = asyncio.new_event_loop()

        def _run():
            _loop.run_forever()

        _loop_thread = threading.Thread(target=_run, daemon=True, name="mcp-loop")
        _loop_thread.start()
    return _loop


def get_specs() -> list[dict]:
    ensure_ready()
    return list(_specs)


def call_tool(full_name: str, arguments: dict, timeout: float = 45.0) -> dict:
    """调用 MCP 工具（同步）。full_name = mcp__<server>__<tool>。"""
    ensure_ready()
    try:
        _, name, tool = full_name.split("__", 2)
        entry = _sessions.get(name)
        if not entry:
            return {"ok": False, "error": f"MCP server {name} 未接入"}

        async def _call():
            result = await entry["session"].call_tool(tool, arguments)
            texts = [c.text for c in (result.content or []) if getattr(c, "text", None)]
            return {"ok": not result.isError, "content": "\\n".join(texts)[:4000]}

        fut = asyncio.run_coroutine_threadsafe(_call(), _get_loop())
        return fut.result(timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
