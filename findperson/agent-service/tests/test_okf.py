"""模块 19/20:OKF Publisher 校验链 + Repository 版本管理测试。"""
import pytest
import pytest_asyncio

from app.contracts.okf import OkfDocument, OkfMetadata, OkfStatus, OkfType, Visibility
from app.okf.document import from_markdown, to_markdown
from app.okf.publisher import OkfPublisher, OkfValidator
from app.okf.repository import OkfRepository

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("okf") / "knowledge-okf"
    r = OkfRepository(root)
    await r.ensure_git_initialized()
    return r


def _doc(doc_id: str = "responsibility-dify-platform",
         title: str = "Dify平台运维", body: str = "Dify平台由智能平台部负责维护。") -> OkfDocument:
    return OkfDocument(
        metadata=OkfMetadata(
            type=OkfType.RESPONSIBILITY, id=doc_id, title=title,
            status=OkfStatus.PUBLISHED, visibility=Visibility.INTERNAL, sensitivity=0,
            source_type="public.responsibility_assignments", source_id="ra-mock-0001",
            source_uri=f"public.responsibility_assignments/ra-mock-0001",
            owner_department_id=3,
        ),
        body=body,
    )


# ---------------- 序列化(模块 19)----------------

def test_document_roundtrip() -> None:
    """frontmatter + 正文序列化往返,13 字段与 extra 完整。"""
    doc = _doc()
    doc.metadata.content_hash = doc.metadata.compute_hash(doc.body)
    doc.extra = {"time_limit": "4小时"}
    text = to_markdown(doc)
    restored = from_markdown(text)
    assert restored.metadata.id == "responsibility-dify-platform"
    assert restored.metadata.type == OkfType.RESPONSIBILITY
    assert restored.metadata.content_hash == doc.metadata.content_hash
    assert restored.extra["time_limit"] == "4小时"
    assert "智能平台部" in restored.body


def test_validator_schema_and_stable_id() -> None:
    """校验链:缺字段/坏 ID/坏敏感级全部被拦(§10.2)。"""
    v = OkfValidator()
    good = _doc()
    good.metadata.content_hash = "x"
    assert v.validate(good, known_ids=set()) == []
    bad = _doc(doc_id="Bad_ID_大写")
    bad.metadata.content_hash = "x"
    errors = v.validate(bad, known_ids=set())
    assert any("stable_id" in e for e in errors)
    bad2 = _doc()
    bad2.metadata.content_hash = "x"
    bad2.metadata.sensitivity = 9
    bad2.extra = {"related_okf_ids": ["not-exists-id"]}
    errors2 = v.validate(bad2, known_ids=set())
    assert any("sensitivity" in e for e in errors2)
    assert any("link" in e for e in errors2)


# ---------------- 发布 + 版本管理(模块 19/20)----------------

async def test_publish_and_incremental_skip(repo) -> None:
    """首次发布 v1;内容未变跳过(增量判断);内容变化升 v2(§10.2/§10.6)。"""
    pub = OkfPublisher(repo)
    r1 = await pub.publish(_doc())
    assert r1.published and r1.version == 1 and r1.changed

    r2 = await pub.publish(_doc())  # 相同内容
    assert r2.published and not r2.changed and r2.version == 1

    r3 = await pub.publish(_doc(body="Dify平台由智能平台部负责维护。主要职责:平台运行维护、用户问题处理。"))
    assert r3.published and r3.changed and r3.version == 2


async def test_publish_validation_failure_no_pollution(repo) -> None:
    """校验失败不写入仓库(§10.2:发布失败不能污染当前可查询版本)。"""
    pub = OkfPublisher(repo)
    bad = _doc(doc_id="responsibility-bad-one")
    bad.metadata.source_id = ""     # Source 校验必挂
    result = await pub.publish(bad)
    assert not result.published
    assert result.errors
    assert await repo.get_latest("responsibility-bad-one") is None


async def test_history_diff_rollback(repo) -> None:
    """版本历史/Diff/回滚(§10.3)。"""
    doc_id = "responsibility-dify-platform"
    history = await repo.history(doc_id)
    assert len(history) >= 2  # v1 + v2 两次 commit
    first_commit = history[-1]["commit"]
    second_commit = history[0]["commit"]

    diff = await repo.diff(doc_id, first_commit, second_commit)
    assert "主要职责" in diff  # v2 新增内容出现在 diff

    await repo.rollback(doc_id, first_commit)
    restored = await repo.get_latest(doc_id)
    assert "主要职责" not in restored.body  # 回到 v1 内容
    # 恢复 v2 供后续测试/使用
    await repo.rollback(doc_id, second_commit)
