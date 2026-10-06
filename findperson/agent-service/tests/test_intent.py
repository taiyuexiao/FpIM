"""模块 11:意图识别 + RuleFallbackRouter 测试。"""
import pytest
import pytest_asyncio

from app.agent.intent import IntentNode, IntentService, RuleFallbackRouter
from app.agent.orchestrator import ServiceRegistry
from app.contracts.agent_state import (
    AgentState, Intent, QueryType, RequestState, UserContext,
)
from app.contracts.errors import ErrorCode, llm_error
from app.core.llm_client import LLMResult
from app.core.db import close_pool, fetchval, health, init_pool

pytestmark = pytest.mark.asyncio(loop_scope="module")


def _state(query: str) -> AgentState:
    return AgentState(
        request=RequestState(trace_id="t", run_id="r",
                             user_context=UserContext(user_id="p-0001"),
                             original_query=query, normalized_query=query)
    )


class StubLLM:
    """返回固定 JSON 的 LLM stub。"""

    def __init__(self, data: dict | None = None, error: Exception | None = None):
        self._data = data
        self._error = error

    async def structured_chat(self, messages, *, required_keys, **kw):
        if self._error:
            raise self._error
        return self._data, LLMResult(content="{}", tokens=10, model="stub")


async def test_llm_classify_find_person() -> None:
    """LLM 正常:解析意图与 query_type。"""
    svc = IntentService(StubLLM({
        "intent": "find_person", "query_type": "explicit_responsibility",
        "confidence": 0.97, "needs_clarification": False, "clarify_question": "",
    }))
    result = await svc.classify("谁负责智能体平台?")
    assert result.intent == Intent.FIND_PERSON
    assert result.query_type == QueryType.EXPLICIT_RESPONSIBILITY
    assert result.confidence == 0.97


async def test_llm_classify_illegal_value() -> None:
    """LLM 输出非法枚举值 → INTENT_ERROR(LLM 不允许产生 Schema 外输出)。"""
    svc = IntentService(StubLLM({
        "intent": "hack", "query_type": None, "confidence": 1.0,
        "needs_clarification": False, "clarify_question": "",
    }))
    with pytest.raises(Exception) as exc:
        await svc.classify("x")
    assert getattr(exc.value, "code", None) == ErrorCode.INTENT_ERROR


async def test_node_degrades_to_rule_on_llm_failure() -> None:
    """LLM 故障 → 降级规则路由,degraded=true 且意图仍正确。"""
    try:
        await init_pool()
    except Exception:
        pytest.skip("数据库不可用")
    if not await health():
        pytest.skip()
    services = ServiceRegistry({"intent_service": IntentService(StubLLM(error=llm_error("API down")))})
    node = IntentNode()
    name = await fetchval("SELECT name FROM public.people WHERE status='active' ORDER BY id LIMIT 1")
    update = await node.execute(_state(f"{name}的电话是多少?"), services)
    assert update.degraded is True
    assert update.intent.intent == Intent.FIND_PERSON
    assert update.intent.query_type == QueryType.CONTACT_LOOKUP
    await close_pool()


async def test_node_defaults_to_find_person_when_nothing_works() -> None:
    """架构收敛(查/写双轨):LLM 故障且规则无特定命中 → 默认低置信查人,
    由检索与置信门自判 NO_RESULT(不再产出 unclear)。"""
    try:
        await init_pool()
    except Exception:
        pytest.skip("数据库不可用")
    services = ServiceRegistry({"intent_service": IntentService(StubLLM(error=llm_error("down")))})
    node = IntentNode()
    update = await node.execute(_state("嗯那个事情怎么办呢"), services)
    assert update.intent.intent == Intent.FIND_PERSON
    assert update.intent.query_type is None
    assert update.intent.confidence <= 0.5
    assert update.degraded is True
    await close_pool()


async def test_rule_router_high_certainty_only() -> None:
    """规则路由:查电话/谁负责高确定性命中;无特定命中默认低置信查人(架构收敛)。"""
    try:
        await init_pool()
    except Exception:
        pytest.skip("数据库不可用")
    router = RuleFallbackRouter()
    name = await fetchval("SELECT name FROM public.people WHERE status='active' ORDER BY id LIMIT 1")
    r1 = await router.route(f"{name}电话多少")
    assert r1 is not None and r1.query_type == QueryType.CONTACT_LOOKUP
    r2 = await router.route("谁负责Dify平台")
    assert r2 is not None and r2.query_type == QueryType.EXPLICIT_RESPONSIBILITY
    r3 = await router.route("Dify并发一高就超时,还伴随各种诡异的现象,该找谁")
    # 架构收敛:规则无特定命中时默认低置信查人,由检索/置信门判 NO_RESULT(不再返回 None)
    assert r3 is not None and r3.intent == Intent.FIND_PERSON
    assert r3.query_type is None and r3.confidence <= 0.5
    await close_pool()
