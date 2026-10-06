"""模块 28:评测体系测试(harness 正确性,跑小子集)。"""
import pytest
import pytest_asyncio

from app.core.db import close_pool, health, init_pool
from app.eval.metrics import MetricsAccumulator, attribute_error, hit_at_k, recall_at_k
from app.eval.runner import load_cases, run_evaluation

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


def test_metric_primitives() -> None:
    """Recall@k / Hit@k 基础函数。"""
    assert recall_at_k(["a", "b", "c"], ["a", "d"], 2) == 0.5
    assert recall_at_k([], ["a"], 3) == 0.0
    assert recall_at_k([], [], 3) == 1.0
    assert hit_at_k(["a"], ["a", "b"], 1) == 1.0
    assert hit_at_k(["c"], ["a"], 1) == 0.0


def test_error_attribution() -> None:
    """错误归因:概念错/召回错/排序错分层(§16.2)。"""
    from app.eval.metrics import CaseResult
    r = CaseResult(case_id="x", query="q", intent="find_person",
                   query_type="explicit_responsibility",
                   predicted_intent="find_person",
                   predicted_query_type="explicit_responsibility",
                   resolved_concept_names=["别的概念"],
                   gold_concept_names=["数据治理"],
                   gold_person_ids=["p-0001"])
    assert attribute_error(r) == "query_concept_error"
    r2 = CaseResult(case_id="y", query="q", intent="find_person",
                    query_type="expert_finding",
                    predicted_intent="find_person",
                    predicted_query_type="expert_finding",
                    resolved_concept_names=["数据治理"],
                    structured_person_ids=["p-0001"],
                    candidate_person_ids=["p-0001"],
                    ranked_person_ids=["p-9999"],
                    gold_concept_names=["数据治理"], gold_person_ids=["p-0001"])
    assert attribute_error(r2) == "ranking_error"


def test_dataset_split_frozen(pool) -> None:
    """dev/test 两套独立存在,用例有 gold 标注(§16.1)。"""
    dev = load_cases("dev")
    test = load_cases("test")
    assert dev and test
    assert {c["id"] for c in dev}.isdisjoint({c["id"] for c in test})
    for c in dev:
        assert "gold" in c and "intent" in c and "query" in c


async def test_runner_small_subset(pool) -> None:
    """Runner 端到端:跑 dev 前 4 例,指标结构完整、报告含基线对比(§16.1)。"""
    import app.eval.runner as runner_mod
    original_load = runner_mod.load_cases
    runner_mod.load_cases = lambda split="dev": original_load(split)[:4]
    try:
        output = await run_evaluation("dev", baselines=("A", "D"))
    finally:
        runner_mod.load_cases = original_load
    assert output["baselines"]["A"]["metrics"]["cases"] == 4
    d_metrics = output["baselines"]["D"]["metrics"]
    for key in ("Intent Accuracy", "Final Recall@3", "Error Attribution"):
        assert key in d_metrics
    # Baseline 对照存在(§16.3:避免无法判断提升来自哪个模块)
    assert set(output["baselines"].keys()) == {"A", "D"}
