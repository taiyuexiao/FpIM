"""群聊 Agent 通用 HTTP API。

当前 FpIM 群聊通过 integration.py 直接调用服务；飞书、企业微信、Slack 等
其他 IM 可以把消息事件 POST 到本路由，并通过同步返回值或 replyUrl 获取回复。
"""
from __future__ import annotations

import hmac

from fastapi import APIRouter, HTTPException, Request

from ...core.config import settings
from ...group_agent.contracts import ActionDecision, GroupAgentEvent
from ...group_agent.integration import get_service

router = APIRouter(prefix="/group-agent", tags=["group-agent"])


def require_group_agent_key(request: Request) -> None:
    expected = settings.GROUP_AGENT_API_KEY
    if not expected:
        raise HTTPException(status_code=503, detail="未配置 GROUP_AGENT_API_KEY")
    provided = request.headers.get("X-Group-Agent-Key", "")
    if not provided and request.headers.get("Authorization", "").startswith("Bearer "):
        provided = request.headers["Authorization"][7:]
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="群聊 Agent API Key 无效")


@router.get("/capabilities")
def capabilities() -> dict:
    """无需密钥的能力发现，供外部 IM 配置向导使用。"""
    return {
        "name": "FpIM Group Agent",
        "version": "0.1.0",
        "triggers": ["@agent", "@小管家", "/agent", "/ask"],
        "commands": ["help", "summarize", "draft-issue", "ask"],
        "eventEndpoint": "/api/v1/group-agent/events",
        "actionEndpoint": "/api/v1/group-agent/actions/{actionId}/confirm",
        "writePolicy": "Agent 只产草稿，业务动作需人工确认",
    }


@router.post("/events")
def handle_event(
    event: GroupAgentEvent,
    request: Request,
) -> dict:
    """接收任意 IM 的群聊事件，同步返回处理结果。

    `replyUrl` 可选；配置后服务会额外 POST 一份 `group_agent.reply` 回调。
    """
    require_group_agent_key(request)
    return get_service().handle_event(event).model_dump(by_alias=True, mode="json")


@router.get("/actions/{action_id}")
def get_action(action_id: str, request: Request) -> dict:
    require_group_agent_key(request)
    action = get_service().get_action(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="动作不存在")
    return action.model_dump(by_alias=True, mode="json")


@router.post("/actions/{action_id}/confirm")
def confirm_action(
    action_id: str,
    decision: ActionDecision,
    request: Request,
) -> dict:
    """确认动作。只有确认后才允许执行器触碰业务写入。"""
    require_group_agent_key(request)
    try:
        action = get_service().confirm_action(action_id, decision)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="动作不存在") from exc
    return action.model_dump(by_alias=True, mode="json")
