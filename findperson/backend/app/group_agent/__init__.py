"""群聊 Agent 网关。

平台无关的群聊 Agent 事件、回复、动作和适配器契约。
当前 FpIM 通过 integration.py 接入，其他 IM 通过 /api/v1/group-agent/* 接入。
"""

from .contracts import (
    AgentAction,
    AgentReply,
    BrainRequest,
    BrainResponse,
    ContextMessage,
    GroupAgentEvent,
    GroupAgentResult,
)
from .service import GroupAgentService

__all__ = [
    "AgentAction",
    "AgentReply",
    "BrainRequest",
    "BrainResponse",
    "ContextMessage",
    "GroupAgentEvent",
    "GroupAgentResult",
    "GroupAgentService",
]
