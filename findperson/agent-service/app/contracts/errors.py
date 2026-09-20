"""统一错误模型(V1.2 §14.5)。

所有模块抛出/返回错误时必须使用这里的错误码;
HTTP 层与 SSE 层分别把 AgentError 转换为对应协议错误(V1.2 §5.1 验收:建流前/建流后错误分别处理)。
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ErrorCode(str, Enum):
    """V1.2 §14.5 定义的 12 类错误。"""

    INPUT_ERROR = "INPUT_ERROR"
    AUTH_ERROR = "AUTH_ERROR"
    INTENT_ERROR = "INTENT_ERROR"
    CONCEPT_ERROR = "CONCEPT_ERROR"
    RETRIEVAL_ERROR = "RETRIEVAL_ERROR"
    MCP_ERROR = "MCP_ERROR"
    RAG_ERROR = "RAG_ERROR"
    LLM_ERROR = "LLM_ERROR"
    RANK_ERROR = "RANK_ERROR"
    TIMEOUT = "TIMEOUT"
    DEGRADED = "DEGRADED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorPayload(BaseModel):
    """对外返回的统一错误体。"""

    code: ErrorCode
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None
    degraded: bool = False


class AgentError(Exception):
    """Agent 主链统一异常。

    - code:统一错误码
    - message:人类可读信息
    - detail:结构化上下文(不得包含敏感信息)
    - degraded:是否为降级结果(降级不是失败,但需要显式标记)
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        detail: dict[str, Any] | None = None,
        degraded: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}
        self.degraded = degraded

    def to_payload(self, trace_id: str | None = None) -> ErrorPayload:
        """转换为对外错误体。"""
        return ErrorPayload(
            code=self.code,
            message=self.message,
            detail=self.detail,
            trace_id=trace_id,
            degraded=self.degraded,
        )


# 常用错误的便捷构造函数,保证各模块错误格式一致

def input_error(message: str, **detail: Any) -> AgentError:
    return AgentError(ErrorCode.INPUT_ERROR, message, detail=detail)


def auth_error(message: str = "未认证或权限不足", **detail: Any) -> AgentError:
    return AgentError(ErrorCode.AUTH_ERROR, message, detail=detail)


def llm_error(message: str, **detail: Any) -> AgentError:
    return AgentError(ErrorCode.LLM_ERROR, message, detail=detail)


def timeout_error(message: str, **detail: Any) -> AgentError:
    return AgentError(ErrorCode.TIMEOUT, message, detail=detail)


def degraded_error(message: str, **detail: Any) -> AgentError:
    return AgentError(ErrorCode.DEGRADED, message, detail=detail, degraded=True)
