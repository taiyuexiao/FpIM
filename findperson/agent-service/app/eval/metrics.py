"""评测指标(V1.2 §16.2 节点级评测)。

不只评最终准确率。员工侧 RawTag→Concept 与查询侧 Query→Concept 分别统计;
每条错误可归因(§16.2 错误归因清单)。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CaseResult:
    """单条评测用例的运行结果。"""

    case_id: str
    query: str
    intent: str
    query_type: str | None
    # 预测
    predicted_intent: str = ""
    predicted_query_type: str | None = None
    resolved_concept_names: list[str] = field(default_factory=list)
    structured_person_ids: list[str] = field(default_factory=list)
    rag_document_ids: list[str] = field(default_factory=list)
    candidate_person_ids: list[str] = field(default_factory=list)
    ranked_person_ids: list[str] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)
    has_formal_top1: bool = False
    # gold
    gold_person_ids: list[str] = field(default_factory=list)
    gold_concept_names: list[str] = field(default_factory=list)
    gold_document_ids: list[str] = field(default_factory=list)
    # 归因
    error_attribution: str = ""


def recall_at_k(predicted: list, gold: list, k: int) -> float:
    """Recall@k:gold 中有多大比例被预测 Top-k 覆盖。"""
    if not gold:
        return 1.0
    top = set(predicted[:k])
    covered = len([g for g in gold if g in top])
    return covered / len(gold)


def hit_at_k(predicted: list, gold: list, k: int) -> float:
    """Hit@k:Top-k 中是否至少命中一个 gold(0/1)。"""
    if not gold:
        return 1.0
    return 1.0 if set(predicted[:k]) & set(gold) else 0.0


class MetricsAccumulator:
    """节点级指标累计器(§16.2)。"""

    def __init__(self) -> None:
        self.results: list[CaseResult] = []

    def add(self, result: CaseResult) -> None:
        self.results.append(result)

    def summary(self) -> dict:
        """汇总全部节点级指标。"""
        rs = self.results
        n = len(rs)
        if n == 0:
            return {}
        fp = [r for r in rs if r.intent == "find_person"]
        qa = [r for r in rs if r.intent == "knowledge_qa"]

        def avg(values) -> float:
            values = list(values)
            return round(sum(values) / len(values), 4) if values else 0.0

        return {
            "cases": n,
            "Intent Accuracy": avg(r.predicted_intent == r.intent for r in rs),
            "QueryType Accuracy": avg(
                r.predicted_query_type == r.query_type for r in fp),
            "Query→Concept Recall@3": avg(
                recall_at_k(r.resolved_concept_names, r.gold_concept_names, 3)
                for r in fp if r.gold_concept_names),
            "Structured Recall@3": avg(
                hit_at_k(r.structured_person_ids, r.gold_person_ids, 3)
                for r in fp if r.gold_person_ids),
            "RAG Recall@5": avg(
                hit_at_k(r.rag_document_ids, r.gold_document_ids, 5)
                for r in qa if r.gold_document_ids),
            "Candidate Recall@5": avg(
                hit_at_k(r.candidate_person_ids, r.gold_person_ids, 5)
                for r in fp if r.gold_person_ids),
            "Final Top1": avg(
                hit_at_k(r.ranked_person_ids, r.gold_person_ids, 1)
                for r in fp if r.gold_person_ids),
            "Final Recall@3": avg(
                hit_at_k(r.ranked_person_ids, r.gold_person_ids, 3)
                for r in fp if r.gold_person_ids),
            "OKF Citation Coverage": avg(
                bool(r.citations) for r in qa if r.rag_document_ids),
            "Error Attribution": self._attribution_counts(),
        }

    def _attribution_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self.results:
            if r.error_attribution:
                counts[r.error_attribution] = counts.get(r.error_attribution, 0) + 1
        return counts


def attribute_error(r: CaseResult) -> str:
    """错误归因(§16.2):失败案例定位到第一个出错节点。"""
    if r.intent == "find_person":
        if r.predicted_intent != r.intent:
            return "intent_error"
        if r.predicted_query_type != r.query_type:
            return "query_type_error"
        if r.gold_concept_names and not set(r.resolved_concept_names) & set(r.gold_concept_names):
            return "query_concept_error"
        if r.gold_person_ids:
            if not set(r.structured_person_ids) & set(r.gold_person_ids) \
               and not set(r.ranked_person_ids) & set(r.gold_person_ids):
                return "structured_recall_error"
            if not set(r.candidate_person_ids) & set(r.gold_person_ids) \
               and not set(r.ranked_person_ids) & set(r.gold_person_ids):
                return "merge_error"
            if not set(r.ranked_person_ids) & set(r.gold_person_ids):
                return "ranking_error"
    else:
        if r.predicted_intent != r.intent:
            return "intent_error"
        if r.gold_document_ids and not set(r.rag_document_ids) & set(r.gold_document_ids):
            return "rag_recall_error"
    return ""
