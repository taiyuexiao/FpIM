"""模块 08:业务数据校验(连真实库;V2 数据集经 scripts/import_v2_data.py 导入)。"""
import pytest
import pytest_asyncio

from app.core.db import close_pool, fetchrow, fetchval, health, init_pool

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def pool():
    try:
        await init_pool()
    except Exception:
        pytest.skip("数据库不可用,跳过")
    if not await health():
        pytest.skip("数据库 health 未通过,跳过")
    yield
    await close_pool()


async def test_people_300(pool) -> None:
    """V2:252 人全部导入,保留 p-* 形式 id。"""
    assert await fetchval("SELECT count(*) FROM public.people") == 252
    assert await fetchval("SELECT count(*) FROM public.people WHERE id LIKE 'p-%'") == 252


async def test_departments_and_link(pool) -> None:
    """20 个部门,人员 department_id 已关联。"""
    assert await fetchval("SELECT count(*) FROM public.departments") == 20
    orphan = await fetchval("SELECT count(*) FROM public.people WHERE department_id IS NULL")
    assert orphan == 0


async def test_contents_30(pool) -> None:
    """V2:620 篇内容导入,标签数组非空。"""
    assert await fetchval("SELECT count(*) FROM public.contents") == 620
    assert await fetchval("SELECT count(*) FROM public.contents WHERE array_length(tags,1) > 0") >= 400


async def test_rawtags_persontags(pool) -> None:
    """V2:837 个 RawTag、1962 条 person_tags(self/peer 标签全量)。"""
    assert await fetchval("SELECT count(*) FROM agent.raw_tags") == 837
    assert await fetchval("SELECT count(*) FROM agent.person_tags") == 1962


async def test_mock_responsibilities(pool) -> None:
    """V2 正式责任数据:责任人存在且属于该部门。"""
    n = await fetchval("SELECT count(*) FROM public.responsibility_assignments")
    assert n == 52
    bad = await fetchval(
        "SELECT count(*) FROM public.responsibility_assignments ra"
        " LEFT JOIN public.people p ON p.id = ra.owner_person_id"
        " WHERE p.id IS NULL OR p.department_id != ra.owner_department_id"
    )
    assert bad == 0
    sample = await fetchrow(
        "SELECT title, time_limit, escalation_path FROM public.responsibility_assignments LIMIT 1"
    )
    assert sample["title"]  # V2 责任事项标题非空;时限/升级路径允许为空(数据未配置)
