"""会话记忆(多轮对话上下文)。

从 agent.agui_messages 读取同一会话的最近 N 轮消息,注入 AgentState.request.history,
供 IntentNode / QueryStructurerNode 等节点的 LLM prompt 使用,支撑追问、指代消解。

结构化短期记忆(验收:省略式追问的意图继承):
- 每轮结束后用运行产物直接组装 round 摘要(意图/动作/槽位/状态),零额外 LLM 调用;
- 存入 agent_sessions.state.memory(JSONB),最多保留 6 轮;
- 下一轮以"记忆"角色注入 prompt,LLM 读到的是精确槽位状态而非原始对话。

约束:
- 记忆只读不回写(消息落库仍由 AguiService 负责);
- 读取失败不阻断主链(降级为空历史);
- 注入 prompt 时截断,防止上下文膨胀。
"""
from __future__ import annotations

import json

from app.core import db

# 注入 LLM 的历史轮次上限(一轮 = user + assistant 两条)
MAX_HISTORY_TURNS = 6
# 单条历史文本注入 prompt 时的截断长度
MAX_HISTORY_TEXT = 120
# 结构化记忆保留轮次
MAX_MEMORY_ROUNDS = 6


async def load_history(session_id: str | None, *, max_turns: int = MAX_HISTORY_TURNS) -> list[dict]:
    """读取会话最近 N 轮历史,按时间正序返回 [{role, text}]。

    本轮用户消息在回答生成后才落库,因此查询到的均为历史消息,天然排除本轮。
    """
    if not session_id:
        return []
    try:
        rows = await db.fetch(
            "SELECT role, text FROM agent.agui_messages"
            " WHERE session_id=$1 ORDER BY id DESC LIMIT $2",
            session_id, max_turns * 2,
        )
    except Exception:  # noqa: BLE001 —— 记忆读取失败不阻断问答
        return []
    return [{"role": r["role"], "text": r["text"]} for r in reversed(rows)]


def format_history(history: list[dict], *, max_chars: int = MAX_HISTORY_TEXT) -> str:
    """格式化为 prompt 用的纯文本块;无历史返回空串。"""
    if not history:
        return ""
    lines = []
    for m in history:
        role = {"user": "用户", "assistant": "助手", "memory": "记忆"}.get(m.get("role"), "助手")
        text = " ".join(str(m.get("text") or "").split())[:max_chars]
        if text:
            lines.append(f"{role}: {text}")
    return "\n".join(lines)


# ---------------------------------------------------------------- 结构化短期记忆

async def load_memory_lines(session_id: str | None) -> list[str]:
    """读取结构化记忆并格式化为单行摘要列表(注入 prompt 用)。"""
    if not session_id:
        return []
    try:
        row = await db.fetchrow(
            "SELECT state FROM agent.agent_sessions WHERE session_id=$1", session_id)
        if not row:
            return []
        state = row["state"]
        if isinstance(state, str):
            state = json.loads(state)
        memory = (state or {}).get("memory") or []
        lines = []
        for i, rec in enumerate(memory[-MAX_MEMORY_ROUNDS:], 1):
            parts = [f"第{i}轮意图={rec.get('intent', '?')}"]
            if rec.get("action"):
                parts.append(f"写操作={rec['action']}")
            if rec.get("slots"):
                parts.append(f"槽位:{rec['slots']}")
            if rec.get("status"):
                parts.append(str(rec["status"]))
            parts.append(f"用户说:{rec.get('q', '')}")
            lines.append(" ".join(parts))
        return lines
    except Exception:  # noqa: BLE001
        return []


async def append_memory_round(session_id: str | None, record: dict) -> None:
    """把本轮结构化摘要追加进会话状态(state.memory),最多保留 6 轮。失败不阻断。"""
    if not session_id:
        return
    try:
        row = await db.fetchrow(
            "SELECT state FROM agent.agent_sessions WHERE session_id=$1", session_id)
        if not row:
            return
        state = row["state"]
        if isinstance(state, str):
            state = json.loads(state)
        state = state or {}
        memory = list(state.get("memory") or [])
        memory.append(record)
        state["memory"] = memory[-MAX_MEMORY_ROUNDS:]
        await db.execute(
            "UPDATE agent.agent_sessions SET state=$2 WHERE session_id=$1",
            session_id, json.dumps(state, ensure_ascii=False, default=str))
    except Exception:  # noqa: BLE001
        pass
