"""/agent/chat 请求接入与 AG-UI/SSE(V1.2 §5.1 / §13.2)。

§5.1:身份验证 → user_context 构建 → trace_id/run_id → 输入长度校验
      → AgentState 初始化 → Orchestrator 启动。
      HTTP 建流前错误与 SSE 建流后错误分别处理。
      Agent 不接受客户端自行声明角色作为权限依据。

§13.2:统一事件 run_started / text_delta / recommendation_cards / citations /
      clarification / run_error / run_finished;每次运行带
      sessionId / runId / messageId / traceId。

V1 身份适配器[Demo]:X-User-Id 头 → public.people 校验;不存在则 401。
正式 JWT/网关在真实联调阶段(模块 30)替换,接入接口不变。
"""
from __future__ import annotations

import json
import uuid
import asyncio

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.agent.chain import build_orchestrator
from app.agent.memory import load_history
from app.contracts.agent_state import AgentState, RequestState, UserContext
from app.contracts.errors import ErrorCode, auth_error, input_error
from app.contracts.trace import new_trace_id
from app.core import db
from app.core.observability import get_metrics, persist_trace

router = APIRouter(prefix="/agent", tags=["agent"])

MAX_QUERY_LEN = 500


class ChatRequest(BaseModel):
    """对话请求体。"""

    query: str = Field(min_length=1, max_length=MAX_QUERY_LEN)
    session_id: str | None = None


class TagLinkRequest(BaseModel):
    """标签→概念链接请求(backend 写侧调用)。"""

    text: str = Field(min_length=1, max_length=64)


@router.post("/tags/link")
async def link_tag(body: TagLinkRequest):
    """标签→概念链接(§7.4 五级召回 + LLM 受约束消歧;backend 写侧同步调用)。"""
    from app.agent.concept_governance import RawTagConceptLinker
    return await RawTagConceptLinker().link_tag(body.text)


async def _build_user_context(x_user_id: str | None) -> UserContext:
    """[Demo 身份适配器] X-User-Id → 可信 user_context。未认证不进入 Agent(§5.1)。"""
    if not x_user_id:
        raise auth_error("缺少 X-User-Id 头")
    row = await db.fetchrow(
        "SELECT id, name, department, department_id FROM public.people"
        " WHERE id = $1 AND status = 'active'",
        x_user_id,
    )
    if not row:
        raise auth_error(f"用户不存在或已停用: {x_user_id}")
    return UserContext(
        user_id=row["id"], name=row["name"],
        department=row["department"], department_id=row["department_id"],
        roles=["user"], sensitivity_level=0,
    )


def _event(event: str, data: dict, ids: dict) -> dict:
    """AG-UI 事件封装(统一携带四个 ID,§13.2)。"""
    return {"event": event, "data": json.dumps({**ids, **data}, ensure_ascii=False)}


@router.post("/chat")
async def agent_chat(
    body: ChatRequest, request: Request, x_user_id: str | None = Header(default=None),
):
    """Agent 对话入口(SSE 流式)。"""
    # ---- HTTP 建流前错误:直接 4xx,不建流(§5.1) ----
    try:
        user_context = await _build_user_context(x_user_id)
    except Exception as e:
        payload = e.to_payload() if hasattr(e, "to_payload") else None  # AgentError
        raise HTTPException(
            status_code=401,
            detail=payload.model_dump() if payload else str(e),
        ) from e

    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail=input_error("query 不能为空").to_payload().model_dump())

    ids = {
        "sessionId": body.session_id or uuid.uuid4().hex,
        "runId": uuid.uuid4().hex,
        "messageId": uuid.uuid4().hex,
        "traceId": new_trace_id(),
    }

    state = AgentState(
        request=RequestState(
            trace_id=ids["traceId"], run_id=ids["runId"], session_id=ids["sessionId"],
            user_context=user_context, original_query=query,
            normalized_query=" ".join(query.split()),
            # 多轮记忆:显式传 session_id 时注入对话历史
            history=await load_history(body.session_id) if body.session_id else [],
        )
    )
    state.trace.trace_id = ids["traceId"]
    state.trace.run_id = ids["runId"]
    state.trace.session_id = ids["sessionId"]

    async def event_stream():
        yield _event("run_started", {"query": query}, ids)
        try:
            orchestrator = build_orchestrator()
            # 全链超时保护(§19 阶段 8:Timeout;P95 复杂诊断 < 6s,全链上限 30s)
            final = await asyncio.wait_for(orchestrator.run(state), timeout=30.0)
            await persist_trace(final)          # §15.1 trace 落库
            get_metrics().record_request(final)  # §15.2 指标
            answer = final.response.final_answer
            # text_delta:分块流式下发
            chunk = 24
            for i in range(0, len(answer), chunk):
                yield _event("text_delta", {"delta": answer[i : i + chunk]}, ids)
            if final.response.clarification:
                yield _event("clarification", {"text": final.response.clarification}, ids)
            if final.response.recommendation_cards:
                yield _event("recommendation_cards",
                             {"cards": final.response.recommendation_cards}, ids)
            if final.response.citations:
                yield _event("citations", {"citations": final.response.citations}, ids)
            yield _event("run_finished", {
                "degraded": final.execution.degraded,
                "gate_decision": final.ranking.gate_decision.value if final.ranking.gate_decision else None,
                "rank_policy": final.ranking.rank_policy or None,
                "total_latency_ms": final.execution.total_latency_ms,
            }, ids)
        except asyncio.TimeoutError:
            yield _event("run_error", {"code": ErrorCode.TIMEOUT.value,
                                       "message": "全链执行超时(30s)"}, ids)
            yield _event("run_finished", {"degraded": True}, ids)
        except Exception as e:  # noqa: BLE001 —— SSE 建流后错误:run_error 事件(§5.1)
            code = e.code.value if hasattr(e, "code") else ErrorCode.INTERNAL_ERROR.value
            yield _event("run_error", {"code": code, "message": str(e)[:300]}, ids)
            yield _event("run_finished", {"degraded": True}, ids)

    return EventSourceResponse(event_stream())


@router.get("/metrics")
async def agent_metrics() -> dict:
    """指标快照(JSON)+ Prometheus 文本经 /metrics 纯文本端点(挂主 app)。"""
    m = get_metrics()
    return {"counters": m.counters,
            "latency_avg_ms": {k: round(v / max(m.latency_count[k], 1), 2)
                               for k, v in m.latency_sum.items()}}
