"""管理看板"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...middleware.deps import require_admin, get_current_user
from ...models.user import User
from ...models.content import Content
from ...models.session import QueryLog

router = APIRouter(prefix="/admin", tags=["管理"])


@router.get("/dashboard", summary="Dashboard", description="管理看板概览")
def dashboard(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    people_count = db.query(sa_func.count(User.id)).scalar() or 0
    content_count = db.query(sa_func.count(Content.id)).filter(Content.is_deleted == False).scalar() or 0
    dept_count = db.query(sa_func.count(User.department_id.distinct())).scalar() or 0
    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=now.weekday())
    week_rec = db.query(sa_func.coalesce(sa_func.sum(Content.weekly_recommend_count), 0)).filter(
        Content.is_deleted == False
    ).scalar() or 0
    return {
        "peopleCount": people_count,
        "contentCount": content_count,
        "domainCount": dept_count,
        "weeklyRecommendationTotal": week_rec,
    }


@router.get("/metrics", summary="Metrics", description="管理看板核心指标（对齐前端 useAdminStore.metrics）")
def metrics(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    from sqlalchemy import text as sa_text
    people_count = db.query(sa_func.count(User.id)).scalar() or 0
    content_count = db.query(sa_func.count(Content.id)).filter(Content.is_deleted == False).scalar() or 0
    dept_count = db.query(sa_func.count(User.department_id.distinct())).scalar() or 0
    # 本周推荐量:Agent 推荐日志真实计数(content.weekly_recommend_count 无写入方,已弃用)
    week_rec = db.execute(sa_text(
        "SELECT COALESCE(sum(jsonb_array_length(ranked_candidates)),0)"
        " FROM agent.agent_recommendation_logs"
        " WHERE created_at >= date_trunc('week', now())"
    )).scalar() or 0
    return {
        "peopleCount": people_count,
        "contentCount": content_count,
        "domainCount": dept_count,
        "weeklyRecommendationTotal": int(week_rec),
    }


@router.get("/rankings/recommend", summary="Recommend Ranking", description="本周推荐热度排行 TOP5（对齐前端 useAdminStore.ranking）")
def recommend_ranking(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    # 本周推荐热度:Agent 推荐日志按候选人聚合(真实数据,替代无写入方的 weekly_recommend_count)
    from sqlalchemy import text as sa_text
    rows = db.execute(sa_text(
        "SELECT c->>'person_id' AS pid, count(*) AS value"
        " FROM agent.agent_recommendation_logs l,"
        "      jsonb_array_elements(l.ranked_candidates) c"
        " WHERE l.created_at >= date_trunc('week', now())"
        " GROUP BY 1 ORDER BY 2 DESC LIMIT 5"
    )).all()
    result = []
    for pid, value in rows:
        person = db.query(User).filter(User.id == pid).first()
        result.append({
            "person": {
                "id": pid,
                "name": person.name if person else "",
                "department": person.department.name if person and person.department else "",
                "role": person.role or "" if person else "",
            },
            "value": int(value),
        })
    return result


@router.get("/trends/activity", summary="Activity Trend", description="近 7 天活动趋势（对齐前端 useAdminStore.trend）")
def activity_trend(
    request: Request,
    week: str = Query("current", description="current | previous"),
    db: Session = Depends(get_db),
):
    require_admin(request)
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    if week == "previous":
        now -= timedelta(days=7)
    week_start = now - timedelta(days=now.weekday())
    # 周日活:Agent 运行轨迹真实计数(public query_logs 无写入方,已弃用)
    from sqlalchemy import text as sa_text
    trend = []
    for i in range(7):
        day_start = week_start + timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        count = db.execute(sa_text(
            "SELECT count(*) FROM agent.agent_traces WHERE created_at >= :s AND created_at < :e",
        ), {"s": day_start, "e": day_end}).scalar() or 0
        trend.append({"day": day_start.strftime("%m-%d"), "value": count, "percent": 0})
    max_val = max(t["value"] for t in trend) if trend else 1
    for t in trend:
        t["percent"] = round(t["value"] / max_val * 100) if max_val > 0 else 0
    return trend


@router.get("/statistics", summary="List Statistics", description="统计指标列表")
def list_statistics(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    return [
        {"key": "total_users", "label": "总用户数"},
        {"key": "total_contents", "label": "总内容数"},
        {"key": "total_reviews", "label": "总标签数"},
    ]


@router.get("/statistics/data", summary="Statistics Data", description="统计指标实时值列表")
def statistics_data(request: Request, db: Session = Depends(get_db)):
    """各指标的实时值汇总（一次返回，前端看板不用逐 key 轮询）。
    ⚠️ 必须声明在 /statistics/{metric_key} 之前，否则 "data" 会被路径参数吞掉。"""
    require_admin(request)
    from ...models.review import PeerReview
    return [
        {"key": "total_users", "label": "总用户数",
         "value": db.query(sa_func.count(User.id)).scalar() or 0},
        {"key": "total_contents", "label": "总内容数",
         "value": db.query(sa_func.count(Content.id)).filter(Content.is_deleted == False).scalar() or 0},
        {"key": "total_reviews", "label": "总标签数",
         "value": db.query(sa_func.count(PeerReview.id)).scalar() or 0},
    ]


@router.get("/audit-logs", summary="Audit Logs", description="操作审计日志（审计中间件落库）")
def audit_logs(request: Request, db: Session = Depends(get_db),
               limit: int = Query(default=50, ge=1, le=200)):
    require_admin(request)
    from ...models.admin import AuditLog
    q = db.query(AuditLog).order_by(AuditLog.id.desc())
    total = q.count()
    items = [{
        "id": row.id,
        "userId": row.user_id,
        "action": row.action,
        "resourceType": row.resource_type,
        "resourceId": row.resource_id,
        "method": row.method,
        "path": row.path,
        "detail": row.detail,
        "createdAt": row.created_at.isoformat() if row.created_at else None,
    } for row in q.limit(limit).all()]
    return {"total": total, "items": items}


@router.get("/statistics/{metric_key}", summary="Get Statistic Value", description="执行统计 SQL 获取实时值")
def get_statistic_value(metric_key: str, request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    if metric_key == "total_users":
        return {"key": metric_key, "value": db.query(sa_func.count(User.id)).scalar() or 0}
    elif metric_key == "total_contents":
        return {"key": metric_key, "value": db.query(sa_func.count(Content.id)).filter(Content.is_deleted == False).scalar() or 0}
    elif metric_key == "total_reviews":
        from ...models.review import PeerReview
        return {"key": metric_key, "value": db.query(sa_func.count(PeerReview.id)).scalar() or 0}
    return {"key": metric_key, "value": 0}


# ---------------------------------------------------------------- 推荐反馈可视化(验收:反馈数据进库 + 后台展示)

# 反馈分析模块仅对师沛琳开放(前端页签同款限制,此处做服务端强制)
FEEDBACK_ADMIN_ID = "P0004"


def _require_feedback_admin(request: Request, db: Session) -> None:
    from fastapi import HTTPException
    user = get_current_user(request, db)
    if user.id != FEEDBACK_ADMIN_ID:
        raise HTTPException(status_code=403, detail="反馈分析模块仅指定管理员可见")


@router.get("/feedback/summary", summary="Feedback Summary", description="推荐反馈汇总(有帮助率/趋势/点踩原因分布)")
def feedback_summary(request: Request, db: Session = Depends(get_db)):
    _require_feedback_admin(request, db)
    from sqlalchemy import text as sa_text
    totals = db.execute(sa_text(
        "SELECT feedback_type, count(*) AS n FROM agent.feedback_events"
        " WHERE feedback_type IN ('like','dislike') GROUP BY feedback_type"
    )).all()
    up = sum(int(r.n) for r in totals if r.feedback_type == "like")
    down = sum(int(r.n) for r in totals if r.feedback_type == "dislike")
    total = up + down
    # 近 7 天趋势(按自然日,连续 7 天补齐 0 值,保证前端 7 柱完整呈现)
    trend_rows = db.execute(sa_text(
        "SELECT to_char(d, 'MM-DD') AS day,"
        "       COALESCE(sum((e.feedback_type='like')::int),0) AS up,"
        "       COALESCE(sum((e.feedback_type='dislike')::int),0) AS down"
        " FROM generate_series("
        "   date_trunc('day', now() + interval '8 hours') - interval '6 days',"
        "   date_trunc('day', now() + interval '8 hours'), interval '1 day') d"
        " LEFT JOIN agent.feedback_events e"
        "   ON date_trunc('day', e.created_at + interval '8 hours') = d"
        "  AND e.feedback_type IN ('like','dislike')"
        " GROUP BY 1, d ORDER BY d"
    )).all()
    trend = [{"day": r.day, "up": int(r.up), "down": int(r.down)} for r in trend_rows]
    # 点踩原因分布(与趋势同窗口:近 7 天)
    reason_rows = db.execute(sa_text(
        "SELECT COALESCE(NULLIF(reason,''),'未填写') AS reason, count(*) AS n"
        " FROM agent.feedback_events WHERE feedback_type='dislike'"
        "   AND created_at >= now() - interval '7 days'"
        " GROUP BY 1 ORDER BY n DESC"
    )).all()
    return {
        "up": up, "down": down, "total": total,
        "helpfulRate": round(up / total * 100, 1) if total else 0,
        "trend": trend,
        "reasons": [{"reason": r.reason, "count": int(r.n)} for r in reason_rows],
    }


@router.get("/feedback/recent", summary="Feedback Recent", description="最近反馈明细(含用户问题与推荐人选)")
def feedback_recent(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    _require_feedback_admin(request, db)
    from sqlalchemy import text as sa_text
    rows = db.execute(sa_text(
        "SELECT e.id, e.created_at, e.user_id, u.name AS user_name,"
        "       e.feedback_type, e.reason, e.trace_id, e.message_id,"
        "       e.payload, l.query_summary, l.ranked_candidates"
        " FROM agent.feedback_events e"
        " LEFT JOIN public.user2 u ON u.id = e.user_id"
        " LEFT JOIN agent.agent_recommendation_logs l"
        "   ON l.trace_id = e.trace_id AND e.trace_id <> ''"
        "  AND l.message_id = e.message_id"
        " WHERE e.feedback_type IN ('like','dislike')"
        " ORDER BY e.created_at DESC LIMIT :limit"
    ), {"limit": limit}).all()
    import json as _json
    result = []
    for r in rows:
        payload = r.payload if isinstance(r.payload, dict) else (_json.loads(r.payload) if r.payload else {})
        ctx = payload.get("context") or payload
        # 推荐人选:优先反馈上下文里带的名单,否则从推荐日志取
        candidates = ctx.get("candidates") or []
        if not candidates and r.ranked_candidates:
            rc = r.ranked_candidates if isinstance(r.ranked_candidates, list) else _json.loads(r.ranked_candidates)
            candidates = [c.get("person_id", "") for c in rc[:5]]
        result.append({
            "id": r.id,
            "createdAt": (r.created_at + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
            "user": r.user_name or r.user_id,
            "question": ctx.get("question") or r.query_summary or "",
            "candidates": candidates,
            "value": "up" if r.feedback_type == "like" else "down",
            "reason": r.reason or "",
        })
    return result


# ---------------------------------------------------------------- Agent 可观测(验收:每轮问答全链路持久化 + 管理员工具)

@router.get("/traces", summary="Agent Traces", description="Agent 运行轨迹列表(分页/搜索)")
def list_traces(
    request: Request,
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    require_admin(request)
    from sqlalchemy import text as sa_text
    where = ""
    params: dict = {}
    if keyword:
        where = "WHERE (t.original_query ILIKE :kw OR u.name ILIKE :kw)"
        params["kw"] = f"%{keyword}%"
    total = db.execute(sa_text(
        f"SELECT count(*) FROM agent.agent_traces t"
        f" LEFT JOIN public.user2 u ON u.id = t.user_id {where}"), params).scalar() or 0
    rows = db.execute(sa_text(
        "SELECT * FROM ("
        " SELECT DISTINCT ON (t.trace_id) t.trace_id, t.created_at, t.original_query,"
        "        t.total_latency_ms, t.degraded,"
        "        u.name AS user_name, m.analysis, l.gate_decision, l.rank_policy"
        " FROM agent.agent_traces t"
        " LEFT JOIN public.user2 u ON u.id = t.user_id"
        " LEFT JOIN agent.agui_messages m ON m.trace_id = t.trace_id AND m.role = 'assistant'"
        " LEFT JOIN agent.agent_recommendation_logs l ON l.trace_id = t.trace_id"
        f" {where}"
        " ORDER BY t.trace_id, m.id NULLS LAST, l.id NULLS LAST"
        ") x ORDER BY x.created_at DESC LIMIT :limit OFFSET :offset"),
        {**params, "limit": page_size, "offset": (page - 1) * page_size}).all()
    import json as _json
    items = []
    for r in rows:
        analysis = r.analysis if isinstance(r.analysis, dict) else (_json.loads(r.analysis) if r.analysis else {})
        items.append({
            "traceId": r.trace_id,
            "createdAt": (r.created_at + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
            "query": r.original_query,
            "user": r.user_name or "",
            "latencyMs": round(r.total_latency_ms or 0),
            "degraded": r.degraded,
            "intent": (analysis or {}).get("intent") or "",
            "queryType": (analysis or {}).get("queryType") or "",
            "gateDecision": r.gate_decision or "",
            "rankPolicy": r.rank_policy or "",
        })
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/traces/{trace_id}", summary="Agent Trace Detail", description="单条轨迹全链路详情(节点/概念/RAG/MCP/推荐/回答/反馈)")
def trace_detail(trace_id: str, request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    from sqlalchemy import text as sa_text
    import json as _json

    trace = db.execute(sa_text(
        "SELECT t.trace_id, t.run_id, t.session_id, t.created_at, t.original_query,"
        "       t.total_latency_ms, t.degraded, u.name AS user_name"
        " FROM agent.agent_traces t LEFT JOIN public.user2 u ON u.id = t.user_id"
        " WHERE t.trace_id = :tid"), {"tid": trace_id}).first()
    if not trace:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="轨迹不存在")

    def _loads(v):
        return _json.loads(v) if isinstance(v, str) and v else (v or None)

    spans = db.execute(sa_text(
        "SELECT node_name, status, latency_ms, degraded, error_code, llm_tokens,"
        "       tool_calls, input_summary, output_summary"
        " FROM agent.agent_node_spans WHERE trace_id = :tid ORDER BY id"), {"tid": trace_id}).all()
    concept = db.execute(sa_text(
        "SELECT query, link_trace, resolved_concepts, created_at"
        " FROM agent.query_concept_logs WHERE trace_id = :tid ORDER BY id DESC LIMIT 1"),
        {"tid": trace_id}).first()
    mcp_calls = db.execute(sa_text(
        "SELECT tool, params, ok, latency_ms, created_at"
        " FROM agent.mcp_call_logs WHERE trace_id = :tid ORDER BY created_at"), {"tid": trace_id}).all()
    rec = db.execute(sa_text(
        "SELECT query_summary, query_type, rank_policy, ranked_candidates, gate_decision"
        " FROM agent.agent_recommendation_logs WHERE trace_id = :tid ORDER BY id DESC LIMIT 1"),
        {"tid": trace_id}).first()
    messages = db.execute(sa_text(
        "SELECT role, text, analysis, cards, created_at FROM agent.agui_messages"
        " WHERE trace_id = :tid ORDER BY id"), {"tid": trace_id}).all()
    feedbacks = db.execute(sa_text(
        "SELECT feedback_type, value, reason, target_type, target_id, created_at"
        " FROM agent.feedback_events WHERE trace_id = :tid ORDER BY id"), {"tid": trace_id}).all()

    return {
        "trace": {
            "traceId": trace.trace_id, "runId": trace.run_id, "sessionId": trace.session_id,
            "createdAt": (trace.created_at + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S") if trace.created_at else "",
            "query": trace.original_query, "user": trace.user_name or "",
            "latencyMs": round(trace.total_latency_ms or 0), "degraded": trace.degraded,
        },
        "spans": [{
            "node": s.node_name, "status": s.status, "latencyMs": round(s.latency_ms or 0, 1),
            "degraded": s.degraded, "errorCode": s.error_code, "llmTokens": s.llm_tokens,
            "toolCalls": _loads(s.tool_calls) or [], "input": s.input_summary, "output": s.output_summary,
        } for s in spans],
        "conceptLink": ({
            "query": concept.query,
            "linkTrace": _loads(concept.link_trace) or [],
            "resolvedConcepts": _loads(concept.resolved_concepts) or [],
        } if concept else None),
        "mcpCalls": [{
            "tool": m.tool, "params": _loads(m.params) or {}, "ok": m.ok,
            "latencyMs": round(m.latency_ms or 0, 1),
        } for m in mcp_calls],
        "recommendation": ({
            "querySummary": rec.query_summary, "queryType": rec.query_type,
            "rankPolicy": rec.rank_policy, "gateDecision": rec.gate_decision,
            "candidates": _loads(rec.ranked_candidates) or [],
        } if rec else None),
        "messages": [{
            "role": m.role, "text": m.text,
            "analysis": _loads(m.analysis), "cards": _loads(m.cards) or [],
        } for m in messages],
        "feedbacks": [{
            "type": f.feedback_type, "value": f.value, "reason": f.reason,
            "targetType": f.target_type, "targetId": f.target_id,
        } for f in feedbacks],
    }
