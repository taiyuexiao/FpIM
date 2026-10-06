"""群聊 Agent 编排服务。

职责：
1. 识别 @Agent / `/agent` 触发；
2. 将 IM 无关事件交给可替换 AgentBrain；
3. 把回复交给 ReplySink（当前 IM 或外部 IM 回调）；
4. 管理待确认动作，确认后交给 ActionExecutor。

服务本身不依赖 SQLAlchemy，方便单元测试，也方便其他 IM 通过 HTTP 复用。
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
import uuid
from collections import deque
from collections.abc import Callable
from typing import Any, Protocol

from .brains import AgentBrain, HeuristicBrain
from .contracts import (
    ActionDecision,
    AgentAction,
    AgentReply,
    BrainRequest,
    ContextMessage,
    GroupAgentEvent,
    GroupAgentResult,
)


class ReplySink(Protocol):
    def send(self, event: GroupAgentEvent, reply: AgentReply) -> Any: ...


class ActionExecutor(Protocol):
    def execute(self, action: AgentAction, decision: ActionDecision) -> dict[str, Any]: ...


class NullActionExecutor:
    def execute(self, action: AgentAction, decision: ActionDecision) -> dict[str, Any]:
        return {"executed": False, "reason": "未配置业务执行器，仅保存确认结果"}


_TRIGGER_RE = re.compile(
    r"(?:^|\s)(?:@?(?:agent|group-agent|小管家|群聊\s*agent)\b|/(?:agent|ask)(?:\s|$))",
    re.IGNORECASE,
)
_TRIGGER_NAMES = {"agent", "group-agent", "小管家", "群聊 agent"}


def _known_mention(value: str) -> bool:
    return value.strip().casefold() in {name.casefold() for name in _TRIGGER_NAMES}


class GroupAgentService:
    def __init__(
        self,
        brain: AgentBrain | None = None,
        reply_sink: ReplySink | None = None,
        action_executor: ActionExecutor | None = None,
        trigger_names: set[str] | None = None,
        callback_timeout_seconds: float = 5.0,
    ) -> None:
        self.brain = brain or HeuristicBrain()
        self.reply_sink = reply_sink
        self.action_executor = action_executor or NullActionExecutor()
        self.trigger_names = trigger_names or _TRIGGER_NAMES
        self.callback_timeout_seconds = callback_timeout_seconds
        self._actions: dict[str, AgentAction] = {}
        self._seen_events: dict[str, GroupAgentResult] = {}
        self._seen_order: deque[str] = deque(maxlen=2048)

    def handle_event(self, event: GroupAgentEvent | dict[str, Any]) -> GroupAgentResult:
        event = GroupAgentEvent.model_validate(event)
        event_key = f"{event.source}:{event.conversation_id}:{event.message_id}"
        if event.message_id and event_key in self._seen_events:
            previous = self._seen_events[event_key]
            return previous.model_copy(update={"duplicate": True})

        trigger = self._extract_trigger(event)
        if not trigger and event.trigger_mode != "always":
            return GroupAgentResult(handled=False, reason="未触发群聊 Agent")

        query = self._strip_trigger(event.text, trigger)
        command = self._parse_command(query)
        if command == "draft-issue":
            query = re.sub(
                r"^(?:draft-issue|立项|创建问题|新建问题)\b",
                "",
                query,
                flags=re.IGNORECASE,
            ).strip()
        request = BrainRequest(
            query=query if command != "help" else query or "帮助",
            command=command,
            event=event,
            context=event.context,
        )
        response = self.brain.respond(request)
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        trace_id = response.trace_id or f"trace-{uuid.uuid4().hex[:12]}"
        reply = AgentReply(
            text=response.text or "群聊 Agent 已处理请求。",
            kind="card" if response.cards else "text",
            cards=response.cards,
            actions=response.actions,
            run_id=run_id,
            trace_id=trace_id,
            reply_to=event.message_id or None,
            degraded=response.degraded,
            metadata=response.metadata,
        )
        for action in response.actions:
            self._actions[action.id] = action

        result = GroupAgentResult(
            handled=True,
            reason="triggered",
            run_id=run_id,
            trace_id=trace_id,
            replies=[reply],
            actions=response.actions,
        )
        if event.message_id:
            self._seen_events[event_key] = result
            self._seen_order.append(event_key)
            while len(self._seen_order) > self._seen_order.maxlen:
                self._seen_events.pop(self._seen_order.popleft(), None)

        if self.reply_sink:
            try:
                self.reply_sink.send(event, reply)
            except Exception as exc:  # noqa: BLE001 - 回复失败不应吞掉原始群聊消息
                reply.metadata = {**reply.metadata, "replyError": str(exc)[:200]}
        if event.reply_url:
            self._post_callback(event.reply_url, result)
        return result

    def confirm_action(self, action_id: str, decision: ActionDecision | dict[str, Any]) -> AgentAction:
        decision = ActionDecision.model_validate(decision)
        action = self._actions.get(action_id)
        if not action:
            raise KeyError(action_id)
        if action.status not in {"pending", "needs_input"}:
            return action
        if not decision.approved:
            action.status = "rejected"
            action.execution = {"note": decision.note}
            return action
        if action.status == "needs_input":
            for key, value in decision.metadata.items():
                if value not in (None, ""):
                    action.payload[key] = value
            if action.kind == "create_issue" and action.payload.get("assigneePersonId"):
                action.status = "pending"
            else:
                action.execution = {"reason": "动作缺少必填信息，暂不能执行"}
                return action
        try:
            action.execution = self.action_executor.execute(action, decision)
            action.status = "approved"
        except Exception as exc:  # noqa: BLE001 - 业务执行器错误显式落动作
            action.status = "failed"
            action.execution = {"error": str(exc)[:300]}
        return action

    def get_action(self, action_id: str) -> AgentAction | None:
        return self._actions.get(action_id)

    def _extract_trigger(self, event: GroupAgentEvent) -> str:
        for mention in event.mentions:
            if _known_mention(mention):
                return mention
        match = _TRIGGER_RE.search(event.text or "")
        return match.group(0).strip() if match else ""

    @staticmethod
    def _strip_trigger(text: str, trigger: str) -> str:
        value = (text or "").strip()
        if trigger:
            value = re.sub(re.escape(trigger), "", value, count=1, flags=re.IGNORECASE).strip()
        value = re.sub(r"^/(?:agent|ask)\b", "", value, flags=re.IGNORECASE).strip()
        return value

    @staticmethod
    def _parse_command(query: str) -> str:
        lowered = query.casefold()
        if not query or lowered in {"help", "帮助", "？", "?"}:
            return "help"
        if lowered.startswith(("summarize", "总结", "摘要")):
            return "summarize"
        if lowered.startswith(("draft-issue", "立项", "创建问题", "新建问题")):
            return "draft-issue"
        return "ask"

    def _post_callback(self, reply_url: str, result: GroupAgentResult) -> None:
        if not reply_url.startswith(("http://", "https://")):
            return
        payload = {
            "type": "group_agent.reply",
            "result": result.model_dump(by_alias=True, mode="json"),
        }
        request = urllib.request.Request(
            reply_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(request, timeout=self.callback_timeout_seconds).read()
        except (urllib.error.URLError, TimeoutError, OSError):
            # 外部 IM 的回调失败不回滚本次处理；调用方仍可读取同步响应。
            return


def build_brain(agent_service_url: str = "", use_agent_service: bool = True,
                timeout_seconds: float = 8.0, tool_executor=None) -> AgentBrain:
    """构建 Brain（所有 Agent 能力共用）：DeepSeek 大模型优先，失败自动降级启发式。

    用户决策（2026-10-05）：所有 agent 能力均用 DeepSeek；agent-service 仅在
    未配置 DEEPSEEK_API_KEY 时作为兼容路径。
    """
    from ..core.config import settings as _settings
    from .brains import DeepSeekBrain, HttpAgentBrain

    heuristic = HeuristicBrain()
    if _settings.DEEPSEEK_API_KEY and _settings.DEEPSEEK_API_KEY != "CHANGE_ME":
        return DeepSeekBrain(
            api_key=_settings.DEEPSEEK_API_KEY,
            base_url=_settings.DEEPSEEK_BASE_URL or "https://api.deepseek.com",
            model=_settings.DEEPSEEK_MODEL or "deepseek-chat",
            timeout_seconds=_settings.DEEPSEEK_TIMEOUT_SECONDS or 30.0,
            fallback=heuristic,
            tool_executor=tool_executor,
        )
    if not use_agent_service or not agent_service_url:
        return heuristic
    return HttpAgentBrain(agent_service_url, timeout_seconds=timeout_seconds, fallback=heuristic)
