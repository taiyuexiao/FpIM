"""AnswerBuilder(V1.2 §13.1)。

Hermes/模板只负责自然语言组织。回答强制分「检索到的事实 / 建议」;
人员标注身份(正式责任人/明确负责领域命中者/相关参与者/能力候选人/领域专家)。
不得:新增 PeopleRanker 未返回人员、修改顺序、将文章作者描述成正式负责人。

V1 实现为确定性模板(离线可测、天然满足「不新增/不重排」);
LLM 润色留作后续可选项,不改变事实与顺序。
"""
from __future__ import annotations

from app.agent.orchestrator import AgentNode, ServiceRegistry
from app.contracts.agent_state import (
    AgentState, ConfidenceDecision, Intent, QueryType, ResponseState, StateUpdate,
)
from app.contracts.evidence import EvidenceType
from app.core import db

# 身份标签(§13.1)
IDENTITY_FORMAL = "正式责任人"
IDENTITY_LEAF = "明确负责领域命中者"
IDENTITY_RELATED = "相关参与者"
IDENTITY_EXPERT = "领域专家"
IDENTITY_CANDIDATE = "能力候选人"

# 事实部分最多呈现的候选人数
MAX_FACT_CANDIDATES = 5
# 推荐卡片:宁缺毋滥——仅分数过线的达标者出卡,最多 3 张(1-2 个达标就 1-2 张)
CARD_SCORE_FLOOR = 0.05
MAX_CARDS = 3


def _identity_of(candidate: dict) -> str:
    """按证据语义定身份标签(不得把文章作者标成正式责任人)。"""
    if candidate.get("has_formal"):
        return IDENTITY_FORMAL
    levels = {(e.get("detail") or {}).get("match_level") for e in candidate.get("evidences", [])}
    types = {e.get("evidence_type") for e in candidate.get("evidences", [])}
    if "leaf_exact" in levels:
        return IDENTITY_LEAF
    if EvidenceType.INFERRED_FROM_ARTICLE.value in types:
        return IDENTITY_EXPERT
    if EvidenceType.INFERRED_FROM_PROFILE.value in types:
        return IDENTITY_CANDIDATE
    return IDENTITY_RELATED


