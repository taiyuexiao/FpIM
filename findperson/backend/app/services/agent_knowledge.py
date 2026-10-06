"""Agent 知识库服务（二期 R1）：知识检索与代答文案组装。

披露红线（research-agent-capability-mapping.md）：只查「已授权分享给当前群」的知识，
能读≠能分享——私有知识不得因为能被检索到就进入群回答。
"""
from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.orm import Session

def _tokens(text_str: str) -> list[str]:
    """中文按连续段取二元组/整段，英文数字取词——中文无空格，不能按空格切。"""
    toks: set[str] = set()
    for w in re.findall(r"[A-Za-z0-9_]{2,}", text_str or ""):
        toks.add(w.lower())
    for seg in re.findall(r"[\u4e00-\u9fff]+", text_str or ""):
        if len(seg) <= 4:
            toks.add(seg)
        for i in range(max(0, len(seg) - 1)):
            toks.add(seg[i:i + 2])
    return sorted(toks)


def find_relevant_knowledge(db: Session, conv_id: int, question: str,
                            limit: int = 3) -> list[dict]:
    """关键词命中「授权给本群」的 active 知识，按命中词数排序。"""
    toks = _tokens(question)
    if not toks:
        return []
    rows = db.execute(text(
        """
        SELECT k.id, k.title, k.content, k.owner_person_id, u.name
          FROM public.agent_knowledge k
          LEFT JOIN public.user2 u ON u.id = k.owner_person_id
         WHERE k.status = 'active'
           AND EXISTS (SELECT 1 FROM jsonb_array_elements_text(k.shared_group_ids) g
                        WHERE g = :cid)
        """
    ), {"cid": str(conv_id)}).fetchall()
    scored = []
    for r in rows:
        hay = f"{r[1] or ''} {r[2] or ''}"
        score = sum(1 for t in toks if t in hay)
        if score:
            scored.append((score, r))
    scored.sort(key=lambda x: -x[0])
    return [{
        "id": r[0], "title": r[1], "content": r[2],
        "ownerId": r[3], "ownerName": r[4] or r[3], "score": s,
    } for s, r in scored[:limit]]


def find_owner_knowledge(db: Session, owner_id: str, question: str,
                         limit: int = 3) -> list[dict]:
    """私聊代理（R2）用：委托人自己的知识库（无需分享授权——是其本人的代理）。"""
    toks = _tokens(question)
    if not toks:
        return []
    rows = db.execute(text(
        """
        SELECT k.id, k.title, k.content, k.owner_person_id, u.name
          FROM public.agent_knowledge k
          LEFT JOIN public.user2 u ON u.id = k.owner_person_id
         WHERE k.status = 'active' AND k.owner_person_id = :owner
        """
    ), {"owner": owner_id}).fetchall()
    scored = []
    for r in rows:
        hay = f"{r[1] or ''} {r[2] or ''}"
        score = sum(1 for t in toks if t in hay)
        if score:
            scored.append((score, r))
    scored.sort(key=lambda x: -x[0])
    return [{
        "id": r[0], "title": r[1], "content": r[2],
        "ownerId": r[3], "ownerName": r[4] or r[3], "score": s,
    } for s, r in scored[:limit]]


def compose_knowledge_answer(hits: list[dict], attribution: bool = True) -> str:
    """把知识命中组装成可直接发送的回答（带来源，不编造）。"""
    best = hits[0]
    head = f"【{best['ownerName']} 的知识库·代答】" if attribution else ""
    body = (best["content"] or "").strip()
    if len(body) > 600:
        body = body[:600] + "…"
    more = ""
    if len(hits) > 1:
        more = "\n（另命中：" + "、".join(f"《{h['title']}》" for h in hits[1:]) + "）"
    return f"{head}\n{body}\n——依据：《{best['title']}》{more}"


def answer_with_llm(question: str, hits: list[dict]) -> str:
    """用 DeepSeek 依据知识材料组答（带来源）；失败回退确定性拼接。"""
    if not hits:
        return ""
    try:
        from ..group_agent.contracts import BrainRequest, ContextMessage, GroupAgentEvent
        from ..group_agent.service import build_brain
        from ..core.config import settings

        context = [
            ContextMessage(
                sender_id="knowledge",
                sender_name=f"知识库·{h.get('ownerName') or ''}·《{h.get('title') or ''}》",
                text=h.get("content") or "",
            )
            for h in hits
        ]
        event = GroupAgentEvent(source="knowledge", conversation_id="0",
                                text=question, context=context)
        req = BrainRequest(
            query=f"请严格依据以上知识库材料回答：{question}\n（结尾注明依据了哪份材料；材料未覆盖的部分明确说明缺口）",
            event=event, context=context)
        resp = build_brain(
            settings.AGENT_SERVICE_URL,
            use_agent_service=settings.GROUP_AGENT_USE_AGENT_SERVICE,
            timeout_seconds=settings.DEEPSEEK_TIMEOUT_SECONDS,
        ).respond(req)
        if resp.text and not resp.degraded:
            return resp.text
    except Exception:  # noqa: BLE001
        pass
    return compose_knowledge_answer(hits)
