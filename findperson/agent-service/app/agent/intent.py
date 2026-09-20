"""一级意图与查询类型识别 + RuleFallbackRouter(V1.2 §5.2 / §5.3)。

- IntentService:LLM 输出严格限制为 Intent Schema;LLM 不允许直接产生
  人员 ID、最终概念 ID 或 SQL(§5.2)——这里只输出意图枚举。
- RuleFallbackRouter:LLM 不可用时的应急路由,只覆盖高确定性情况
  (查电话、谁负责明确系统 X、查某部门某人),不猜测复杂责任关系;
  所有降级输出显式 degraded=true。
"""
from __future__ import annotations

import re

from app.agent.orchestrator import AgentNode, ServiceRegistry
from app.contracts.agent_state import (
    AgentState, Intent, IntentState, QueryType, StateUpdate,
)
from app.contracts.errors import AgentError, ErrorCode
from app.core import db
from app.core.llm_client import LLMPort, get_llm

# ---------------------------------------------------------------- Prompt(业务 Prompt 归本模块,不进 LLM Client)

INTENT_PROMPT = """你是首问必答平台的意图识别器。平台只做两件事:查(帮用户找到对的人)和写(维护资料/发布内容/画像)。把用户问题分类为以下一级意图之一:

- find_person:一切非写操作的问题(默认项)。包括:找人(负责人、联系人、专家、谁懂某领域、谁喜欢/擅长某事、故障找谁);知识/制度/流程/操作方法/技术方案类问题(平台以“找懂它的人”作答,同样归此类);寒暄、问候、与平台业务无关的对话
- edit:写操作,包括修改本人资料(如『我现在负责X』『把我的电话改为X』『我的负责领域更新为X』)、发布内容、为他人写评价/画像
- unclear:完全无法理解(乱码、无意义输入)

若意图是 find_person,再判断查询类型:
- contact_lookup:查某人的电话/联系方式/基本信息
- explicit_responsibility:明确问"谁负责某系统/平台/领域"
- diagnostic:描述故障/症状/异常现象,问该找谁
- expert_finding:问"谁比较懂/谁是专家/谁做过";知识/制度/流程/操作方法类问题也归入此类
- 寒暄/无关对话:query_type 输出 null

严格输出 JSON(不要输出任何其他内容):
{{"intent": "...", "query_type": "...或null", "confidence": 0.0~1.0,
 "needs_clarification": false, "clarify_question": ""}}

{history_block}用户问题: {query}"""


# ---------------------------------------------------------------- RuleFallbackRouter(§5.3)

class RuleFallbackRouter:
    """LLM 不可用时的应急路由。仅覆盖高确定性情况。"""

    def __init__(self) -> None:
        self._names: list[str] = []
        self._loaded = False

    async def _ensure_dict(self) -> None:
        if self._loaded:
            return
        rows = await db.fetch("SELECT name FROM public.people WHERE status='active'")
        self._names = [r["name"] for r in rows]
        self._loaded = True

    async def route(self, query: str) -> IntentState | None:
        """命中高确定性规则则返回 IntentState,否则返回 None(不猜复杂情况)。"""
        await self._ensure_dict()
        q = query.strip()

        # 1) 查电话/联系方式 → contact_lookup
        if re.search(r"(电话|手机号|联系方式|怎么联系)", q):
            for name in self._names:
                if name in q:
                    return IntentState(intent=Intent.FIND_PERSON,
                                       query_type=QueryType.CONTACT_LOOKUP, confidence=0.95)

        # 2) "谁负责X" → explicit_responsibility
        if re.search(r"谁(来)?负责", q):
            return IntentState(intent=Intent.FIND_PERSON,
                               query_type=QueryType.EXPLICIT_RESPONSIBILITY, confidence=0.9)

        # 2.5) "谁喜欢/擅长/会/懂/熟悉 X" → expert_finding(兴趣/技能找人)
        if re.search(r"谁(喜欢|擅长|会|懂|熟悉|了解)", q):
            return IntentState(intent=Intent.FIND_PERSON,
                               query_type=QueryType.EXPERT_FINDING, confidence=0.9)

        # 3) "X部门(的)谁/人" → contact_lookup(部门找人)
        if re.search(r"部(的门|人员|谁|找人)", q):
            return IntentState(intent=Intent.FIND_PERSON,
                               query_type=QueryType.CONTACT_LOOKUP, confidence=0.85)

        # 4) 高确定性写操作 → edit(架构收敛:查/写双轨,写操作不进查人链)
        if _looks_like_write(q):
            return IntentState(intent=Intent.EDIT, confidence=0.8)

        # 5) 默认:低置信进查人链,由检索与置信门自判 NO_RESULT(架构收敛:不再猜 unclear)
        return IntentState(intent=Intent.FIND_PERSON, confidence=0.3)


# 高确定性写操作模式(仅供 _looks_like_write 纠偏使用)
_WRITE_PATTERNS = (
    r"我的.{1,12}(改为|修改为|改成|更新为|更新成|变为|变成)",
    r"(联系方式|电话|手机号|邮箱|负责领域|自画像|字画像|画像|岗位).{0,4}(改为|改成|变为|换成|是|为)",
    r"我(现在|目前|如今)?负责",        # 『我现在负责X』→ 负责领域变更
    r"(为|给|帮).{1,8}(添加|增加|加|写|补|补一?条|补充).{0,4}(评价|画像|标签)",
    r"(发布|投稿|写一?篇|发一?篇)",
)