class AnswerBuilder:
    """回答组织器(确定性模板)。"""

    async def build(self, state: AgentState) -> ResponseState:
        response = ResponseState()
        decision = state.ranking.gate_decision or ConfidenceDecision.ANSWER
        ranked = state.ranking.ranked_candidates
        names = await self._load_names([c["person_id"] for c in ranked])

        if decision == ConfidenceDecision.NO_RESULT:
            # 空结果不编造(§18)
            response.facts = ["没有找到与您的问题匹配的责任人或专家。"]
            response.suggestions = ["可以尝试换个说法,例如补充系统名称、领域关键词;",
                                    "也可以在个人名片中完善“负责领域”信息。"]
            response.final_answer = self._render(response)
            return response
        if decision == ConfidenceDecision.CLARIFY:
            response.clarification = self._build_clarification(state)
            response.final_answer = response.clarification
            return response

        # answer / degraded_answer
        qt = state.intent.query_type
        if qt == QueryType.CONTACT_LOOKUP:
            self._build_contact_facts(state, ranked, names, response)
        else:
            self._build_person_facts(ranked, names, response)
        # 架构收敛:知识类问题(已并入 expert_finding)命中的内容证据标注来源,
        # 以名片为锚作答,详细内容见名片「相关发布内容」
        if state.retrieval.rag_documents:
            response.citations = [{
                "document_id": h["document_id"], "chunk_id": h["chunk_id"],
                "version": h["version"], "source_uri": h["source_uri"],
            } for h in state.retrieval.rag_documents[:3]]
        self._build_suggestions(state, ranked, response)
        response.recommendation_cards = self._build_cards(ranked, names)
        related_fallback = any(c.get("is_related_fallback") for c in ranked)
        if related_fallback:
            response.final_answer = response.facts[0]
            return response
        fact_heading = ("【检索到的事实】" if qt == QueryType.CONTACT_LOOKUP
                        else "为你推荐以下负责人")
        response.final_answer = self._render(
            response,
            degraded=(decision == ConfidenceDecision.DEGRADED_ANSWER),
            fact_heading=fact_heading,
        )
        return response

    # ---------------- 事实组织 ----------------

    def _build_contact_facts(self, state, ranked, names, response) -> None:
        for c in ranked:
            for e in c.get("evidences", []):
                d = e.get("detail") or {}
                if d.get("name"):
                    response.facts.append(
                        f"{d['name']}({d.get('department','')}/{d.get('role','')}),"
                        f"联系方式:{d.get('contact') or '未登记'}。"
                    )

    def _build_person_facts(self, ranked, names, response) -> None:
        related_fallback = any(c.get("is_related_fallback") for c in ranked)
        if related_fallback:
            response.facts.append("未找到与问题完全匹配的正式责任人或专家，以下是可能相关的老师。")
            return
        for c in ranked[:MAX_FACT_CANDIDATES]:  # 事实只呈现 Top N,避免刷屏
            pid = c["person_id"]
            identity = _identity_of(c)
            name = names.get(pid, pid)
            if identity == IDENTITY_FORMAL and c.get("responsibilities"):
                rec = c["responsibilities"][0]
                response.facts.append(
                    f"{name} 是【{rec['title']}】的{identity}(责任部门:{rec.get('owner_department','')},"
                    f"时限:{rec.get('time_limit','')},升级路径:{rec.get('escalation_path','')})。"
                )
            else:
                raw_tags = [((e.get("detail") or {}).get("source_raw_tag") or "")
                            for e in c.get("evidences", [])]
                raw_tags = [t for t in raw_tags if t]
                tag_txt = f",负责领域:{ '、'.join(raw_tags[:3]) }" if raw_tags else ""
                response.facts.append(f"{name} 是{identity}{tag_txt}。")

    def _build_suggestions(self, state, ranked, response) -> None:
        decision = state.ranking.gate_decision
        if any(c.get("is_related_fallback") for c in ranked):
            return
        if decision == ConfidenceDecision.DEGRADED_ANSWER:
            response.suggestions.append(
                "本次结果部分来自降级路径(如知识服务不可用时的业务直读),建议稍后复核。")
        qt = state.intent.query_type
        if qt == QueryType.DIAGNOSTIC and ranked:
            response.suggestions.append("如首要责任人无法解决,可按升级路径逐级上报。")
        elif qt == QueryType.EXPERT_FINDING and ranked:
            top = ranked[0]["person_id"]
            response.suggestions.append("可以通过查看其发表的文章进一步了解其专业深度。")
            if state.retrieval.rag_documents:
                response.suggestions.append("相关已发布内容见名片「相关发布内容」,来源见引用。")
        elif qt == QueryType.EXPLICIT_RESPONSIBILITY:
            if not any(c.get("has_formal") for c in ranked):
                response.suggestions.append(
                    "当前未查到该领域的正式责任登记,以上基于人员自填负责领域,建议向部门负责人确认。")

    def _build_clarification(self, state: AgentState) -> str:
        if state.intent.clarify_question:
            return state.intent.clarify_question
        if state.concept.ambiguous:
            terms = [t["term"] for t in state.concept.concept_link_trace]
            return (f"您提到的「{'、'.join(terms[:3])}」可能存在多种理解,"
                    f"能具体说明是哪方面的业务或系统吗?")
        return "找到多位可能相关的人员,能否补充更多条件(如具体系统、部门)?"

    def _build_cards(self, ranked, names) -> list[dict]:
        cards = []
        for c in [c for c in ranked if c["score"] >= CARD_SCORE_FLOOR][:MAX_CARDS]:
            pid = c["person_id"]
            cards.append({
                "person_id": pid,
                "name": names.get(pid, pid),
                "identity": _identity_of(c),
                "score": c["score"],
                "responsibilities": c.get("responsibilities", []),
                "evidence_count": c["evidence_count"],
            })
        return cards

    async def _load_names(self, person_ids: list[str]) -> dict[str, str]:
        if not person_ids:
            return {}
        rows = await db.fetch(
            "SELECT id, name FROM public.people WHERE id = ANY($1)", person_ids)
        return {r["id"]: r["name"] for r in rows}

    def _render(self, response: ResponseState, *, degraded: bool = False,
                fact_heading: str = "【检索到的事实】") -> str:
        parts = []
        if response.facts:
            parts.append(fact_heading + "\n" + "\n".join(response.facts))
        if response.suggestions:
            parts.append("【建议】\n" + "\n".join(response.suggestions))
        if degraded:
            parts.append("(本回答包含降级路径结果)")
        return "\n\n".join(parts)


class AnswerBuilderNode(AgentNode):
    """回答生成节点。find_person 走完整组织;unclear/edit 走提前终态(架构收敛:chat/QA 不再单独成支)。"""

    name = "AnswerBuilderNode"
    timeout_ms = 8000
    on_error = "degrade"

    async def execute(self, state: AgentState, services: ServiceRegistry) -> StateUpdate:
        builder = services.get("answer_builder") if "answer_builder" in services.services else AnswerBuilder()
        update = StateUpdate()

        if state.intent.intent == Intent.UNCLEAR or state.intent.needs_clarification:
            # 架构收敛:不再闲聊,兜底统一为找人类引导
            update.response = ResponseState(
                clarification=(state.intent.clarify_question
                               or "我可以帮你找负责人,试试『谁负责XX』『XX问题找谁』。"))
            update.response.final_answer = update.response.clarification
            update.terminate = True
            return update
        if state.intent.intent == Intent.EDIT:
            # 写操作:产出 confirmation_card 草稿(资料维护/他人画像/内容发布,§实施方案v3 §3.3)
            # Agent 不写业务表;确认后由前端确认链路调业务后端 API 执行。
            from app.agent.action_drafts import ActionDraftService
            service = (services.get("action_drafts")
                       if "action_drafts" in services.services else ActionDraftService())
            query = state.request.normalized_query or state.request.original_query
            result = await service.build(query, state.request.user_context,
                                         run_id=state.request.run_id,
                                         history=state.request.history)
            update.response = ResponseState(final_answer=result.reply_text,
                                            confirmation_card=result.card)
            if result.degraded:
                update.degraded = True
            update.terminate = True
            return update
        # 架构收敛:KNOWLEDGE_QA 意图已废弃,意图层会映射为 find_person/expert_finding;
        # 历史 trace 重放若带出该意图,直接落入下方查人组织逻辑
        update.response = await builder.build(state)
        return update
