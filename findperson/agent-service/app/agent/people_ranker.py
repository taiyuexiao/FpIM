"""PeopleRanker(V1.2 §12.3)+ ConfidenceGate(§12.4)。

不使用一套全局排序逻辑处理所有找人问题,根据 query_type 选择 RankPolicy。
排序是确定性的:Hermes 不能重排 PeopleRanker 输出(§12.3 验收)。

ConfidenceGate 判断 Top1 可信度,输出 answer / clarify / no_result / degraded_answer。
"""
from __future__ import annotations

import re

from app.agent.candidate_merger import MergedPersonCandidate
from app.contracts.agent_state import ConfidenceDecision, QueryType
from app.contracts.evidence import EvidenceType

# 证据语义的基础权重(供各 policy 组合;不是全局唯一排序公式)
EVIDENCE_BASE_WEIGHT = {
    EvidenceType.FORMAL_ASSIGNMENT: 1.0,
    EvidenceType.EXPLICIT_SELF_TAG: 0.8,
    EvidenceType.INFERRED_FROM_PROFILE: 0.6,
    EvidenceType.INFERRED_FROM_REVIEW: 0.5,
    EvidenceType.INFERRED_FROM_ARTICLE: 0.45,
    EvidenceType.DIRECTORY_MATCH: 0.9,
}

# 匹配层级修正(§9.3:细分层精确 > 概念层泛化)
MATCH_LEVEL_FACTOR = {"leaf_exact": 1.0, "concept_generalized": 0.7}


def _keyword_bonus(text: str | None, query: str) -> float:
    """查询词与证据来源文本的匹配奖励(区分同一概念下不同职责)。"""
    if not text or not query:
        return 0.0
    text = text.lower()
    query = query.lower()
    # 生成 query 的 2-gram/3-gram,去掉纯标点和空格的
    grams: set[str] = set()
    for n in (2, 3):
        for i in range(len(query) - n + 1):
            g = query[i:i + n]
            if any('\u4e00' <= c <= '\u9fff' for c in g):
                grams.add(g)
    if not grams:
        return 0.0
    matched = sum(1 for g in grams if g in text)
    bonus = min(0.3, (matched / len(grams)) * 0.5) if grams else 0.0
    # ASCII 技术词(HiAgent/HarnessEval/Agent Tracing…):原文命中给强相关奖励。
    # 纯英文术语不含 CJK 字符,上面的 2/3-gram 生成器会完全跳过,
    # 导致「文章标题精确含查询术语」这一最强信号零贡献(实测 HarnessEval case)
    ascii_terms = [t for t in re.findall(r"[a-z][a-z0-9]*(?: [a-z0-9]+)*", query)
                   if len(t) >= 2]
    if ascii_terms:
        hits = sum(1 for t in ascii_terms if t in text)
        bonus = max(bonus, min(0.3, (hits / len(ascii_terms)) * 0.3))
    return bonus


def _evidence_score(ev: dict, query: str = "") -> float:
    """单条证据的确定性得分:语义权重 × 匹配置信 × 层级修正 + 查询匹配奖励。"""
    base = EVIDENCE_BASE_WEIGHT.get(EvidenceType(ev["evidence_type"]), 0.3)
    conf = float(ev.get("confidence") or 0.0)
    factor = MATCH_LEVEL_FACTOR.get((ev.get("detail") or {}).get("match_level", ""), 1.0)
    score = base * conf * factor
    # query-aware 奖励:自填标签/画像/文章标题与查询关键词越相关,得分越高。
    # 专家发现场景尤其依赖文章关键词匹配;诊断场景主要由 self_tag/profile 驱动。
    detail = ev.get("detail") or {}
    if ev["evidence_type"] == EvidenceType.EXPLICIT_SELF_TAG.value:
        score += _keyword_bonus(detail.get("source_raw_tag"), query)
    elif ev["evidence_type"] in (EvidenceType.INFERRED_FROM_PROFILE.value,
                                 EvidenceType.INFERRED_FROM_ARTICLE.value):
        score += _keyword_bonus(detail.get("title_hint") or detail.get("document_id"), query)
    return score


