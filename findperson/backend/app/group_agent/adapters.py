"""FpIM 适配器：把通用群聊 Agent 接到当前项目的 IM 会话。"""
from __future__ import annotations

from typing import Any

from .contracts import ActionDecision, AgentAction, AgentReply, GroupAgentEvent

GROUP_AGENT_ID = "group-agent"


class FpIMReplySink:
    """将 AgentReply 写回当前 im.messages，并通过既有 WS/REST 链路广播。"""

    def send(self, event: GroupAgentEvent, reply: AgentReply) -> dict[str, Any]:
        from ..core.database import SessionLocal
        from ..services import im as im_service

        db = SessionLocal()
        try:
            content = {
                "text": reply.text,
                "agent": {
                    "name": "群聊 Agent",
                    "runId": reply.run_id,
                    "traceId": reply.trace_id,
                    "cards": reply.cards,
                    "actions": [action.model_dump(by_alias=True, mode="json") for action in reply.actions],
                },
            }
            message, created = im_service.send_message(
                db,
                conv_id=int(event.conversation_id),
                sender_id=GROUP_AGENT_ID,
                msg_type="text",
                content=content,
                client_msg_id=f"group-agent:{event.message_id or reply.run_id}",
            )
            from ..ws.im_gateway import broadcast_message_sync
            broadcast_message_sync(int(event.conversation_id), message)
            return {"message": message, "created": created}
        finally:
            db.close()


class FpIMActionExecutor:
    """当前项目的动作执行器：只执行已确认的业务动作。"""

    def execute(self, action: AgentAction, decision: ActionDecision) -> dict[str, Any]:
        if action.kind != "create_issue":
            return {"executed": False, "reason": f"暂不支持动作类型 {action.kind}"}

        from ..core.database import SessionLocal
        from ..services import im as im_service

        payload = action.payload
        conversation_id = payload.get("conversationId")
        if not conversation_id:
            raise ValueError("缺少 conversationId")
        assignee_id = payload.get("assigneePersonId")
        if not assignee_id:
            raise ValueError("群聊立项必须指定唯一责任人")

        db = SessionLocal()
        try:
            result = im_service.create_issue_in_conversation(
                db,
                conv_id=int(conversation_id),
                creator_id=decision.actor_id or str(payload.get("creatorId") or ""),
                question=str(payload.get("question") or ""),
                assignee_id=str(assignee_id),
                summary=str(payload.get("summary") or ""),
            )
            return {"executed": True, "issue": result.get("issue"), "message": result.get("message")}
        finally:
            db.close()
