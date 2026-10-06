"""模块 22:Chunker 测试。"""
from app.contracts.okf import OkfDocument, OkfMetadata, OkfType, Visibility
from app.rag.chunker import Chunker, _split_long_text


def _doc(doc_type: OkfType, doc_id: str, body: str, extra: dict | None = None) -> OkfDocument:
    return OkfDocument(
        metadata=OkfMetadata(
            type=doc_type, id=doc_id, title="测试文档", version=2,
            visibility=Visibility.DEPARTMENT, sensitivity=1,
            source_type="public.x", source_id="x-1",
            source_uri="public.x/x-1", owner_department_id=3,
            content_hash="h123",
        ),
        body=body,
        extra=extra or {},
    )


def test_responsibility_chunking() -> None:
    """责任事项按字段切:定义/责任部门/时限/转办/升级各自成块(§10.7)。"""
    body = ("Dify平台运维由智能平台部负责。\n\n主要职责:平台维护。\n\n"
            "- 受理部门:智能平台部\n- 责任部门:智能平台部\n- 责任人:张三(运维工程师)\n"
            "- 时限:4小时\n- 转办条件:涉及模型服务转交\n- 升级路径:部门负责人→分管领导")
    chunks = Chunker().chunk(_doc(OkfType.RESPONSIBILITY, "responsibility-x", body))
    paths = {c.section_path for c in chunks}
    assert "定义" in paths and "时限" in paths and "升级路径" in paths
    assert all(c.metadata["sensitivity"] == 1 for c in chunks)  # 权限元数据不丢
    assert all(c.metadata["okf_version"] == 2 for c in chunks)  # 版本元数据不丢


def test_person_chunking() -> None:
    """人物按段落标题切(自我介绍/评价分开)。"""
    body = ("王丹,数据管理与应用部数据治理专员。\n\n自我介绍:\n负责数据治理相关工作。\n\n"
            "同事评价(聚合):\n工作认真负责。")
    chunks = Chunker().chunk(_doc(OkfType.PEOPLE, "person-x", body))
    paths = {c.section_path for c in chunks}
    assert any("自我介绍" in p for p in paths)
    assert any("同事评价" in p for p in paths)


def test_long_text_sentence_split_with_overlap() -> None:
    """长文章 >500 字按句子续切,保留 overlap(§10.7)。"""
    sentence = "这是一个用于测试分块的句子,内容围绕数据平台建设展开。"
    body = "## 章节一\n" + sentence * 40  # ~1200 字
    chunks = Chunker().chunk(_doc(OkfType.CONTENT, "content-x", body))
    assert len(chunks) >= 2
    # 相邻 chunk 有重叠内容
    c0, c1 = chunks[0].content, chunks[1].content
    assert c1[:20] in c0 or c0[-20:] in c1 or any(
        c0[i:i + 15] in c1 for i in range(len(c0) - 40, len(c0) - 15))


def test_chunk_ids_and_metadata_complete() -> None:
    """chunk_id 稳定规则;metadata 含权限/版本/来源(§10.7 验收)。"""
    chunks = Chunker().chunk(_doc(OkfType.CONTENT, "content-y", "第一段。\n\n第二段。"))
    assert chunks[0].chunk_id == "content-y-c000"
    for c in chunks:
        for key in ("okf_type", "okf_version", "content_hash", "source_uri",
                    "owner_department_id", "visibility", "sensitivity"):
            assert key in c.metadata, f"chunk metadata 缺 {key}"
        assert c.token_count > 0