def _aggregate(candidate: MergedPersonCandidate, policy: str, query: str = "") -> float:
    """按 policy 聚合候选人得分(确定性,可解释)。"""
    scores = [(e, _evidence_score(e.model_dump(), query)) for e in candidate.evidences]
    by_type: dict[EvidenceType, float] = {}
    for e, s in scores:
        by_type[e.evidence_type] = max(by_type.get(e.evidence_type, 0.0), s)

    if policy == "responsibility_policy":
        # 正式责任 > 精确自填 > 宽泛自填 > 画像 > 评价 > 文章(§12.3)
        if candidate.has_formal:
            return 10.0 + by_type.get(EvidenceType.EXPLICIT_SELF_TAG, 0.0)
        return (by_type.get(EvidenceType.EXPLICIT_SELF_TAG, 0.0) * 1.0
                + by_type.get(EvidenceType.INFERRED_FROM_PROFILE, 0.0) * 0.5
                + by_type.get(EvidenceType.INFERRED_FROM_REVIEW, 0.0) * 0.4
                + by_type.get(EvidenceType.INFERRED_FROM_ARTICLE, 0.0) * 0.3)
    if policy == "diagnostic_policy":
        # 症状责任域:正式责任与精确职责优先,泛化与画像辅助;
        # 文章证据计入——排障类文档(运维治理/调优实践)是症状找人最直接的经验证据,
        # 不含此项时诊断策略会把文章命中者整体打成 0 分(实测「集群报警」案例)
        return (by_type.get(EvidenceType.FORMAL_ASSIGNMENT, 0.0) * 1.0
                + by_type.get(EvidenceType.EXPLICIT_SELF_TAG, 0.0) * 0.9
                + by_type.get(EvidenceType.INFERRED_FROM_ARTICLE, 0.0) * 0.5
                + by_type.get(EvidenceType.INFERRED_FROM_PROFILE, 0.0) * 0.5
                + by_type.get(EvidenceType.INFERRED_FROM_REVIEW, 0.0) * 0.4)
    if policy == "expert_policy":
        # 专家:领域自填 + 项目/画像实践 + 高相关文章 + 同行评价(§12.3)
        return (by_type.get(EvidenceType.EXPLICIT_SELF_TAG, 0.0) * 1.0
                + by_type.get(EvidenceType.INFERRED_FROM_PROFILE, 0.0) * 0.8
                + by_type.get(EvidenceType.INFERRED_FROM_ARTICLE, 0.0) * 0.7
                + by_type.get(EvidenceType.INFERRED_FROM_REVIEW, 0.0) * 0.6
                + by_type.get(EvidenceType.FORMAL_ASSIGNMENT, 0.0) * 0.3)
    # directory_policy:仅身份唯一性与范围校验,得分无意义
    return by_type.get(EvidenceType.DIRECTORY_MATCH, 0.0)


POLICY_BY_QUERY_TYPE = {
    QueryType.EXPLICIT_RESPONSIBILITY: "responsibility_policy",
    QueryType.DIAGNOSTIC: "diagnostic_policy",
    QueryType.EXPERT_FINDING: "expert_policy",
    QueryType.CONTACT_LOOKUP: "directory_policy",
}


