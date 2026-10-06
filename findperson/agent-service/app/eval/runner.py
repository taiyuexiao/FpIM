"""Evaluation Runner(V1.2 §16.1 / §16.3)。

一条命令运行全量评测,输出节点级指标、最终指标、错误样本与 Baseline 对照。

Baseline(§16.3):
  A Structured Only       — 只走 TagMatcher 结构化召回
  B RAG Only              — 只走 RAG 人员证据
  C Structured+RAG+Ranker — 双路融合排序
  D Agent 全链            — 完整编排(stub 意图为 gold 意图,评意图后全链;
                            真实 LLM 意图准确率用 REAL_LLM=1 单独评)
  E Concept Ablation      — RawTag 字符串匹配 vs Concept 对齐(§16.3)

开发只能使用 dev 集调规则和 Prompt;test 集冻结(§16.1)。
"""
from __future__ import annotations

import json
from pathlib import Path

from app.agent.candidate_merger import CandidateMerger
from app.agent.chain import build_orchestrator
from app.agent.concept_linker import QueryConceptLinker
from app.agent.orchestrator import ServiceRegistry
from app.agent.people_ranker import PeopleRanker
from app.agent.query_structurer import QueryStructurerService
from app.contracts.agent_state import (
    AgentState, Intent, IntentState, QueryType, RequestState,
    UnderstandingState, UserContext,
)
from app.core import db
from app.eval.metrics import CaseResult, MetricsAccumulator, attribute_error
from app.rag.retriever import HybridRetriever
from app.rag.evidence_adapter import RagEvidenceAdapter
from app.retrieval.tag_matcher import TagMatcher

EVAL_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "eval"


def load_cases(split: str = "dev") -> list[dict]:
    """加载评测集。split ∈ {dev, test};调参只允许 dev(§16.1)。"""
    path = EVAL_DIR / f"{split}.json"
    return json.loads(path.read_text(encoding="utf-8"))


class _GoldIntentStructurer(QueryStructurerService):
    """评测专用:意图与问题结构化确定性化(绕过 LLM,意图准确率单独评)。

    概念链接输入 = gold 概念名;contact_lookup 用例补 mentioned_people(gold 人名)。
    """

    def __init__(self, case: dict) -> None:
        self._case = case

    async def structure(self, query: str) -> UnderstandingState:
        u = UnderstandingState()
        names = self._case["gold"].get("concept_names", [])
        u.mentioned_systems = list(names)
        u.explicit_terms = list(names)
        u.field_sources = {f"systems:{n}": "explicit" for n in names}
        # contact_lookup:从 gold person_ids 反查人名作显式提及(DirectorySearch 输入)
        if self._case["query_type"] == "contact_lookup":
            person_ids = self._case["gold"].get("person_ids", [])
            if person_ids:
                rows = await db.fetch(
                    "SELECT name FROM public.people WHERE id = ANY($1)", person_ids)
                u.mentioned_people = [r["name"] for r in rows]
        return u


class _GoldIntentService:
    def __init__(self, case: dict) -> None:
        self._case = case

    async def classify(self, query: str):
        from app.contracts.agent_state import IntentState
        return IntentState(
            intent=Intent(self._case["intent"]),
            query_type=QueryType(self._case["query_type"]) if self._case["query_type"] else None,
            confidence=1.0,
        )


