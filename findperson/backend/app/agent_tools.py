"""Agent 工具网关（二期 R3）：受控工具调用。

切片 1 工具：
  file.search  找文件 —— 本地伴随程序优先（用户电脑），回退平台文件库（会话附件）
  file.send    发文件 —— 作为 file 消息进入会话（"已发送"以消息回执为准，附件 §7.2 红线）
指令入口：`match_file_command()` 解析"把名为 xxx 的文件发给对方/发到本会话"。
写动作红线：发送本身是业务写入，但"发文件给当前对话"是明确指令，直接执行并回凭据；
跨会话/公开范围/歧义未解时停下来问（附件 §7.3）。
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_FILE_CMD = re.compile(
    r"(?:把|将)\s*(?:名为|叫做|叫)?\s*[\"'「『]?(?P<name>[^\"'」』，,。.]{1,60}?)[\"'」』]?\s*"
    r"(?:的)?\s*(?:文件|文档)\s*(?:发送?|传)?\s*(?:给|到)\s*(?P<target>对方|他|她|本会话|当前会话|群里)?")


def match_file_command(text_body: str) -> dict | None:
    """识别「发文件」意图；识别不了返回 None（走普通对话）。"""
    m = _FILE_CMD.search(text_body or "")
    if not m:
        return None
    name = (m.group("name") or "").strip()
    if not name:
        return None
    return {"fileQuery": name, "target": (m.group("target") or "对方")}


def search_files(db: Session, user_id: str, query: str, timeout: float = 10.0) -> list[dict]:
    """file.search：本地伴随优先，回退平台文件库。"""
    # ① 本地伴随（用户授权的电脑目录）
    try:
        from .ws import companion_gateway
        if companion_gateway.is_online(user_id):
            result = companion_gateway.search_local_files(user_id, query, timeout=timeout)
            files = result.get("files") or []
            return [{**f, "source": "local"} for f in files][:5]
    except Exception:  # noqa: BLE001
        logger.exception("本地文件搜索失败，回退平台文件库")

    # ② 平台文件库：会话文件消息（我参与的会话中出现过的文件）
    rows = db.execute(sql_text(
        """
        SELECT DISTINCT m.content->>'name', m.content->>'url', m.content->>'size',
               m.conversation_id, m.id
          FROM im.messages m
          JOIN im.conversation_members cm
            ON cm.conversation_id = m.conversation_id AND cm.user_id = :uid AND cm.left_at IS NULL
         WHERE m.msg_type IN ('file', 'image') AND m.revoked = false
           AND COALESCE(m.content->>'name', '') ILIKE :kw
         ORDER BY m.id DESC LIMIT 5
        """
    ), {"uid": user_id, "kw": f"%{query}%"}).fetchall()
    return [{
        "name": r[0], "url": r[1], "size": r[2],
        "conversationId": r[3], "messageId": r[4], "source": "platform",
    } for r in rows]


def send_file(db: Session, user_id: str, conversation_id: int, candidate: dict,
              timeout: float = 60.0) -> dict:
    """file.send：把候选文件作为 file 消息发进会话；返回消息凭据。"""
    from .services import im as im_service

    if candidate.get("source") == "local":
        # 本地文件：先让 companion 上传到平台文件库，再发消息
        from .ws import companion_gateway
        uploaded = companion_gateway.request_local_upload(user_id, candidate["path"], timeout=timeout)
        if not uploaded.get("ok"):
            raise RuntimeError("本地文件上传失败")
        content = {
            "url": uploaded["url"], "name": uploaded.get("name") or candidate.get("name"),
            "size": uploaded.get("size"), "mime": uploaded.get("mime"),
            "sha256": uploaded.get("sha256"),
        }
    else:
        content = {
            "url": candidate.get("url"), "name": candidate.get("name"),
            "size": candidate.get("size"), "mime": "",
        }
    msg, _ = im_service.send_message(
        db, conversation_id, user_id, "file", content,
        client_msg_id=f"tool-file:{candidate.get('name')}:{conversation_id}")
    from .ws.im_gateway import broadcast_message_sync
    broadcast_message_sync(conversation_id, msg)
    return {"message": msg, "credential": {"messageId": msg.get("id"), "seq": msg.get("seq")}}


def run_file_command(db: Session, user_id: str, conversation_id: int,
                     text_body: str) -> str | None:
    """执行发文件指令；返回给用户的结果文本（含凭据），识别不了返回 None。"""
    cmd = match_file_command(text_body)
    if not cmd:
        return None
    candidates = search_files(db, user_id, cmd["fileQuery"])
    if not candidates:
        return f"我在授权范围里没找到名为「{cmd['fileQuery']}」的文件。已查：平台会话文件" + (
            "、你的本地目录" if True else "") + "。请确认文件名或扩大授权范围。"
    if len(candidates) > 1 and candidates[0].get("source") == "local":
        # 同名多版本 → 消歧，不猜（附件 §7.2）
        names = "、".join(f"{c.get('name')}（{c.get('path', '')}）" for c in candidates[:3])
        return f"找到多个候选：{names}。请告诉我用哪一个（回复完整路径或更精确的文件名）。"
    candidate = candidates[0]
    try:
        result = send_file(db, user_id, conversation_id, candidate)
    except Exception as exc:  # noqa: BLE001
        return f"发送失败：{exc}"
    cred = result["credential"]
    return (f"已把「{candidate.get('name')}」发到当前会话"
            f"（消息 id={cred['messageId']}，seq={cred['seq']}，发送凭据以此为准）。")


# ── DeepSeek 函数调用（function calling）支持 ─────────────────────────

def get_tool_specs() -> list[dict]:
    """OpenAI 兼容 tools 参数：让模型自主决定何时调工具。"""
    tools = [
        {"type": "function", "function": {
            "name": "file_search",
            "description": "在授权范围内搜索文件（用户本地目录优先，回退平台会话文件）。用户提到找/发送文件时先用它。",
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string", "description": "文件名关键词，如「场景」或「报销手册」"},
            }, "required": ["query"]},
        }},
        {"type": "function", "function": {
            "name": "fs_list",
            "description": "列出用户电脑上的目录内容（本地伴随节点执行）。找文件、看目录结构用。",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string", "description": "目录路径，如 ~/Documents 或桌面路径"},
            }, "required": ["path"]},
        }},
        {"type": "function", "function": {
            "name": "fs_read",
            "description": "读取用户电脑上的文本文件内容（本地伴随节点执行）。",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string", "description": "文件路径"},
            }, "required": ["path"]},
        }},
        {"type": "function", "function": {
            "name": "fs_write",
            "description": "写入用户电脑上的文件（本地伴随节点执行）。覆盖已有文件需要用户确认。",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "文件内容"},
                "confirmed": {"type": "boolean", "description": "用户已确认危险操作时为 true（收到 needConfirm 后，用户回复确认时置 true 重试）"},
            }, "required": ["path", "content"]},
        }},
        {"type": "function", "function": {
            "name": "shell_exec",
            "description": "在用户电脑上执行命令（本地伴随节点执行，默认 cwd=授权目录）。危险命令（rm -rf/drop table 等）会被拦截要求确认：返回 needConfirm 时，如实告知用户风险并等其回复「确认执行」，之后带 confirmed=true 重试。",
            "parameters": {"type": "object", "properties": {
                "command": {"type": "string", "description": "要执行的命令行"},
                "confirmed": {"type": "boolean", "description": "用户已确认危险操作时为 true"},
            }, "required": ["command"]},
        }},
        {"type": "function", "function": {
            "name": "file_send",
            "description": "把找到的文件发送到当前会话。file_search 结果唯一时可直接发送；多个候选时先向用户确认。",
            "parameters": {"type": "object", "properties": {
                "name": {"type": "string", "description": "要发送的文件名（file_search 返回的 name）"},
            }, "required": ["name"]},
        }},
    ]
    # MCP 工具（腿二）：接入的 MCP server 工具自动并入
    try:
        from .mcp_gateway import get_specs as mcp_specs
        tools.extend(mcp_specs())
    except Exception:  # noqa: BLE001
        pass
    return tools


def _emit_step(event, text: str) -> None:
    """过程小灰条：Agent 干活的每一步实时可见（zcode 式执行日志，IM 内为居中小灰条）。"""
    if not getattr(event, "conversation_id", None):
        return
    from .core.database import SessionLocal

    db = SessionLocal()
    try:
        from .services import im as im_service
        from .ws.im_gateway import broadcast_message_sync

        msg, _ = im_service.send_message(
            db, int(event.conversation_id), "group-agent",
            "system", {"text": text},
            f"step:{uuid.uuid4().hex[:8]}")
        broadcast_message_sync(int(event.conversation_id), msg)
    except Exception:  # noqa: BLE001 - 过程汇报失败不影响执行
        pass
    finally:
        db.close()


def make_tool_executor():
    """返回 (tool_name, args, event) -> result dict 的执行器。

    event 携带 sender_id（工具以谁的身份执行）与 conversation_id（发到哪个会话）。
    每步执行发过程小灰条（Agent 执行日志实时可见）。
    """
    import json as _json
    import uuid
    from .core.database import SessionLocal

    def execute(tool_name: str, args: dict, event) -> dict:
        _emit_step(event, f"🔧 {tool_name}({_json.dumps(args, ensure_ascii=False)[:80]})")
        db = SessionLocal()
        try:
            # MCP 工具（腿二）：mcp__<server>__<tool>
            if tool_name.startswith("mcp__"):
                from .mcp_gateway import call_tool
                return call_tool(tool_name, args)

            # 本地执行节点工具（腿一）：fs/shell/file 统一走 companion
            if tool_name in ("fs_list", "fs_read", "fs_write", "shell_exec"):
                from .ws import companion_gateway
                uid = event.sender_id or ""
                if not companion_gateway.is_online(uid):
                    return {"ok": False,
                            "error": "你的电脑未连接本地执行节点——请在自己电脑上运行 local_companion.py 后重试"}
                local_type = {"fs_list": "fs.list", "fs_read": "fs.read",
                              "fs_write": "fs.write", "shell_exec": "shell.exec"}[tool_name]
                result = companion_gateway.request_tool(
                    uid, local_type, args, confirmed=bool(args.get("confirmed")))
                return result
            uid = event.sender_id or ""
            cid = int(event.conversation_id or 0)
            if tool_name == "file_search":
                files = search_files(db, uid, str(args.get("query", "")))
                return {"ok": True, "count": len(files), "files": files,
                        "hint": "count==1 可直接 file_send(name=该文件名)；多个候选时列出让用户选"}
            if tool_name == "file_send":
                cands = search_files(db, uid, str(args.get("name", "")))
                if not cands:
                    return {"ok": False, "error": "未找到匹配文件"}
                if len(cands) > 1 and cands[0].get("source") == "local":
                    return {"ok": False, "error": "多个同名候选，请让用户确认具体文件",
                            "candidates": [c.get("name") for c in cands[:3]]}
                result = send_file(db, uid, cid, cands[0])
                return {"ok": True, "messageId": result["credential"]["messageId"],
                        "seq": result["credential"]["seq"],
                        "note": "已发送；凭据为消息 id，可告知用户"}
            return {"ok": False, "error": f"未知工具 {tool_name}"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        finally:
            db.close()

    def execute_with_trace(tool_name: str, args: dict, event) -> dict:
        result = execute(tool_name, args, event)
        brief = result.get("error") or f"完成：{_json.dumps({k: v for k, v in result.items() if k in ('ok','count','messageId')}, ensure_ascii=False)}"
        _emit_step(event, f"→ {brief[:80]}")
        return result

    return execute_with_trace
