"""用户反馈:互斥/取消语义(DB)+ 排序回流调整值(纯逻辑)。

DB 测试连真实库(shouwenzeren_agent),DB 不可用时整组跳过。
"""
import pytest
import pytest_asyncio

from app.core.db import close_pool, fetchval, health, init_pool
from app.feedback.repository import FeedbackRepository
from app.feedback.service import FeedbackService

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def pool():
    try:
        await init_pool()
    except Exception:
        pytest.skip("数据库不可用,跳过反馈 DB 测试")
    if not await health():
        pytest.skip("数据库 health 未通过")
    yield
    await close_pool()


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def repo(pool):
    repo = FeedbackRepository()
    yield repo
    # 清理测试数据
    from app.core import db
    await db.execute("DELETE FROM agent.feedback_events WHERE user_id LIKE 'test-fb-%'")


async def test_vote_record_update_cancel(repo) -> None:
    """互斥:首次记录 → 异值改值 → 同值取消(v4 §四)。"""
    uid = "test-fb-001"
    r1 = await repo.record_vote(user_id=uid, target_type="person", target_id="p-0001",
                                value="up", message_id="m1", trace_id="t1")
    assert r1["status"] == "recorded"
    # 异值:up → down(改值,不新增)
    r2 = await repo.record_vote(user_id=uid, target_type="person", target_id="p-0001",
                                value="down", message_id="m1", reason="人选不对")
    assert r2["status"] == "updated"
    n = await fetchval(
        "SELECT count(*) FROM agent.feedback_events"
        " WHERE user_id=$1 AND target_id='p-0001' AND message_id='m1'", uid)
    assert n == 1
    # 同值:取消(删除)
    r3 = await repo.record_vote(user_id=uid, target_type="person", target_id="p-0001",
                                value="down", message_id="m1")
    assert r3["status"] == "cancelled"
    n = await fetchval(
        "SELECT count(*) FROM agent.feedback_events"
        " WHERE user_id=$1 AND target_id='p-0001' AND message_id='m1'", uid)
    assert n == 0


async def test_vote_requires_session_message_trace(repo) -> None:
    """推荐反馈关联 session/message/trace(v4 §四/§十二)。"""
    uid = "test-fb-002"
    await repo.record_vote(user_id=uid, target_type="person", target_id="p-0002",
                           value="up", message_id="m9", session_id="s9", trace_id="tr9")
    row = await fetchval(
        "SELECT session_id || '/' || message_id || '/' || trace_id"
        " FROM agent.feedback_events WHERE user_id=$1", uid)
    assert row == "s9/m9/tr9"


async def test_interaction_appends(repo) -> None:
    """interaction 事件全量追加不去重。"""
    uid = "test-fb-003"
    for _ in range(2):
        await repo.record_interaction(user_id=uid, event_type="person_detail_open",
                                      target_type="person", target_id="p-0003")
    n = await fetchval(
        "SELECT count(*) FROM agent.feedback_events"
        " WHERE user_id=$1 AND feedback_type='interaction'", uid)
    assert n == 2


async def test_person_adjustments_math() -> None:
    """回流调整公式:weight × (up-down)/(up+down+1),不超 weight 上限。"""

    class StubRepo:
        async def person_vote_summary(self):
            return {"p-good": {"up": 3, "down": 0}, "p-bad": {"up": 0, "down": 3},
                    "p-mix": {"up": 1, "down": 1}}

    svc = FeedbackService(repo=StubRepo())
    adj = await svc.person_adjustments()
    weight = 0.1
    assert adj["p-good"] == pytest.approx(weight * 3 / 4, abs=1e-4)
    assert adj["p-bad"] == pytest.approx(-weight * 3 / 4, abs=1e-4)
    assert adj["p-mix"] == pytest.approx(0.0, abs=1e-4)
    assert all(abs(v) < weight for v in adj.values())


def test_down_reasons_config() -> None:
    """点踩原因配置非空且含 code/label(GET /agent/feedback/reasons)。"""
    reasons = FeedbackService.down_reasons()
    assert reasons and all(r["code"] and r["label"] for r in reasons)
