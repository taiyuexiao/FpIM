"""模块 12:QueryStructurer 测试。"""
import pytest
import pytest_asyncio

from app.agent.query_structurer import QueryStructurerNode, QueryStructurerService
from app.agent.orchestrator import ServiceRegistry
from app.contracts.agent_state import (
    AgentState, Intent, IntentState, RequestState, UserContext,
)
from app.core.db import close_pool, health, init_pool
from app.core.llm_client import LLMResult

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def pool():
    try:
        await init_pool()
    except Exception:
        pytest.skip("数据库不可用")
    if not await health():
        pytest.skip()
    yield
    await close_pool()


def _state(query: str, intent: Intent = Intent.FIND_PERSON) -> AgentState:
    s = AgentState(
        request=RequestState(trace_id="t", run_id="r",
                             user_context=UserContext(user_id="p-0001"),
                             original_query=query, normalized_query=query)
    )
    s.intent = IntentState(intent=intent)
    return s


class StubLLM:
    def __init__(self, data=None, error=None):
        self._data, self._error = data, error

    async def structured_chat(self, messages, *, required_keys, **kw):
        if self._error:
            raise self._error
        return self._data, LLMResult(content="{}", tokens=5, model="stub")


async def test_structure_diagnostic_query(pool) -> None:
    """诊断类问题:LLM 要素抽取 + 字段来源标注(§6.1)。"""
    svc = QueryStructurerService(StubLLM({
        "systems": ["Dify"], "objects": ["Agent", "大模型调用"],
        "symptoms": ["并发高", "超时"], "duty_clues": ["性能优化", "故障排查"],
    }))
    u = await svc.structure("Dify上的Agent并发一高就超时,该找谁?")
    assert u.mentioned_systems == ["Dify"]
    assert "并发高" in u.symptoms
    assert u.field_sources["systems:Dify"] == "explicit"      # 原文出现
    assert u.field_sources["duty_clues:性能优化"] == "inferred"  # 原文未出现 → 模型推断
    assert "Dify" in u.explicit_terms


async def test_explicit_people_department(pool) -> None:
    """人名/部门名走词典显式匹配,来源 explicit。"""
    svc = QueryStructurerService(StubLLM({"systems": [], "objects": [],
                                          "symptoms": [], "duty_clues": []}))
    u = await svc.structure("王丹的电话是多少")
    assert "王丹" in u.mentioned_people
    assert u.field_sources["people:王丹"] == "explicit"


async def test_node_skip_non_find_person(pool) -> None:
    """非 find_person 意图不执行(§6.1 只服务找人查询)。"""
    node = QueryStructurerNode()
    update = await node.execute(_state("今天天气不错", intent=Intent.CHAT), ServiceRegistry())
    assert update.understanding is None


async def test_failure_no_fake_concepts(pool) -> None:
    """LLM 失败:不产生虚假概念,保留词典匹配,degraded(§6.1 验收)。"""
    svc = QueryStructurerService(StubLLM(error=RuntimeError("LLM down")))
    node = QueryStructurerNode()
    services = ServiceRegistry({"query_structurer": svc})
    update = await node.execute(_state("王丹负责的领域出问题了,找谁"), services)
    assert update.degraded is True
    u = update.understanding
    assert u.mentioned_systems == [] and u.symptoms == []  # 无虚假推断
    assert "王丹" in u.mentioned_people                    # 词典匹配保留
