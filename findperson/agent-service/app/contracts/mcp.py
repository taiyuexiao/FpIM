"""Knowledge MCP 契约(V1.2 §12.1):8 个只读工具的输入/输出 Schema。

Agent 不直连 rag schema,所有知识访问经 MCP;调用强制携带可信 user_context。
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.contracts.agent_state import UserContext


class McpTool(str, Enum):
    """8 个只读知识工具(V1.2 §12.1)。"""

    SEARCH_KNOWLEDGE = "search_knowledge"
    GET_DOCUMENT = "get_document"
    GET_RESPONSIBILITY = "get_responsibility"
    GET_PERSON_PROFILE = "get_person_profile"
    GET_PROCESS = "get_process"
    FIND_RELATED_KNOWLEDGE = "find_related_knowledge"
    LIST_SOURCES = "list_sources"
    KNOWLEDGE_HEALTH = "knowledge_health"


class McpRequest(BaseModel):
    """MCP 调用统一请求。user_context 强制携带(§12.1:无 user_context 的调用被拒绝)。"""

    tool: McpTool
    params: dict[str, Any] = Field(default_factory=dict)
    user_context: UserContext
    trace_id: str


class RagHit(BaseModel):
    """RAG 检索命中(§10.9 Hybrid Retriever 产出)。"""

    document_id: str
    chunk_id: str
    document_type: str
    score: float
    content: str
    source_uri: str = ""
    version: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)  # chunk 元数据(含 owner/author_person_id 等)


class ResponsibilityRecord(BaseModel):
    """正式责任记录(§9.4 Formal Responsibility Retriever 输出)。"""

    responsibility_id: str
    title: str
    intake_department: str = ""        # 受理部门
    owner_department: str = ""         # 最终责任部门
    owner_person_id: str = ""          # 责任人
    owner_role: str = ""               # 责任岗位
    time_limit: str = ""               # 时限
    transfer_condition: str = ""       # 转办条件
    escalation_path: str = ""          # 升级路径
    source_uri: str = ""
    version: int = 1


class McpResponse(BaseModel):
    """MCP 统一响应。ok=False 时 error 为统一错误码字符串。"""

    ok: bool = True
    tool: McpTool
    data: Any = None
    error: str | None = None
    degraded: bool = False
    trace_id: str = ""
