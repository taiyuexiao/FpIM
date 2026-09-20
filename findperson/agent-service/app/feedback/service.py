"""反馈服务:点踩原因配置 + 排序回流调整(反馈回流优化,在线部分)。

回流策略(确定性、可解释):
- 聚合每个人员收到的 有帮助/没帮助 计数;
- adjustment = weight × (up - down) / (up + down + 1) ∈ (-weight, weight);
- weight 由 FEEDBACK_RANK_WEIGHT 配置(默认 0.1,只微调不颠覆排序证据);
- 反馈只调整,不产生/消除候选人(候选仍由检索证据决定,§12.3 确定性排序)。
"""
from __future__ import annotations

from app.config import get_settings
from app.feedback.repository import FeedbackRepository

# 点踩原因配置(GET /agent/feedback/reasons,实施方案v3 §3.2)
DOWN_REASONS = [
    {"code": "wrong_person", "label": "推荐人选不对"},
    {"code": "stale_info", "label": "职责/联系方式已过期"},
    {"code": "missing_scope", "label": "没有覆盖我问的范围"},
    {"code": "incomplete", "label": "回答不完整"},
    {"code": "other", "label": "其他"},
]


class FeedbackService:
    """反馈领域服务。"""

    def __init__(self, repo: FeedbackRepository | None = None) -> None:
        self._repo = repo or FeedbackRepository()

    @staticmethod
    def down_reasons() -> list[dict[str, str]]:
        return list(DOWN_REASONS)

    async def person_adjustments(self) -> dict[str, float]:
        """人员排序反馈调整值:{person_id: [-weight, weight]}。"""
        weight = float(get_settings().feedback_rank_weight)
        if weight <= 0:
            return {}
        summary = await self._repo.person_vote_summary()
        adjustments: dict[str, float] = {}
        for person_id, votes in summary.items():
            up, down = votes["up"], votes["down"]
            if up == 0 and down == 0:
                continue
            adjustments[person_id] = round(weight * (up - down) / (up + down + 1), 4)
        return adjustments
