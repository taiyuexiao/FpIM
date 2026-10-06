"""Agent 主链装配(V1.2 §3.1 基本形式;架构收敛:查/写双轨)。

AgentOrchestrator
  → IntentNode
  → QueryStructurerNode (仅 find_person)
  → ConceptLinkerNode   (仅 find_person)
  → StructuredRetrievalNode (仅 find_person;diagnostic/expert_finding 并联 KnowledgeRetrievalNode)
  → CandidateMergerNode
  → PeopleRankerNode
  → RelatedPeopleFallbackNode (主召回无结果时才执行有效逻辑)
  → ConfidenceGateNode
  → AnswerBuilderNode

架构收敛后:知识问答不再单独成链(KnowledgeQANode 已摘除),
知识类问题由意图层映射为 find_person/expert_finding 走双路检索,以名片作答。

统一双路(RETRIEVAL_ALWAYS_DUAL,默认开):查人一律「结构化 ∥ RAG」并联召回,
不再按 query_type 分单/双路——规则单路会漏掉「没打标签但发过相关文章」的人;
设 RETRIEVAL_ALWAYS_DUAL=0 可回退旧路由(应急回滚开关)。
"""
from __future__ import annotations

import os
import re

# 统一双路开关(默认开;=0 回退旧的按 query_type 分路)
ALWAYS_DUAL = os.getenv("RETRIEVAL_ALWAYS_DUAL", "1") == "1"

_EN_TERM = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[ ._\-][A-Za-z0-9]+)*")


def _has_retrieval_signal(s) -> bool:
    """无信号熔断:理解层什么词都没提出时不进检索(寒暄防 RAG 空跑)。

    任何词项都算信号(含保底正则抽出的英文词——真词/垃圾词在检索层用
    RAG_VECTOR_MIN_SIM 向量下限区分,不在此处截留,否则会误杀 HarnessEval
    这类未建概念的真实英文术语)。
    """
    u = s.understanding
    return bool(
        u.explicit_terms or u.mentioned_systems or u.objects or u.symptoms
        or u.mentioned_people or u.mentioned_departments or s.concept.resolved_concepts
    )
from app.agent.answer_builder import AnswerBuilderNode
from app.agent.concept_linker import ConceptLinkerNode
from app.agent.intent import IntentNode
from app.agent.nodes.knowledge_retrieval import KnowledgeRetrievalNode
from app.agent.nodes.ranking import (
    CandidateMergerNode, ConfidenceGateNode, PeopleRankerNode, RelatedPeopleFallbackNode,
)
from app.agent.nodes.structured_retrieval import StructuredRetrievalNode
from app.agent.orchestrator import AgentOrchestrator, ServiceRegistry
from app.agent.query_structurer import QueryStructurerNode
from app.contracts.agent_state import Intent, QueryType


def build_service_registry() -> ServiceRegistry:
    """装配默认 Service(真实实现;测试可注入 stub)。"""
    return ServiceRegistry()


def build_orchestrator(services: ServiceRegistry | None = None) -> AgentOrchestrator:
    """构建主链编排器。find_person 以外的意图在 AnswerBuilder 提前终态。"""
    orch = AgentOrchestrator(services or build_service_registry())
    orch.add(IntentNode())
    find_person = lambda s: s.intent.intent == Intent.FIND_PERSON  # noqa: E731
    dual_path = lambda s: (  # noqa: E731
        s.intent.intent == Intent.FIND_PERSON
        and s.intent.query_type in (QueryType.DIAGNOSTIC, QueryType.EXPERT_FINDING)
    )
    orch.add(QueryStructurerNode(), condition=find_person)
    orch.add(ConceptLinkerNode(), condition=find_person)
    if ALWAYS_DUAL:
        # 统一双路:所有查人问题「结构化 ∥ RAG」并联召回(防「只发文章没打标签」漏人)
        # 无信号熔断:理解层什么有效词都没提出(寒暄/乱码)时不进检索或相关人员兜底,
        # 防止给非找人问题随意配出名片。
        orch.add_parallel([StructuredRetrievalNode(), KnowledgeRetrievalNode()],
                          label="RetrievalCoordinator",
                          condition=lambda s: find_person(s) and _has_retrieval_signal(s))
    else:
        # 旧路由(回滚用):diagnostic/expert_finding 并联,其余结构化单路
        orch.add_parallel([StructuredRetrievalNode(), KnowledgeRetrievalNode()],
                          label="RetrievalCoordinator", condition=dual_path)
        orch.add(StructuredRetrievalNode(), condition=lambda s: find_person(s) and not dual_path(s))
    orch.add(CandidateMergerNode(), condition=find_person)
    orch.add(PeopleRankerNode(), condition=find_person)
    orch.add(RelatedPeopleFallbackNode(),
             condition=lambda s: find_person(s) and _has_retrieval_signal(s))
    orch.add(ConfidenceGateNode(), condition=find_person)
    orch.add(AnswerBuilderNode())
    return orch
