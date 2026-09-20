"""AGUI 运行服务:执行 Agent 主链并产出前端可消费的事件序列。

事件契约(与前端 src/services/agui/normalizer.js + stores/agui.js 对齐):
- 每个事件都是单行 JSON(SSE data:),含 type/sessionId/runId/messageId;
- run_started 带 result.analysis(意图分析);
- text_delta/text_finished 流式文本;
- recommendation_cards(找人)/ confirmation_card(写操作)二选一;
- state_delta 更新会话标题/摘要/轮次;run_finished 收尾;run_error 兜底。

推荐理由必须指出命中依据(正式责任/领域/画像/内容),不显示"匹配度高"(v4 §四)。
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from app.agent.chain import build_orchestrator
from app.agent.memory import load_history
from app.contracts.agent_state import AgentState, RequestState, UserContext
from app.contracts.trace import new_trace_id
from app.core import db
from app.core.observability import get_metrics, persist_trace

RANK_LABELS = ["首推", "可协助", "相关人员"]
MAX_CARDS = 3  # 宁缺毋滥:最多 3 张名片
CARD_SCORE_FLOOR = 0.05  # 达标线:仅分数过线者出卡(与 answer_builder 同规则)


def _event(event_type: str, ids: dict, **data: Any) -> dict:
    """统一事件封装:type + 三个归属 ID(v3 §3.3:事件按 sessionId/runId/messageId 归属)。"""
    return {"type": event_type, **ids, **data}


class AguiService:
    """AGUI 会话与运行服务。"""

    # ---------------- 会话 ----------------

    async def create_session(self, user_id: str, title: str = "新对话") -> dict:
        session_id = f"session-{uuid.uuid4().hex[:12]}"
        state = {"title": title, "summary": "", "turnCount": 0}
        await db.execute(
            "INSERT INTO agent.agent_sessions(session_id, user_id, state) VALUES($1,$2,$3)",
            session_id, user_id, json.dumps(state, ensure_ascii=False),
        )
        return {"sessionId": session_id, **state}

    async def get_state(self, session_id: str) -> dict | None:
        row = await db.fetchrow(
            "SELECT session_id, user_id, state FROM agent.agent_sessions WHERE session_id=$1",
            session_id)
        if not row:
            return None
        state = row["state"]
        if isinstance(state, str):
            state = json.loads(state)
        msgs = await db.fetch(
            "SELECT message_id, role, text, analysis, cards FROM agent.agui_messages"
            " WHERE session_id=$1 ORDER BY id",
            session_id)
        return {
            "sessionId": row["session_id"],
            **{k: state.get(k) for k in ("title", "summary", "turnCount")},
            "messages": [{
                "id": m["message_id"], "role": m["role"], "text": m["text"],
                "analysis": _loads(m["analysis"]), "cards": _loads(m["cards"]),
            } for m in msgs],
        }

    async def _patch_session(self, session_id: str, *, title: str, summary: str) -> None:
        await db.execute(
            "UPDATE agent.agent_sessions"
            " SET state = jsonb_set(jsonb_set(jsonb_set(state,"
            "   '{title}', to_jsonb($2::text)),"
            "   '{summary}', to_jsonb($3::text)),"
            "   '{turnCount}', to_jsonb(coalesce((state->>'turnCount')::int,0)+1)),"
            "   updated_at=now()"
            " WHERE session_id=$1",
            session_id, title[:28], summary[:200],
        )

    async def _ensure_session(self, session_id: str, user_id: str) -> None:
        """前端本地生成的会话 id 首次落库(幂等),保证 get_state/_patch_session 生效。"""
        await db.execute(
            "INSERT INTO agent.agent_sessions(session_id, user_id, state)"
            " VALUES($1,$2,$3) ON CONFLICT (session_id) DO NOTHING",
            session_id, user_id,
            json.dumps({"title": "新对话", "summary": "", "turnCount": 0}, ensure_ascii=False),
        )

    async def _save_message(self, *, session_id: str, message_id: str, run_id: str,
                            trace_id: str, user_id: str, role: str, text: str,
                            analysis: dict | None = None, cards: list | None = None) -> None:
        await db.execute(
            "INSERT INTO agent.agui_messages"
            " (message_id, session_id, run_id, trace_id, user_id, role, text, analysis, cards)"
            " VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)",
            message_id, session_id, run_id, trace_id, user_id, role, text,
            json.dumps(analysis, ensure_ascii=False, default=str) if analysis else None,
            json.dumps(cards, ensure_ascii=False, default=str) if cards else None,
        )

    # ---------------- 运行 ----------------

    async def run_message(
        self,
        *,
        session_id: str,
        text: str,
        user_context: UserContext,
        user_message_id: str = "",
        client_trace_id: str = "",
        assistant_message_id: str = "",
    ) -> AsyncIterator[dict]:
        """执行一轮问答,按序产出 AG-UI 事件。"""
        trace_id = new_trace_id()
        ids = {
            "sessionId": session_id,
            "runId": uuid.uuid4().hex,
            # 优先使用前端本地生成的助手消息 ID,保证前端事件归属匹配(§3.3)
            "messageId": assistant_message_id or f"msg-a-{uuid.uuid4().hex[:12]}",
            # 反馈入库需 traceId 关联推荐日志(agent_recommendation_logs)
            "traceId": trace_id,
        }
        # 会话管理:确保会话行存在(前端自建 id 首次发消息时);再加载多轮记忆
        try:
            await self._ensure_session(session_id, user_context.user_id)
        except Exception:  # noqa: BLE001 —— 会话落库失败不阻断回答
            pass
        history = await load_history(session_id)
        # 结构化短期记忆注入(运行产物组装,零额外 LLM):意图/结构化 prompt 读到精确槽位状态
        from app.agent.memory import append_memory_round, load_memory_lines
        memory_lines = await load_memory_lines(session_id)
        if memory_lines:
            history = ([{"role": "memory", "text": line} for line in memory_lines] + history)
        # 多轮续接通道(零 LLM):有待确认写操作卡 + 续接特征 → 直接合并草稿出卡
        from app.agent.action_drafts import is_continuation
        pending_card = await self._last_pending_card(session_id)
        if pending_card and is_continuation(text, pending_card):
            async for event in self._run_continuation(
                    session_id=session_id, text=text, ids=ids, trace_id=trace_id,
                    user_context=user_context, user_message_id=user_message_id,
                    pending_card=pending_card):
                yield event
            return
        state = AgentState(request=RequestState(
            trace_id=trace_id, run_id=ids["runId"], session_id=session_id,
            user_context=user_context, original_query=text,
            normalized_query=" ".join(text.split()),
            history=history,
        ))
        state.trace.trace_id = trace_id
        state.trace.run_id = ids["runId"]
        state.trace.session_id = session_id

        # 知识库优先:命中已发布 FAQ 直接给标准答案 + 责任人,不再走推荐链路
        faq = await self._lookup_faq(text)
        if faq:
            async for event in self._run_faq_answer(
                    session_id=session_id, text=text, ids=ids, trace_id=trace_id,
                    user_context=user_context, user_message_id=user_message_id, faq=faq):
                yield event
            return

        started = time.perf_counter()
        try:
            final = await asyncio.wait_for(build_orchestrator().run(state), timeout=30.0)
        except asyncio.TimeoutError:
            yield _event("run_error", ids, message="全链执行超时(30s),请稍后重试")
            yield _event("run_finished", ids)
            return
        except Exception as e:  # noqa: BLE001 —— 建流后错误兜底(§5.1)
            yield _event("run_error", ids, message=str(e)[:300])
            yield _event("run_finished", ids)
            return

        await persist_trace(final)
        get_metrics().record_request(final)

        analysis = self._build_analysis(final)
        # 持久化:用户消息 + 助手消息
        try:
            await self._save_message(session_id=session_id,
                                     message_id=user_message_id or f"msg-u-{uuid.uuid4().hex[:12]}",
                                     run_id=ids["runId"], trace_id=trace_id,
                                     user_id=user_context.user_id, role="user", text=text)
        except Exception:  # noqa: BLE001 —— 持久化失败不阻断回答
            pass

        yield _event("run_started", ids, result={"analysis": analysis})

        answer = final.response.final_answer
        for i in range(0, len(answer), 24):
            yield _event("text_delta", ids, delta=answer[i : i + 24])
        yield _event("text_finished", ids)

        cards_payload: list[dict] = []
        if final.response.confirmation_card:
            yield _event("confirmation_card", ids, card=final.response.confirmation_card)
            cards_payload = [final.response.confirmation_card]
        elif final.response.recommendation_cards:
            cards = await self._build_recommendation_cards(final)
            cards_payload = cards
            if cards:
                yield _event("recommendation_cards", ids, cards=cards)

        summary = f"{text[:24]} {analysis.get('intent') or ''}".strip()
        try:
            await self._save_message(session_id=session_id, message_id=ids["messageId"],
                                     run_id=ids["runId"], trace_id=trace_id,
                                     user_id=user_context.user_id, role="assistant",
                                     text=answer, analysis=analysis, cards=cards_payload)
            await self._log_recommendation(final, ids=ids, trace_id=trace_id,
                                           user_id=user_context.user_id, query=text)
            await self._patch_session(session_id, title=text, summary=summary)
            # 结构化短期记忆:本轮产物组装 round 摘要(意图/动作/槽位/状态),零额外 LLM
            card = final.response.confirmation_card
            await append_memory_round(session_id, {
                "q": text[:30],
                "intent": final.intent.intent.value if final.intent.intent else "",
                "action": (card.get("action") or {}).get("type", "") if card else "",
                "slots": self._slots_summary(card),
                "status": "待确认卡片" if card else "已回答",
            })
        except Exception:  # noqa: BLE001
            pass

        yield _event("state_delta", ids, patch={
            "title": text[:28], "turnCountIncrement": 1, "summary": summary,
        })
        yield _event("run_finished", ids, degraded=final.execution.degraded,
                     latencyMs=int((time.perf_counter() - started) * 1000))

    # ---------------- 知识库优先(FAQ 命中) ----------------

    FAQ_MIN_SIMILARITY = 0.45

    @classmethod
    async def _lookup_faq(cls, text: str) -> dict | None:
        """按问题文本匹配已发布 FAQ(pg_trgm 相似 + 子串命中),命中返回条目。"""
        query = " ".join((text or "").split())
        if len(query) < 4:
            return None
        try:
            row = await db.fetchrow(
                "SELECT id, question, answer, owner_person_id, similarity(question, $1) AS sim"
                " FROM public.faqs"
                " WHERE status = 'published'"
                "   AND (question % $1 OR question ILIKE '%' || $1 || '%'"
                "        OR $1 ILIKE '%' || question || '%')"
                " ORDER BY sim DESC, asked_count DESC LIMIT 1",
                query,
            )
        except Exception:  # noqa: BLE001 —— 知识库不可用不阻断正常问答
            return None
        if not row:
            return None
        question = row["question"] or ""
        sim = float(row["sim"] or 0)
        if sim < cls.FAQ_MIN_SIMILARITY and query not in question and question not in query:
            return None
        return dict(row)

    @staticmethod
    def _compose_faq_answer(faq: dict, owner: dict | None) -> str:
        lines = ["【知识库命中】这个问题已有沉淀好的标准答案：", "", (faq.get("answer") or "").strip()]
        if owner:
            extra = " / ".join(x for x in [owner.get("department"), owner.get("role")] if x)
            lines += ["", f"责任人：{owner['name']}" + (f"（{extra}）" if extra else "")]
        lines += ["", f"（来自知识库 FAQ #{faq['id']}；如与实际不符，可点「没帮助」反馈）"]
        return "\n".join(lines)

    async def _run_faq_answer(self, *, session_id: str, text: str, ids: dict, trace_id: str,
                              user_context: UserContext, user_message_id: str,
                              faq: dict) -> AsyncIterator[dict]:
        """FAQ 命中通道:直接输出标准答案 + 责任人名片,跳过检索/推荐链路。"""
        owner_id = faq.get("owner_person_id")
        owners = await self._load_persons([owner_id]) if owner_id else {}
        owner = owners.get(owner_id) if owner_id else None
        answer = self._compose_faq_answer(faq, owner)
        analysis = {"intent": "faq", "queryType": None, "systems": [], "symptoms": [],
                    "concepts": [], "degraded": False, "faqId": faq["id"]}

        try:
            await self._save_message(session_id=session_id,
                                     message_id=user_message_id or f"msg-u-{uuid.uuid4().hex[:12]}",
                                     run_id=ids["runId"], trace_id=trace_id,
                                     user_id=user_context.user_id, role="user", text=text)
        except Exception:  # noqa: BLE001
            pass

        yield _event("run_started", ids, result={"analysis": analysis})
        for i in range(0, len(answer), 24):
            yield _event("text_delta", ids, delta=answer[i : i + 24])
        yield _event("text_finished", ids)

        cards: list[dict] = []
        if owner:
            cards = [{
                "id": f"faq-{faq['id']}-{owner['id']}",
                "kind": "recommendation",
                "rank": 1,
                "person": {"id": owner["id"], "name": owner["name"]},
                "reasons": [f"知识库条目 #{faq['id']} 的责任人"],
                "related": [],
                "personId": owner["id"],
                "rankLabel": "知识库",
            }]
            yield _event("recommendation_cards", ids, cards=cards)

        summary = f"{text[:24]} faq"
        try:
            await self._save_message(session_id=session_id, message_id=ids["messageId"],
                                     run_id=ids["runId"], trace_id=trace_id,
                                     user_id=user_context.user_id, role="assistant",
                                     text=answer, analysis=analysis, cards=cards)
            await self._patch_session(session_id, title=text, summary=summary)
            from app.agent.memory import append_memory_round
            await append_memory_round(session_id, {
                "q": text[:30], "intent": "faq", "action": "", "slots": "",
                "status": "知识库命中",
            })
            # 命中计数(沉淀打分/热度用)
            await db.execute("UPDATE public.faqs SET asked_count = asked_count + 1 WHERE id = $1",
                             faq["id"])
        except Exception:  # noqa: BLE001
            pass

        yield _event("state_delta", ids, patch={
            "title": text[:28], "turnCountIncrement": 1, "summary": summary,
        })
        yield _event("run_finished", ids, degraded=False, latencyMs=0)

    # ---------------- 多轮续接通道 ----------------

    @staticmethod
    def _slots_summary(card: dict | None) -> str:
        """从确认卡提取槽位摘要(结构化记忆用)。"""
        action = (card or {}).get("action") or {}
        patch = action.get("nextProfilePatch")
        if patch:
            return ",".join(f"{k}={v}" for k, v in patch.items() if not k.startswith("_"))[:80]
        review = action.get("nextReview")
        if review:
            return f"{review.get('personName', '')}:{review.get('tag', '')}"[:80]
        content = action.get("nextContent")
        if content:
            return f"title={content.get('title', '')}"[:80]
        return ""

    @staticmethod
    async def _last_pending_card(session_id: str) -> dict | None:
        """最近一条助手消息里尚未被 confirm 事件消费的确认卡;无则 None。"""
        try:
            row = await db.fetchrow(
                "SELECT cards FROM agent.agui_messages"
                " WHERE session_id=$1 AND role='assistant' AND cards IS NOT NULL"
                " ORDER BY id DESC LIMIT 1", session_id)
            if not row:
                return None
            cards = row["cards"]
            if isinstance(cards, str):
                cards = json.loads(cards)
            for card in (cards or []):
                if card.get("kind") != "confirmation":
                    continue
                if card.get("status") not in (None, "active"):
                    continue
                confirmed = await db.fetchval(
                    "SELECT 1 FROM agent.feedback_events"
                    " WHERE target_id=$1 AND value LIKE 'confirm_%' LIMIT 1",
                    card.get("id"))
                if not confirmed:
                    return card
        except Exception:  # noqa: BLE001
            return None
        return None

    async def _run_continuation(self, *, session_id: str, text: str, ids: dict,
                                trace_id: str, user_context: UserContext,
                                user_message_id: str, pending_card: dict):
        """续接通道:合并上一张草稿出新确认卡,零 LLM,毫秒级。"""
        from app.agent.action_drafts import build_continuation_card
        from app.agent.memory import append_memory_round

        card = build_continuation_card(pending_card, text, run_id=ids["runId"])
        action_type = card["action"]["type"]
        analysis = {"intent": "edit", "actionType": action_type,
                    "summary": card["analysis"]["summary"], "continuation": True}
        reply = "已在上一张草稿卡片的基础上合并你的补充，确认后生效。"
        try:
            await self._save_message(
                session_id=session_id,
                message_id=user_message_id or f"msg-u-{uuid.uuid4().hex[:12]}",
                run_id=ids["runId"], trace_id=trace_id,
                user_id=user_context.user_id, role="user", text=text)
        except Exception:  # noqa: BLE001
            pass
        yield _event("run_started", ids, result={"analysis": analysis})
        for i in range(0, len(reply), 24):
            yield _event("text_delta", ids, delta=reply[i : i + 24])
        yield _event("text_finished", ids)
        yield _event("confirmation_card", ids, card=card)
        try:
            await self._save_message(session_id=session_id, message_id=ids["messageId"],
                                     run_id=ids["runId"], trace_id=trace_id,
                                     user_id=user_context.user_id, role="assistant",
                                     text=reply, analysis=analysis, cards=[card])
            await self._patch_session(session_id, title=text,
                                      summary=f"{text[:24]} edit")
            await append_memory_round(session_id, {
                "q": text[:30], "intent": "edit", "action": action_type,
                "slots": self._slots_summary(card), "status": "待确认卡片(续接合并)",
            })
        except Exception:  # noqa: BLE001
            pass
        yield _event("state_delta", ids, patch={
            "title": text[:28], "turnCountIncrement": 1,
            "summary": f"{text[:24]} edit",
        })
        yield _event("run_finished", ids, degraded=False, latencyMs=0)

    # ---------------- 事件内容构建 ----------------

    @staticmethod
    def _build_analysis(final: AgentState) -> dict:
        return {
            "intent": final.intent.intent.value if final.intent.intent else None,
            "queryType": final.intent.query_type.value if final.intent.query_type else None,
            "systems": final.understanding.mentioned_systems,
            "symptoms": final.understanding.symptoms,
            "concepts": [c.get("canonical_name") for c in final.concept.resolved_concepts],
            "degraded": final.execution.degraded,
        }

    async def _build_recommendation_cards(self, final: AgentState) -> list[dict]:
        ranked = [c for c in final.ranking.ranked_candidates
                  if c["score"] >= CARD_SCORE_FLOOR][:MAX_CARDS]
        persons = await self._load_persons([c["person_id"] for c in ranked])
        related_map = await self._load_related_contents([c["person_id"] for c in ranked])
        cards = []
        for index, c in enumerate(ranked):
            pid = c["person_id"]
            cards.append({
                "id": f"rec-{final.request.run_id}-{pid}",
                "kind": "recommendation",
                "rank": index + 1,
                "rankLabel": RANK_LABELS[min(index, len(RANK_LABELS) - 1)],
                "person": persons.get(pid, {"id": pid, "name": pid}),
                "personId": pid,
                "reasons": _build_reasons(c),
                "related": related_map.get(pid, []),
            })
        return cards

    @staticmethod
    async def _load_persons(person_ids: list[str]) -> dict[str, dict]:
        if not person_ids:
            return {}
        rows = await db.fetch(
            # 联系方式与前端名片库同规则:本人维护的 contact 优先,空则回落初始导入的 phone
            "SELECT id, name, department, role,"
            " COALESCE(NULLIF(contact, ''), NULLIF(phone, '')) AS contact"
            " FROM public.people WHERE id = ANY($1)",
            person_ids)
        return {r["id"]: {"id": r["id"], "name": r["name"], "department": r["department"],
                          "role": r["role"], "contact": r["contact"]} for r in rows}

    @staticmethod
    async def _load_related_contents(person_ids: list[str]) -> dict[str, list[dict]]:
        """候选人已发布内容(卡片「相关发布内容」;人员详情/内容详情跳转用)。"""
        if not person_ids:
            return {}
        # 每人至多 3 条(按创建时间倒序)
        rows2 = await db.fetch(
            "SELECT owner_id, id, title, rank FROM ("
            "  SELECT owner_id, id, title,"
            "         row_number() OVER (PARTITION BY owner_id ORDER BY created_at DESC) AS rank"
            "  FROM public.contents WHERE owner_id = ANY($1) AND status = 'published'"
            ") t WHERE rank <= 3",
            person_ids)
        result = {}
        for r in rows2:
            result.setdefault(r["owner_id"], []).append({"id": r["id"], "title": r["title"]})
        return result

    @staticmethod
    async def _log_recommendation(final: AgentState, *, ids: dict, trace_id: str,
                                  user_id: str, query: str) -> None:
        """推荐记录落库(v4 §十二:问题摘要/候选人员/排序证据/会话/消息/运行标识)。"""
        if not final.ranking.ranked_candidates:
            return
        await db.execute(
            "INSERT INTO agent.agent_recommendation_logs"
            " (trace_id, session_id, message_id, user_id, query_summary,"
            "  query_type, rank_policy, ranked_candidates, gate_decision)"
            " VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)",
            trace_id, ids["sessionId"], ids["messageId"], user_id, query[:80],
            final.intent.query_type.value if final.intent.query_type else None,
            final.ranking.rank_policy or None,
            json.dumps(final.ranking.ranked_candidates[:5], ensure_ascii=False, default=str),
            final.ranking.gate_decision.value if final.ranking.gate_decision else None,
        )


def _loads(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def _build_reasons(candidate: dict) -> list[str]:
    """推荐理由:命中依据(正式责任/领域/画像/内容/评价),不只说"匹配度高"(v4 §四)。"""
    reasons: list[str] = []
    if candidate.get("has_formal") and candidate.get("responsibilities"):
        rec = candidate["responsibilities"][0]
        reasons.append(f"正式责任:{rec.get('title', '')}(责任部门:{rec.get('owner_department', '')})")
    for e in candidate.get("evidences", []):
        detail = e.get("detail") or {}
        etype = e.get("evidence_type", "")
        if etype == "explicit_self_tag" and detail.get("source_raw_tag"):
            reasons.append(f"负责领域命中:{detail['source_raw_tag']}")
        elif etype == "inferred_from_profile":
            if detail.get("no_exact_match"):
                reasons.append(f"可能相关:{detail.get('reason') or '具备相近岗位或领域经验'}")
            else:
                reasons.append("自画像与问题相关")
        elif etype == "inferred_from_article":
            hint = detail.get("title_hint") or detail.get("document_id") or ""
            reasons.append(f"发布过相关内容:{hint}" if hint else "发布过相关内容")
        elif etype == "inferred_from_review":
            reasons.append("同事评价提及相关能力")
        elif etype == "directory_match":
            reasons.append("人员名录精确匹配")
    if candidate.get("feedback_adjust"):
        reasons.append("历史反馈较好" if candidate["feedback_adjust"] > 0 else "历史反馈欠佳")
    # 去重保序,至多 4 条
    seen, unique = set(), []
    for r in reasons:
        if r and r not in seen:
            seen.add(r)
            unique.append(r)
    return unique[:4] or ["综合证据匹配"]
