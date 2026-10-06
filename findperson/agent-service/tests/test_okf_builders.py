"""模块 21:PersonProfile 白名单 + 责任发布链端到端测试。"""
from pathlib import Path

import pytest
import pytest_asyncio

from app.okf.builders import (
    PERSON_PROFILE_ALLOWED, build_person_profile_doc, build_responsibility_doc,
)
from app.okf.document import from_markdown
from app.okf.publisher import OkfPublisher, OkfValidator
from app.okf.repository import OkfRepository

pytestmark = pytest.mark.asyncio(loop_scope="module")

REPO_DIR = Path(__file__).resolve().parent.parent / "knowledge-okf"


def test_person_profile_whitelist() -> None:
    """PersonProfile 只含白名单字段;raw_tags/concept_ids 绝不写入(§10.4 红线)。"""
    person = {
        "id": "p-0001", "name": "王丹", "department": "数据管理与应用部",
        "role": "数据治理专员", "self_portrait": "负责数据治理相关工作。",
        "department_id": 3,
        # 以下字段绝不应进入 OKF
        "raw_tags": ["数据治理"], "concept_ids": ["concept-x"], "password_hash": "x",
    }
    doc = build_person_profile_doc(person, reviews_text="工作认真。")
    text_body = doc.body
    assert "数据治理相关工作" in text_body
    assert "raw_tags" not in text_body and "concept_ids" not in text_body
    assert "password_hash" not in text_body
    # extra 也不夹带
    assert "raw_tags" not in str(doc.extra)
    # 白名单本身符合 §10.4
    assert set(PERSON_PROFILE_ALLOWED) == {"name", "department", "role", "self_portrait"}


def test_person_profile_publishable() -> None:
    """构建的 PersonProfile 能通过六步校验链。"""
    person = {
        "id": "p-0001", "name": "王丹", "department": "数据管理与应用部",
        "role": "数据治理专员", "self_portrait": "负责数据治理相关工作。",
        "department_id": 3,
    }
    doc = build_person_profile_doc(person)
    doc.metadata.status = doc.metadata.status.PUBLISHED
    doc.metadata.content_hash = "x"
    assert OkfValidator().validate(doc, known_ids=set()) == []


def test_responsibility_doc_full_fields() -> None:
    """责任文档含受理/责任部门/责任人/时限/转办/升级(§9.4/§10.5)。"""
    ra = {
        "id": "ra-0001", "title": "Dify平台运维", "description": "平台维护",
        "owner_department_id": 3, "owner_person_id": "p-0001",
        "owner_role": "运维工程师", "time_limit": "4小时",
        "transfer_condition": "涉及模型服务转交", "escalation_path": "部门负责人→分管领导",
    }
    doc = build_responsibility_doc(
        ra, intake_department="智能平台部", owner_department="智能平台部", owner_name="张三")
    for keyword in ("受理部门", "责任部门", "责任人", "时限", "转办条件", "升级路径"):
        assert keyword in doc.body
    assert doc.extra["escalation_path"] == "部门负责人→分管领导"
    assert doc.metadata.source_uri == "public.responsibility_assignments/ra-0001"


async def test_real_repo_published_counts() -> None:
    """端到端(scripts/publish_okf.py 已跑):V2 数据集 944 份 Published 可追溯(§19 阶段 3 验收)。"""
    if not REPO_DIR.exists():
        pytest.skip("knowledge-okf 未生成,先运行 scripts/publish_okf.py")
    repo = OkfRepository(REPO_DIR)
    docs = await repo.list_published()
    assert len(docs) == 944
    by_type = {}
    for d in docs:
        by_type[d.metadata.type.value] = by_type.get(d.metadata.type.value, 0) + 1
    assert by_type == {"responsibilities": 52, "people": 252, "contents": 620, "departments": 20}
    # 每份可反查业务来源(§10.2 验收)
    for d in docs:
        assert d.metadata.source_type and d.metadata.source_id
        assert d.metadata.content_hash and d.metadata.version >= 1


async def test_real_repo_person_profile_no_tags() -> None:
    """真实仓库中的 PersonProfile 不含动态标签(§10.4)。"""
    if not REPO_DIR.exists():
        pytest.skip("knowledge-okf 未生成")
    repo = OkfRepository(REPO_DIR)
    doc = await repo.get_latest("person-p-0001")
    assert doc is not None
    assert "raw_tags" not in doc.body
    assert "concept" not in doc.body.lower() or "concept_id" not in doc.body
