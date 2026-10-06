"""群聊 Agent 网关契约与 HTTP API 回归测试。

这些测试不依赖数据库和外部 agent-service，保证通用接口可被其他 IM 复用。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import httpx
import pytest

from app.core.config import settings
from app.group_agent.brains import HeuristicBrain
from app.group_agent.contracts import ActionDecision, GroupAgentEvent
from app.group_agent.integration import reset_service_for_tests
from app.group_agent.service import GroupAgentService
from app.main import app


class RecordingSink:
    def __init__(self):
        self.items = []

    def send(self, event, reply):
        self.items.append((event, reply))


def test_trigger_commands_and_idempotency():
    sink = RecordingSink()
    service = GroupAgentService(brain=HeuristicBrain(), reply_sink=sink)

    event = GroupAgentEvent(
        source="feishu",
        conversation_id="oc-1",
        message_id="m-1",
        sender_id="u-1",
        text="@agent summarize",
        context=[
            {"senderId": "u-1", "senderName": "甲", "text": "先看登录问题"},
            {"senderId": "u-2", "senderName": "乙", "text": "我来查权限"},
        ],
    )
    result = service.handle_event(event)
    assert result.handled is True
    assert result.replies[0].text.startswith("群聊摘要")
    assert len(sink.items) == 1

    duplicate = service.handle_event(event)
    assert duplicate.duplicate is True
    assert len(sink.items) == 1

    not_triggered = service.handle_event(
        GroupAgentEvent(source="feishu", conversation_id="oc-1", message_id="m-2",
                        sender_id="u-1", text="普通群聊消息")
    )
    assert not_triggered.handled is False


def test_draft_issue_requires_confirmation():
    service = GroupAgentService(brain=HeuristicBrain())
    result = service.handle_event(
        GroupAgentEvent(
            source="generic",
            conversation_id="oc-2",
            message_id="m-3",
            sender_id="u-1",
            text="/agent draft-issue 登录页报错",
        )
    )
    action = result.actions[0]
    assert action.kind == "create_issue"
    assert action.status == "needs_input"
    confirmed = service.confirm_action(action.id, ActionDecision(approved=True, actor_id="u-1"))
    assert confirmed.status == "needs_input"
    assert confirmed.execution["reason"]

    completed = service.confirm_action(
        action.id,
        ActionDecision(approved=True, actor_id="u-1", metadata={"assigneePersonId": "u-2"}),
    )
    assert completed.status == "approved"
    assert completed.execution["executed"] is False


def test_external_api_and_key_auth():
    old_key = settings.GROUP_AGENT_API_KEY
    old_use_agent = settings.GROUP_AGENT_USE_AGENT_SERVICE
    settings.GROUP_AGENT_API_KEY = "test-group-agent-key"
    settings.GROUP_AGENT_USE_AGENT_SERVICE = False
    reset_service_for_tests(GroupAgentService(brain=HeuristicBrain()))
    try:
        def run(coro):
            return asyncio.run(coro)

        async def scenario():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                unauthorized = await client.post(
                    "/api/v1/group-agent/events",
                    json={"conversationId": "oc-3", "messageId": "m-4", "text": "@agent help"},
                )
                assert unauthorized.status_code == 401

                authorized = await client.post(
                    "/api/v1/group-agent/events",
                    json={"conversationId": "oc-3", "messageId": "m-4", "text": "@agent help"},
                    headers={"X-Group-Agent-Key": "test-group-agent-key"},
                )
                assert authorized.status_code == 200
                payload = authorized.json()
                assert payload["handled"] is True
                assert payload["replies"][0]["text"].startswith("群聊 Agent")

                caps = await client.get("/api/v1/group-agent/capabilities")
                assert caps.status_code == 200
                assert caps.json()["writePolicy"].startswith("Agent 只产草稿")

        run(scenario())
    finally:
        settings.GROUP_AGENT_API_KEY = old_key
        settings.GROUP_AGENT_USE_AGENT_SERVICE = old_use_agent
        reset_service_for_tests()
