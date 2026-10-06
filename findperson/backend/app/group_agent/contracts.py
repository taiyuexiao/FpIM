"""群聊 Agent 的平台无关契约。

这些模型同时是 Python API 和外部 IM HTTP API 的边界。字段使用 camelCase
作为 JSON 别名，内部代码使用 snake_case；`populate_by_name` 允许两种输入风格。
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class ContextMessage(ContractModel):
    """群聊上下文消息。只传文本与元数据，不绑定任何 IM 的消息模型。"""

    sender_id: str = Field(default="", alias="senderId")
    sender_name: str | None = Field(default=None, alias="senderName")
    text: str = ""
    created_at: str | None = Field(default=None, alias="createdAt")
    metadata: dict[str, Any] = Field(default_factory=dict)


class GroupAgentEvent(ContractModel):
    """外部 IM 或 FpIM 投递进来的群聊事件。"""

    source: str = "generic"
    conversation_id: str = Field(alias="conversationId")
    message_id: str = Field(default="", alias="messageId")
    sender_id: str = Field(default="", alias="senderId")
    sender_name: str | None = Field(default=None, alias="senderName")
    text: str = ""
    mentions: list[str] = Field(default_factory=list)
    thread_id: str | None = Field(default=None, alias="threadId")
    context: list[ContextMessage] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    reply_url: str | None = Field(default=None, alias="replyUrl")
    trigger_mode: Literal["mention", "always", "command"] = Field(
        default="mention", alias="triggerMode"
    )


class AgentAction(ContractModel):
    """Agent 产出的待确认动作。Agent 不直接写业务状态，动作必须人工确认。"""

    id: str
    kind: str
    title: str
    description: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = Field(default=True, alias="requiresConfirmation")
    status: Literal["pending", "needs_input", "approved", "rejected", "failed"] = "pending"
    execution: dict[str, Any] = Field(default_factory=dict)


class AgentReply(ContractModel):
    """Agent 发回群聊的一条回复。"""

    text: str
    kind: Literal["text", "card", "system"] = "text"
    cards: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[AgentAction] = Field(default_factory=list)
    run_id: str = Field(default="", alias="runId")
    trace_id: str = Field(default="", alias="traceId")
    reply_to: str | None = Field(default=None, alias="replyTo")
    degraded: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class GroupAgentResult(ContractModel):
    """一次事件处理结果。"""

    handled: bool
    reason: str = ""
    duplicate: bool = False
    run_id: str = Field(default="", alias="runId")
    trace_id: str = Field(default="", alias="traceId")
    replies: list[AgentReply] = Field(default_factory=list)
    actions: list[AgentAction] = Field(default_factory=list)


class BrainRequest(ContractModel):
    """传给 Agent Brain 的规范化请求。"""

    query: str
    command: str = "ask"
    event: GroupAgentEvent
    context: list[ContextMessage] = Field(default_factory=list)


class BrainResponse(ContractModel):
    """Agent Brain 的返回。允许 Brain 只给文本，也允许给结构化卡片/动作。"""

    text: str = ""
    cards: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[AgentAction] = Field(default_factory=list)
    trace_id: str = Field(default="", alias="traceId")
    degraded: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActionDecision(ContractModel):
    """动作确认请求。"""

    approved: bool = True
    actor_id: str = Field(default="", alias="actorId")
    note: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
