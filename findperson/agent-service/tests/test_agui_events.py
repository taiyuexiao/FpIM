"""AGUI 事件构建单元测试(纯逻辑,不依赖 DB)。

契约来源:前端 src/services/agui/normalizer.js + stores/agui.js;
推荐理由必须指出命中依据(v4 §四),不得只显示"匹配度高"。
"""
from app.agui.service import _build_reasons, _event


def test_event_envelope() -> None:
    """事件统一携带 type + sessionId/runId/messageId(v3 §3.3 归属约束)。"""
    ids = {"sessionId": "s1", "runId": "r1", "messageId": "m1"}
    e = _event("text_delta", ids, delta="你好")
    assert e["type"] == "text_delta"
    assert e["sessionId"] == "s1" and e["runId"] == "r1" and e["messageId"] == "m1"
    assert e["delta"] == "你好"


def test_reasons_formal_responsibility() -> None:
    candidate = {
        "has_formal": True,
        "responsibilities": [{"title": "Dify平台运维", "owner_department": "科技部"}],
        "evidences": [{"evidence_type": "formal_assignment", "detail": {}}],
    }
    reasons = _build_reasons(candidate)
    assert any("正式责任" in r and "Dify平台运维" in r for r in reasons)


def test_reasons_self_tag_and_article() -> None:
    candidate = {
        "has_formal": False,
        "evidences": [
            {"evidence_type": "explicit_self_tag", "detail": {"source_raw_tag": "RAG"}},
            {"evidence_type": "inferred_from_article", "detail": {"title_hint": "K8s 部署实践"}},
        ],
    }
    reasons = _build_reasons(candidate)
    assert any("负责领域命中:RAG" in r for r in reasons)
    assert any("K8s 部署实践" in r for r in reasons)
    assert not any("匹配度高" in r for r in reasons)


def test_reasons_fallback_not_empty() -> None:
    assert _build_reasons({"evidences": []}) == ["综合证据匹配"]


def test_reasons_dedup_and_limit() -> None:
    candidate = {
        "evidences": [
            {"evidence_type": "explicit_self_tag", "detail": {"source_raw_tag": "RAG"}},
            {"evidence_type": "explicit_self_tag", "detail": {"source_raw_tag": "RAG"}},
        ],
    }
    reasons = _build_reasons(candidate)
    assert len(reasons) == len(set(reasons)) <= 4