def _looks_like_write(query: str) -> bool:
    """高确定性写操作识别(用于纠正 LLM 把写操作误判为 chat/unclear)。"""
    return any(re.search(p, query) for p in _WRITE_PATTERNS)


# ---------------------------------------------------------------- IntentService(§5.2)

class IntentService:
    """LLM 意图识别。输出严格限制为 Schema,非法枚举值视为失败。"""

    def __init__(self, llm: LLMPort | None = None) -> None:
        self._llm = llm

    async def classify(self, query: str, history: list[dict] | None = None) -> IntentState:
        llm = self._llm or get_llm()
        # 多轮记忆:有历史时注入对话上下文,支撑追问/指代(如『他的电话呢』)
        history_block = ""
        if history:
            from app.agent.memory import format_history
            text = format_history(history)
            if text:
                history_block = f"对话历史(供理解追问/指代,追问意图以上下文为准):\n{text}\n\n"
        data, _result = await llm.structured_chat(
            [{"role": "user", "content": INTENT_PROMPT.format(query=query, history_block=history_block)}],
            required_keys=["intent", "query_type", "confidence",
                           "needs_clarification", "clarify_question"],
        )
        try:
            intent = Intent(str(data["intent"]))
        except ValueError as e:
            raise AgentError(ErrorCode.INTENT_ERROR, f"LLM 输出非法意图: {data['intent']}") from e

        # 高确定性写操作校正:LLM 把明显写操作误判为 chat/unclear 时纠偏
        # (如『我现在负责X』『把我的电话改为X』被误判为闲聊;§5.2 意图枚举不变)
        if intent in (Intent.CHAT, Intent.UNCLEAR) and _looks_like_write(query):
            intent = Intent.EDIT

        # 架构收敛(查/写双轨):废弃意图防御性映射——知识问答并入查人(expert_finding),
        # 闲聊默认查人。新 prompt 已不提供这两个选项,此处兼容旧缓存/旧 prompt 输出
        if intent == Intent.KNOWLEDGE_QA:
            intent = Intent.FIND_PERSON
            data["query_type"] = data.get("query_type") or QueryType.EXPERT_FINDING.value
        elif intent == Intent.CHAT:
            intent = Intent.FIND_PERSON

        query_type = None
        if intent == Intent.FIND_PERSON and data.get("query_type"): 
            try:
                query_type = QueryType(str(data["query_type"]))
            except ValueError as e:
                raise AgentError(ErrorCode.INTENT_ERROR,
                                 f"LLM 输出非法 query_type: {data['query_type']}") from e
        if intent == Intent.UNCLEAR:
            needs_clarification = True
        else:
            needs_clarification = bool(data.get("needs_clarification", False))

        return IntentState(
            intent=intent,
            query_type=query_type,
            confidence=float(data.get("confidence") or 0.0),
            needs_clarification=needs_clarification,
            clarify_question=str(data.get("clarify_question") or ""),
        )


# ---------------------------------------------------------------- IntentNode

class IntentNode(AgentNode):
    """意图识别节点。LLM 失败时降级 RuleFallbackRouter(§5.3)。"""

    name = "IntentNode"
    timeout_ms = 15000
    on_error = "degrade"  # 双保险:规则也失败时由编排器降级收敛

    async def execute(self, state: AgentState, services: ServiceRegistry) -> StateUpdate:
        query = state.request.normalized_query or state.request.original_query
        service = services.get("intent_service") if "intent_service" in services.services else IntentService()
        # 意图短缓存:相同(问题+历史)直接命中,省一次远程 LLM 往返(验收:响应慢)
        from app.agent.memory import format_history
        from app.core.cache import get_cache
        cache = get_cache()
        cache_key = f"intent:{query}|{format_history(state.request.history)}"
        try:
            cached = await cache.get(cache_key)
        except Exception:  # noqa: BLE001 —— 缓存故障不影响主链
            cached = None
        if cached is not None:
            return StateUpdate(intent=IntentState(**cached))
        try:
            intent_state = await service.classify(query, history=state.request.history)
            try:
                await cache.set(cache_key, intent_state.model_dump(), ttl_seconds=300)
            except Exception:  # noqa: BLE001
                pass
            return StateUpdate(intent=intent_state)
        except AgentError as e:
            if e.code not in (ErrorCode.LLM_ERROR, ErrorCode.TIMEOUT, ErrorCode.INTENT_ERROR):
                raise
            # 降级:应急规则路由(§5.3)
            fallback = RuleFallbackRouter()
            rule_state = await fallback.route(query)
            if rule_state is not None:
                return StateUpdate(
                    intent=rule_state, degraded=True,
                    error={"code": e.code.value, "message": f"LLM 不可用,降级规则路由: {e.message}"},
                )
            # 规则也不覆盖:不猜测,显式 unclear(§5.3:不通过规则猜测复杂责任关系)
            return StateUpdate(
                intent=IntentState(intent=Intent.UNCLEAR, confidence=0.0,
                                   needs_clarification=True,
                                   clarify_question="我暂时无法理解您的问题,能否换个说法,例如『谁负责XX系统』?"),
                degraded=True,
                error={"code": e.code.value, "message": f"LLM 与规则均不可用: {e.message}"},
            )
