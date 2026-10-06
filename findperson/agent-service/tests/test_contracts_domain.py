"""模块 04:概念/证据/OKF/MCP 契约测试。"""
from app.contracts.agent_state import UserContext
from app.contracts.concept import (
    Concept, ConceptStatus, LinkDecision, MappingType, PersonConceptEvidence,
    RawTag, RelationType, ReviewAction, TagConceptMap,
)
from app.contracts.evidence import EvidenceType, PersonEvidence
from app.contracts.mcp import McpRequest, McpTool, ResponsibilityRecord
from app.contracts.okf import OkfMetadata, OkfStatus, OkfType, RagChunk


def test_rawtag_normalize_and_preserve() -> None:
    """RawTag 原文保留,规范化只用于判重(§7.1)。"""
    tag = RawTag(tag_id="tag-1", text="  AgentOS  ", normalized_text=RawTag.normalize("  AgentOS  "))
    assert tag.text == "  AgentOS  "          # 原文不被覆盖
    assert tag.normalized_text == "agentos"   # 规范化用于统一实体


def test_concept_candidate_isolated() -> None:
    """Candidate Concept 与正式 Concept 状态隔离(§7.5)。"""
    c = Concept(concept_id="candidate-prompt-platform", canonical_name="",
                suggested_name="Prompt管理平台", status=ConceptStatus.CANDIDATE,
                source_tags=["Prompt平台", "提示词平台"])
    assert c.status == ConceptStatus.CANDIDATE
    assert c.status != ConceptStatus.ACTIVE


def test_mapping_requires_type() -> None:
    """映射必须带 mapping_type 与 generated_by(§7.4 验收)。"""
    m = TagConceptMap(map_id="m-1", tag_id="tag-1", concept_id="concept-agent-platform",
                      mapping_type=MappingType.EXACT_ALIAS, confidence=0.99, generated_by="rule")
    assert m.mapping_type == MappingType.EXACT_ALIAS
    assert {d.value for d in LinkDecision} == {"LINK_EXISTING", "CREATE_CANDIDATE", "AMBIGUOUS", "REJECT"}


def test_person_concept_evidence_not_responsible_for() -> None:
    """自填证据 relation_type 不得为 responsible_for(§7.9/§9.2)。"""
    e = PersonConceptEvidence(person_id="p-0001", concept_id="concept-agent-platform",
                              source_raw_tag="AgentOS", confidence=0.96)
    assert e.relation_type == "self_declared_scope"
    assert e.relation_type != "responsible_for"


def test_relation_whitelist() -> None:
    """Concept 关系为白名单(§7.7),含 routes_to。"""
    assert RelationType.ROUTES_TO.value == "routes_to"
    assert len(RelationType) == 9


def test_review_actions_complete() -> None:
    """审核动作覆盖文档 5 种(§7.5)。"""
    assert len(ReviewAction) == 5


def test_person_evidence_keeps_semantics() -> None:
    """不同证据类型语义分层,不是一个浮点数(§12.1)。"""
    formal = PersonEvidence(person_id="p-1", relation_type="formal_assignment",
                            evidence_type=EvidenceType.FORMAL_ASSIGNMENT,
                            source_type="okf_responsibility", confidence=1.0)
    article = PersonEvidence(person_id="p-1", relation_type="article_expertise",
                             evidence_type=EvidenceType.INFERRED_FROM_ARTICLE,
                             source_type="okf_content", confidence=0.7)
    assert formal.evidence_type != article.evidence_type
    assert len(EvidenceType) == 6


def test_okf_metadata_13_fields_and_hash() -> None:
    """OKF 元数据 13 必备字段(§10.1),content_hash 可计算且稳定。"""
    meta = OkfMetadata(type=OkfType.RESPONSIBILITY, id="responsibility-dify-platform",
                       title="Dify平台运维", source_type="public.responsibility_assignments",
                       source_id="ra-001", owner_department_id=3)
    h1 = meta.compute_hash("Dify平台由智能平台部负责维护。")
    h2 = meta.compute_hash("Dify平台由智能平台部负责维护。")
    assert h1 == h2 and len(h1) == 64
    assert meta.status == OkfStatus.DRAFT  # 未发布前是 draft


def test_rag_chunk_fields() -> None:
    """Chunk 输出字段符合 §10.7。"""
    c = RagChunk(chunk_id="c-1", document_id="d-1", section_path="职责", content="...", token_count=42)
    assert c.token_count == 42


def test_mcp_request_requires_user_context() -> None:
    """MCP 调用强制携带 user_context 与 trace_id(§12.1)。"""
    req = McpRequest(tool=McpTool.GET_RESPONSIBILITY,
                     params={"concept_id": "concept-dify"},
                     user_context=UserContext(user_id="p-0001"),
                     trace_id="t-1")
    assert req.user_context.user_id == "p-0001"
    assert len(McpTool) == 8  # 8 个只读工具


def test_responsibility_record_fields() -> None:
    """正式责任记录包含受理/责任部门/时限/转办/升级/来源/版本(§9.4)。"""
    r = ResponsibilityRecord(responsibility_id="resp-1", title="Dify平台运维",
                             owner_department="智能平台部", time_limit="4小时",
                             escalation_path="部门负责人→分管领导", version=2)
    assert r.version == 2
