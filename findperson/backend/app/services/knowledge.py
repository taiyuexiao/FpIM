"""知识沉淀:问答有效性判定(LLM)、沉淀打分、候选池 → FAQ。

链路:对话同步(judge_question 过滤有效问题) → 标记已解决(建候选并打分) → 管理员确认(approve 成 FAQ)。
LLM 不可用时降级为启发式,不阻断主流程。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.config import settings
from ..models.issue import Faq, Issue, KnowledgeCandidate
from . import llm

# 沉淀打分(与设计稿一致:已解决 +5 / 重复 +2 / 点赞 +2 / 点踩 -3 / 缺口 +1)
SCORE_RESOLVED = 5
SCORE_REPEAT = 2
SCORE_GAP = 1
CANDIDATE_THRESHOLD = 5  # 达到该分数才进候选池

_GREETING_WORDS = ("你好", "您好", "在吗", "在么", "谢谢", "多谢", "测试", "hi", "hello")


def _strip_code_fence(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def _heuristic_judge(question: str) -> dict:
    """LLM 不可用时的降级判定:去掉寒暄/太短的,其余视为有效。"""
    q = (question or "").strip()
    lowered = q.lower()
    valid = len(q) >= 6 and not any(
        lowered == w or (lowered.startswith(w) and len(q) <= 5) for w in _GREETING_WORDS
    )
    return {"is_valid": valid, "summary": q[:80], "duplicate_of": None, "degraded": True}


def judge_question(question: str, answer: str = "", candidates: list[dict] | None = None,
                   existing: list[dict] | None = None) -> dict:
    """判定一条问答是否是「需要有人负责落实」的有效业务问题。

    candidates: [{"id": "P0090", "name": "安老师"}] 该轮推荐列表(取首推为建议责任人)
    existing:   [{"id": 12, "summary": "跨境报送对接找谁"}] 该用户已有问题(判重)
    返回 {"is_valid", "summary", "duplicate_of", "assignee_person_id", "degraded"?}
    """
    candidates = candidates or []
    existing = existing or []
    fallback = _heuristic_judge(question)
    fallback["assignee_person_id"] = candidates[0].get("id") if candidates else None
    if not settings.DEEPSEEK_API_KEY or not (question or "").strip():
        return fallback

    people = "、".join(f'{c.get("name") or "?"}({c.get("id")})' for c in candidates[:5]) or "无"
    known = "\n".join(f'- id={e["id"]}: {e["summary"]}' for e in existing[:30]) or "（暂无）"
    prompt = (
        "你是银行内部「首问必答平台」的问题归档助手。用户提问后平台会推荐负责人，"
        "现在要把这次问答归档成一条待跟踪的问题记录。\n\n"
        f"用户问题：{question[:600]}\n"
        f"平台回答（节选）：{(answer or '')[:400]}\n"
        f"该轮推荐的人：{people}\n\n"
        "已有问题列表（用于判重）：\n"
        f"{known}\n\n"
        "请判断：\n"
        "1) is_valid：这是不是一个需要找人负责落实的业务问题？"
        "闲聊、寒暄、纯功能询问（如「你是谁」「怎么用」）、无意义内容 → false；\n"
        "2) summary：把问题归一化成一句书面问题（去掉口语，保留系统名/领域等业务要素）；\n"
        "3) duplicate_of：与已有问题列表里某条是同一个问题 → 填它的 id 数字；否则 null；\n"
        "4) assignee_person_id：建议责任人，从上面推荐的人里选 id；没有合适的人填 null。\n\n"
        '只输出 JSON：{"is_valid": true, "summary": "...", "duplicate_of": null, "assignee_person_id": "P0001"}'
    )
    try:
        content = llm.chat(
            [{"role": "system", "content": "你是严谨的问题归档助手，只输出 JSON。"},
             {"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=400,
        )
        data = json.loads(_strip_code_fence(content))
        summary = str(data.get("summary") or "").strip() or fallback["summary"]
        dup = data.get("duplicate_of")
        dup_id = int(dup) if str(dup).strip().isdigit() else None
        assignee = data.get("assignee_person_id") or fallback["assignee_person_id"]
        return {
            "is_valid": bool(data.get("is_valid")),
            "summary": summary[:200],
            "duplicate_of": dup_id,
            "assignee_person_id": assignee,
        }
    except Exception:
        return fallback


def _similar_issue_count(db: Session, question: str) -> int:
    """全局相近问题数(pg_trgm),用于沉淀打分里的「问得多」。"""
    try:
        return int(db.execute(
            text("SELECT count(*) FROM public.issues WHERE similarity(summary, :q) > 0.6"),
            {"q": question[:200]},
        ).scalar() or 0)
    except Exception:
        return 0


def create_candidate_for_issue(db: Session, issue: Issue, answer: str) -> KnowledgeCandidate | None:
    """问题标记「已解决」后调用:算分,够阈值则进候选池(相近问题自动合并累计分)。"""
    related = _similar_issue_count(db, issue.summary or issue.question)
    repeat = max(0, (issue.repeated_count or 1) - 1) + max(0, related - 1)
    score = SCORE_RESOLVED + SCORE_REPEAT * repeat + SCORE_GAP
    signals = {"resolved": True, "repeated": repeat, "related_global": related, "score": score}
    if score < CANDIDATE_THRESHOLD:
        return None

    # 与已有 pending 候选合并(相近问题不重复建)
    existing = db.execute(
        text("SELECT id, score, source_issue_ids FROM public.knowledge_candidates "
             "WHERE status='pending' AND similarity(question, :q) > 0.6 "
             "ORDER BY id DESC LIMIT 1"),
        {"q": issue.summary or issue.question},
    ).fetchone()
    if existing:
        cand = db.query(KnowledgeCandidate).filter(KnowledgeCandidate.id == existing[0]).first()
        ids = list(existing[2] or [])
        if issue.id not in ids:
            ids.append(issue.id)
        cand.source_issue_ids = ids
        cand.score = int(cand.score or 0) + SCORE_REPEAT
        cand.updated_at = datetime.now(timezone.utc)
        db.flush()
        return cand

    cand = KnowledgeCandidate(
        question=issue.summary or issue.question,
        answer=answer,
        summary=issue.summary or issue.question,
        score=score,
        signals=signals,
        status="pending",
        source_issue_ids=[issue.id],
    )
    db.add(cand)
    db.flush()
    return cand


def approve_candidate(db: Session, candidate: KnowledgeCandidate, reviewer_id: str,
                      answer: str | None = None, question: str | None = None,
                      tags: list | None = None, owner_person_id: str | None = None) -> Faq:
    """确认沉淀:候选 → FAQ 条目。"""
    faq = Faq(
        question=(question or candidate.question).strip(),
        answer=(answer or candidate.answer).strip(),
        tags=tags or [],
        owner_person_id=owner_person_id,
        source="candidate",
        status="published",
        asked_count=len(candidate.source_issue_ids or []),
    )
    db.add(faq)
    db.flush()
    candidate.status = "approved"
    candidate.target_faq_id = faq.id
    candidate.reviewed_by = reviewer_id
    candidate.reviewed_at = datetime.now(timezone.utc)
    return faq
