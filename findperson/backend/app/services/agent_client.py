"""Agent 对接层：转发 Agent 请求 + Agent 字段 → 表字段映射。

联调时若 Agent 返回字段名变化，只改本文件的映射函数，不动路由。

对接契约（对齐 agent-service 真实接口，见 agent-service/app/api_agent.py）：
- 端点：POST {AGENT_BASE_URL}/agent/chat（SSE 流式）
- 身份：X-User-Id 请求头（agent 经 public.people 校验，非 body user_id）
- 请求体：{"query", "session_id"}

当前「前端直连 agent」（见部署文档），后端此转发路径已停用；本文件保留
以记录真实契约，若将来恢复后端转发，需把 call_agent 改为 SSE 流式透传。
"""
import json
import urllib.error
import urllib.request

from ..core.config import settings


def agent_available() -> bool:
    """Agent 是否已配置（未配置时收口层走降级）"""
    return bool(settings.AGENT_BASE_URL)


def build_agent_payload(question: str, user_id: str, session_id: str, context: dict | None = None) -> dict:
    """构造转发给 Agent 的请求体 + 身份（agent 契约：body {query, session_id}，身份走 X-User-Id 头）。"""
    return {
        "query": question,
        "session_id": session_id,
        "user_id": user_id,  # 由 call_agent 转成 X-User-Id 头
        "context": context or {},
    }


def call_agent(payload: dict, timeout: int = 30) -> dict | None:
    """同步转发 Agent（非流式），返回解析后的 dict；未配置/失败返回 None。

    agent 实际返回 SSE 流，非流式 json.loads 会失败而返回 None（走降级）。
    当前前端已直连 agent，后端此转发路径停用；若将来恢复后端转发，
    需把这里改为 SSE 流式透传（参考 agent-service/app/api_agent.py 的 EventSourceResponse）。
    """
    if not agent_available():
        return None
    url = settings.AGENT_BASE_URL.rstrip("/") + "/agent/chat"
    body = {
        "query": payload.get("query"),
        "session_id": payload.get("session_id"),
    }
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-User-Id": payload.get("user_id") or "",
    }
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_body = resp.read().decode("utf-8")
            return json.loads(resp_body) if resp_body else {}
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return None


def map_cards_to_logs(cards: list, message_id: str, session_id: str, user_id: str, query_text: str) -> list[dict]:
    """把推荐卡片（前端 mock 字段）转成 recommendation_logs 行。

    字段映射（mock → 表）：
      personId / person.id → person_id
      rank                → rank
      reasons             → reasons
      score（缺省）        → score（mock 无 score，暂填 0）
    """
    rows = []
    for card in cards or []:
        person = card.get("person") or {}
        person_id = card.get("personId") or person.get("id") or ""
        rows.append({
            "message_id": message_id,
            "session_id": session_id,
            "user_id": user_id,
            "query_text": query_text,
            "person_id": person_id,
            "rank": card.get("rank", 0),
            "score": card.get("score", 0),
            "reasons": card.get("reasons") or [],
        })
    return rows
