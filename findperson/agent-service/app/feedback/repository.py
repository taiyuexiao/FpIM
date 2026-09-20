"""反馈存储(v4 §四:回答与推荐卡片有帮助/没帮助互斥反馈,再次点击取消)。

规则:
- 同一用户对同一对象(target_type+target_id)同一消息(message_id)仅保留一种反馈;
- 再次点击同值 = 取消(DELETE);点击异值 = 改值(UPDATE);
- 推荐反馈必须关联 session_id/message_id/trace_id;
- interaction 类事件(详情查看/确认等)不去重,全量追加。
"""
from __future__ import annotations

import json
from typing import Any

from app.core import db

# 反馈值 ↔ feedback_type 映射(对外 value 用 up/down,库内 like/dislike)
_VALUE_TO_TYPE = {"up": "like", "down": "dislike", "like": "like", "dislike": "dislike"}


class FeedbackRepository:
    """feedback_events 读写。"""

    async def record_vote(
        self,
        *,
        user_id: str,
        target_type: str,
        target_id: str,
        value: str,
        message_id: str = "",
        session_id: str | None = None,
        trace_id: str = "",
        reason: str = "",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        """记录有帮助/没帮助反馈(互斥 + 可取消)。返回 {"status": recorded/updated/cancelled}。"""
        ftype = _VALUE_TO_TYPE.get(value)
        if ftype is None:
            raise ValueError(f"非法反馈值: {value}(仅支持 up/down)")
        existing = await db.fetchrow(
            "SELECT id, feedback_type FROM agent.feedback_events"
            " WHERE user_id=$1 AND target_type=$2 AND target_id=$3 AND message_id=$4"
            "   AND feedback_type IN ('like','dislike')",
            user_id, target_type, target_id, message_id,
        )
        if existing and existing["feedback_type"] == ftype:
            await db.execute("DELETE FROM agent.feedback_events WHERE id=$1", existing["id"])
            return {"status": "cancelled", "feedback_type": ftype}
        if existing:
            await db.execute(
                "UPDATE agent.feedback_events SET feedback_type=$1, reason=$2, payload=$3,"
                " trace_id=$4, session_id=$5, created_at=now() WHERE id=$6",
                ftype, reason, json.dumps(payload or {}, ensure_ascii=False),
                trace_id, session_id, existing["id"],
            )
            return {"status": "updated", "feedback_type": ftype}
        await db.execute(
            "INSERT INTO agent.feedback_events"
            " (trace_id, session_id, message_id, user_id, feedback_type,"
            "  target_type, target_id, value, reason, payload)"
            " VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",
            trace_id, session_id, message_id, user_id, ftype,
            target_type, target_id, "up" if ftype == "like" else "down",
            reason, json.dumps(payload or {}, ensure_ascii=False),
        )
        return {"status": "recorded", "feedback_type": ftype}

    async def record_interaction(
        self,
        *,
        user_id: str,
        event_type: str,
        target_type: str = "",
        target_id: str = "",
        message_id: str = "",
        session_id: str | None = None,
        trace_id: str = "",
        context: dict[str, Any] | None = None,
    ) -> None:
        """记录交互事件(详情打开/卡片确认/点踩原因等),全量追加。"""
        await db.execute(
            "INSERT INTO agent.feedback_events"
            " (trace_id, session_id, message_id, user_id, feedback_type,"
            "  target_type, target_id, value, payload)"
            " VALUES($1,$2,$3,$4,'interaction',$5,$6,$7,$8)",
            trace_id, session_id, message_id, user_id,
            target_type, target_id, event_type,
            json.dumps(context or {}, ensure_ascii=False),
        )

    async def person_vote_summary(self) -> dict[str, dict[str, int]]:
        """按人员聚合反馈:{person_id: {"up": n, "down": n}}(排序回流入参)。

        两类事件都计入:
        - target_type='person':直接对人员的反馈(target_id 即人员);
        - target_type='answer':回答级反馈(前端「有帮助/没帮助」的实际形态),
          按 trace 关联该轮推荐日志,归到该轮全部候选人名下——
          没有这层归属时排序回流永远拿不到票(反馈优化「未上线」的根因)。
        """
        rows = await db.fetch(
            "WITH votes AS ("
            "  SELECT target_id AS pid, feedback_type FROM agent.feedback_events"
            "  WHERE target_type='person' AND feedback_type IN ('like','dislike')"
            "  UNION ALL"
            "  SELECT c->>'person_id', e.feedback_type"
            "  FROM agent.feedback_events e"
            "  JOIN (SELECT DISTINCT ON (trace_id) trace_id, message_id, ranked_candidates"
            "        FROM agent.agent_recommendation_logs ORDER BY trace_id, id DESC) l"
            "    ON l.trace_id = e.trace_id AND e.trace_id <> ''"
            "   AND (e.message_id = '' OR l.message_id = e.message_id)"
            "  CROSS JOIN LATERAL jsonb_array_elements(l.ranked_candidates) c"
            "  WHERE e.target_type='answer' AND e.feedback_type IN ('like','dislike')"
            ")"
            " SELECT pid, feedback_type, count(*) AS n FROM votes"
            " GROUP BY pid, feedback_type",
        )
        summary: dict[str, dict[str, int]] = {}
        for r in rows:
            slot = summary.setdefault(r["pid"], {"up": 0, "down": 0})
            slot["up" if r["feedback_type"] == "like" else "down"] = int(r["n"])
        return summary