class EvaluationRunner:
    """评测运行器。"""

    def __init__(self) -> None:
        self._linker = QueryConceptLinker()
        self._matcher = TagMatcher()
        self._retriever = HybridRetriever()
        self._merger = CandidateMerger()
        self._ranker = PeopleRanker()
        self._adapter = RagEvidenceAdapter()

    # ---------------- 全链(Baseline D)----------------

    async def run_chain(self, case: dict) -> CaseResult:
        """完整编排(意图用 gold 意图注入,评意图后全链路)。"""
        services = ServiceRegistry({
            "intent_service": _GoldIntentService(case),
            "query_structurer": _GoldIntentStructurer(case),
        })
        orch = build_orchestrator(services)
        state = AgentState(
            request=RequestState(
                trace_id=f"eval-{case['id']}", run_id="eval",
                user_context=UserContext(user_id="p-0001", name="评测"),
                original_query=case["query"], normalized_query=case["query"],
            )
        )
        final = await orch.run(state)
        return self._to_result(case, final=final)

    # ---------------- Baseline A/B/C ----------------

    async def run_structured_only(self, case: dict) -> CaseResult:
        """Baseline A:只走概念对齐 + TagMatcher。"""
        concept_names = case["gold"].get("concept_names", [])
        concept_state = await self._linker.link(concept_names, query=case["query"])
        evidences, _ = await self._matcher.match(concept_state.resolved_concepts, expand=False)
        person_ids = [e.person_id for e in evidences]
        result = self._to_result(case)
        result.resolved_concept_names = [c["canonical_name"] for c in concept_state.resolved_concepts]
        result.structured_person_ids = person_ids
        result.candidate_person_ids = person_ids
        result.ranked_person_ids = person_ids  # 无排序,直接按证据顺序
        result.error_attribution = attribute_error(result)
        return result

    async def run_rag_only(self, case: dict) -> CaseResult:
        """Baseline B:只走 RAG 人员证据。"""
        ctx = UserContext(user_id="p-0001", name="评测")
        hits = await self._retriever.retrieve(case["query"], ctx, top_k=5)
        evidences = self._adapter.to_person_evidence(hits)
        person_ids = [e.person_id for e in evidences]
        result = self._to_result(case)
        result.rag_document_ids = [h.document_id for h in hits]
        result.ranked_person_ids = person_ids
        result.error_attribution = attribute_error(result)
        return result

    async def run_hybrid(self, case: dict) -> CaseResult:
        """Hybrid C:Structured + RAG + Ranker(无 Hermes 解释层)。"""
        from app.contracts.evidence import EvidenceType, PersonEvidence
        a = await self.run_structured_only(case)
        b = await self.run_rag_only(case)
        structured_evs = [
            PersonEvidence(
                person_id=pid, relation_type="self_declared_scope",
                evidence_type=EvidenceType.EXPLICIT_SELF_TAG,
                source_type="raw_tag", confidence=1.0,
                detail={"match_level": "leaf_exact"},
            ).model_dump()
            for pid in a.structured_person_ids
        ]
        ctx = UserContext(user_id="p-0001", name="评测")
        hits = await self._retriever.retrieve(case["query"], ctx, top_k=5)
        rag_evs = [e.model_dump() for e in self._adapter.to_person_evidence(hits)]
        merged = self._merger.merge(structured_evs, rag_evs, [])
        qt = QueryType(case["query_type"]) if case["query_type"] else None
        ranked, _, _ = self._ranker.rank(merged, qt)
        result = self._to_result(case)
        result.resolved_concept_names = a.resolved_concept_names
        result.structured_person_ids = a.structured_person_ids
        result.rag_document_ids = b.rag_document_ids
        result.candidate_person_ids = [c.person_id for c in merged]
        result.ranked_person_ids = [r["person_id"] for r in ranked]
        result.error_attribution = attribute_error(result)
        return result

    # ---------------- Concept Ablation(Baseline E)----------------

    async def run_string_match_only(self, case: dict) -> CaseResult:
        """Ablation E:RawTag 字符串直接匹配(无 Concept 中间层)。"""
        names = case["gold"].get("concept_names", [])
        person_ids: list[str] = []
        for name in names:
            rows = await db.fetch(
                "SELECT DISTINCT pt.person_id FROM agent.person_tags pt"
                " JOIN agent.raw_tags rt ON rt.tag_id = pt.tag_id"
                " WHERE pt.is_active AND rt.normalized_text LIKE $1 LIMIT 20",
                f"%{name.lower()}%")
            person_ids.extend(r["person_id"] for r in rows)
        result = self._to_result(case)
        result.ranked_person_ids = list(dict.fromkeys(person_ids))
        result.error_attribution = attribute_error(result)
        return result

    # ---------------- 汇总 ----------------

    def _to_result(self, case: dict, final: AgentState | None = None) -> CaseResult:
        r = CaseResult(
            case_id=case["id"], query=case["query"],
            intent=case["intent"], query_type=case["query_type"],
            gold_person_ids=case["gold"].get("person_ids", []),
            gold_concept_names=case["gold"].get("concept_names", []),
            gold_document_ids=case["gold"].get("document_ids", []),
        )
        if final is not None:
            r.predicted_intent = final.intent.intent.value if final.intent.intent else ""
            r.predicted_query_type = final.intent.query_type.value if final.intent.query_type else None
            r.resolved_concept_names = [c.get("canonical_name", "") for c in final.concept.resolved_concepts]
            r.structured_person_ids = [e["person_id"] for e in final.retrieval.structured_candidates]
            r.rag_document_ids = [h["document_id"] for h in final.retrieval.rag_documents]
            r.candidate_person_ids = [c["person_id"] for c in final.ranking.merged_candidates]
            r.ranked_person_ids = [c["person_id"] for c in final.ranking.ranked_candidates]
            r.citations = final.response.citations
            if final.ranking.ranked_candidates:
                r.has_formal_top1 = final.ranking.ranked_candidates[0].get("has_formal", False)
            r.error_attribution = attribute_error(r)
        else:
            r.predicted_intent = r.intent
            r.predicted_query_type = r.query_type
        return r


async def run_evaluation(split: str = "dev", *, baselines: tuple[str, ...] = ("D",)) -> dict:
    """一条命令跑全量评测(§16.1 验收)。"""
    runner = EvaluationRunner()
    cases = load_cases(split)
    output: dict = {"split": split, "baselines": {}}
    for baseline in baselines:
        acc = MetricsAccumulator()
        for case in cases:
            if baseline == "A":
                result = await runner.run_structured_only(case)
            elif baseline == "B":
                result = await runner.run_rag_only(case)
            elif baseline == "C":
                result = await runner.run_hybrid(case)
            elif baseline == "E":
                result = await runner.run_string_match_only(case)
            else:
                result = await runner.run_chain(case)
            acc.add(result)
        output["baselines"][baseline] = {
            "metrics": acc.summary(),
            "failed_cases": [
                {"id": r.case_id, "query": r.query, "attribution": r.error_attribution}
                for r in acc.results if r.error_attribution
            ],
        }
    return output