class PeopleRanker:
    """按 query_type 选择 RankPolicy 的确定性排序器。"""

    def rank(
        self, candidates: list[MergedPersonCandidate], query_type: QueryType | None,
        *, query: str = "",
        feedback_adjust: dict[str, float] | None = None,
    ) -> tuple[list[dict], str, float]:
        """返回 (ranked_list, policy, top1_confidence)。

        feedback_adjust:用户反馈回流微调({person_id: ±weight}),
        只调整不产生/消除候选人(§12.3:候选仍由检索证据决定)。
        """
        policy = POLICY_BY_QUERY_TYPE.get(query_type, "expert_policy")
        adjust = feedback_adjust or {}
        ranked = []
        for c in candidates:
            if c.person_id == "__department_responsibility__":
                continue  # 部门级责任不进入人员排名,由 AnswerBuilder 单独呈现
            score = _aggregate(c, policy, query)
            fb = adjust.get(c.person_id, 0.0)
            ranked.append({
                "person_id": c.person_id,
                "score": round(score + fb, 4),
                "feedback_adjust": fb,
                "has_formal": c.has_formal,
                "evidence_count": len(c.evidences),
                "evidences": [e.model_dump() for e in c.evidences],
                "responsibilities": c.responsibilities,
            })
        ranked.sort(key=lambda r: (-r["score"], r["person_id"]))
        top1 = ranked[0]["score"] if ranked else 0.0
        return ranked, policy, top1


class ConfidenceGate:
    """置信度闸门(§12.4)。"""

    def decide(
        self,
        ranked: list[dict],
        *,
        concept_ambiguous: bool = False,
        degraded: bool = False,
        resolved_concepts: list[dict] | None = None,
        min_score: float = 0.05,  # 与名片达标线对齐:噪声由检索层挡(向量下限+信号熔断+泛词停用),
                                  # 门只判「有无证据支撑的候选」;弱行为证据以领域专家/相关参与者身份诚实呈现
        min_gap: float = 0.05,
    ) -> ConfidenceDecision:
        """按 Top1 得分/Top1-Top2 差距/正式证据/概念歧义/降级状态判定。"""
        if not ranked:
            return ConfidenceDecision.NO_RESULT
        top1 = ranked[0]
        if degraded:
            return ConfidenceDecision.DEGRADED_ANSWER
        if concept_ambiguous:
            return ConfidenceDecision.CLARIFY
        if top1["score"] < min_score and not top1["has_formal"]:
            return ConfidenceDecision.NO_RESULT
        # 兜底候选已经由大模型按相关性筛选并限制为 1～3 人。
        # 它们本来就是“无完全匹配时的可能相关人选”，不应再因分数接近
        # 被普通候选的歧义规则打回澄清或无结果。
        if top1.get("is_related_fallback"):
            return ConfidenceDecision.ANSWER
        # Top1/Top2 差距过小且双方均无正式证据 → 澄清;
        # 但双方命中同一 Concept(同领域并列人选)不属于需要用户澄清的歧义,应并列返回;
        # 仅在 Top1 本身够强(≥0.3)时才谈「歧义澄清」——全是弱行为证据时,
        # 给诚实线索(领域专家/相关参与者名片)比追问「能否补充条件」更有用(实测「集群报警」)
        if len(ranked) > 1 and top1["score"] >= 0.3:
            gap = top1["score"] - ranked[1]["score"]
            if gap < min_gap and not (top1["has_formal"] or ranked[1]["has_formal"]):
                if not _share_same_concept(top1, ranked[1], resolved_concepts):
                    return ConfidenceDecision.CLARIFY
        return ConfidenceDecision.ANSWER


def _share_same_concept(a: dict, b: dict, resolved_concepts: list[dict] | None = None) -> bool:
    """两个候选是否命中同一 Concept,或同属本轮并列归一的概念组(并列人选,而非歧义)。"""
    ca = {e.get("concept_id") for e in a.get("evidences", []) if e.get("concept_id")}
    cb = {e.get("concept_id") for e in b.get("evidences", []) if e.get("concept_id")}
    if ca & cb:
        return True
    # 同属并列归一概念组(如「集群」并列命中三个集群类概念→各标签持有者是并列人选)
    resolved_ids = {c.get("concept_id") for c in (resolved_concepts or [])}
    if resolved_ids and ca and cb and ca <= resolved_ids and cb <= resolved_ids:
        return True
    return False
