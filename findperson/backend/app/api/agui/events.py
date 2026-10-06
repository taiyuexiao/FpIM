"""AGUI 交互上报：POST /agui/events（feedback_toggle → public.feedback）"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...middleware.deps import get_current_user
from ...models.assistant import Feedback
from .schemas import InteractionEvent

router = APIRouter(prefix="/events", tags=["AGUI"])

_TARGET_TYPES = ("answer", "person", "content")


def _infer_target_type(target_key: str) -> str:
    """前端 targetType 不传，从 targetId 前缀推断（answer:/person:/content:）。"""
    if not target_key:
        return "answer"
    prefix = target_key.split(":", 1)[0]
    return prefix if prefix in _TARGET_TYPES else "answer"


@router.post("", summary="Report AGUI Event", description="反馈/交互事件上报")
def report_event(body: InteractionEvent, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)

    # 赞/踩/取消 → public.feedback（value 三态：up / down / 空=取消）
    if body.eventType == "feedback_toggle":
        target_type = body.targetType or _infer_target_type(body.targetId)
        target_key = body.targetId or ""
        value = body.value if body.value in ("up", "down") else ""

        if target_key:
            existing = db.query(Feedback).filter(
                Feedback.user_id == user.id,
                Feedback.target_type == target_type,
                Feedback.target_key == target_key,
            ).first()

            if value in ("up", "down"):
                # 同一 target 重复上报 → 更新状态（up↔down 切换），不新增行
                if existing:
                    existing.value = value
                else:
                    db.add(Feedback(
                        user_id=user.id,
                        target_type=target_type,
                        target_key=target_key,
                        value=value,
                    ))
            elif existing:
                # 取消（value 为空）→ 删除记录
                db.delete(existing)

            db.commit()

    # 其他交互事件（person_detail_open / confirm_* 等）暂只收不落库
    return {"accepted": True}
