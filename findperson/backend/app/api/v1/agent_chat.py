"""Agent 交互面板接口（二期 agent-panel 第一切片）。

- POST /api/v1/agent/chat   与 Agent 自然语言交互（复用 group-agent 的 Brain：
  agent-service 可用则用之，失败自动降级启发式）

设计要点见 docs/modules/agent-panel.md：面板与群 @走同一个 Agent 内核；
面板里的写动作（actions）只返回草稿卡片，仍须确认后才执行（ActionExecutor 红线）。
切片 1 为同步 JSON；流式输出（SSE）与对话持久化在下一切片。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...core.config import settings
from ...core.database import get_db
from ...middleware.deps import get_current_user
from ...models.user import User
from ...group_agent.contracts import BrainRequest, GroupAgentEvent, ContextMessage
from ...group_agent.integration import _load_context
from ...group_agent.service import build_brain

router = APIRouter(tags=["Agent 面板"])

_brain = None


def _get_brain():
    global _brain
    if _brain is None:
        from ..agent_tools import make_tool_executor
        _brain = build_brain(
            settings.AGENT_SERVICE_URL,
            use_agent_service=settings.GROUP_AGENT_USE_AGENT_SERVICE,
            timeout_seconds=settings.GROUP_AGENT_BRAIN_TIMEOUT_SECONDS,
            tool_executor=make_tool_executor(),
        )
    return _brain


class AgentChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    conversationId: int | None = None   # 可选：带上当前会话上下文


@router.post("/agent/chat", summary="Agent 面板对话",
             description="与 Agent 自然语言交互；可带当前会话作为上下文")
def agent_chat(body: AgentChatIn, request: Request,
               db: Session = Depends(get_db)):
    user = get_current_user(request, db)

    # R3 工具优先：识别"把名为 xxx 的文件发给…"直接执行并回凭据
    from ...agent_tools import run_file_command
    tool_result = run_file_command(db, user.id, body.conversationId or 0, body.text)
    if tool_result:
        return {"reply": {"text": tool_result, "actions": [], "cards": [], "degraded": False},
                "traceId": f"tool-{user.id}"}

    context: list[ContextMessage] = []
    if body.conversationId:
        try:
            context = _load_context(db, body.conversationId)
        except Exception:  # noqa: BLE001 - 上下文加载失败不阻断对话
            context = []

    event = GroupAgentEvent(
        source="panel",
        conversation_id=str(body.conversationId or f"panel-{user.id}"),
        sender_id=user.id,
        text=body.text,
        context=context,
    )
    request_brain = BrainRequest(query=body.text, command="ask", event=event, context=context)
    try:
        resp = _get_brain().respond(request_brain)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Agent 暂不可用：{exc}") from exc

    return {
        "reply": {
            "text": resp.text,
            "actions": [a.model_dump(by_alias=True, mode="json") for a in resp.actions],
            "cards": resp.cards,
            "degraded": resp.degraded,
        },
        "traceId": resp.trace_id,
    }
