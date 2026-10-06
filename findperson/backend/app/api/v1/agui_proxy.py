"""AGUI 代理(integration 分支新增)。

前端 reporter.js 经业务 HTTP 通道上报事件(POST {VITE_API_BASE_URL}/agui/events),
本路由把它转发给 agent-service,前端零改动。仅用标准库,不新增依赖。
"""
import json
import urllib.request

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ...core.config import settings

AGENT_SERVICE_URL = settings.AGENT_SERVICE_URL

router = APIRouter(prefix="/agui", tags=["agui-proxy"])


@router.post("/events")
async def forward_agui_event(request: Request):
    body = await request.body()
    req = urllib.request.Request(
        f"{AGENT_SERVICE_URL}/api/agui/events",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return JSONResponse(status_code=resp.status,
                                content=json.loads(resp.read().decode("utf-8")))
    except Exception as e:  # noqa: BLE001 —— agent-service 不可用时优雅降级(前端仅 console.warn)
        return JSONResponse(status_code=200, content={"ok": False, "forwarded": False, "detail": str(e)[:200]})


@router.get("/feedback/reasons")
async def forward_feedback_reasons():
    """点踩原因配置透传(agent-service /agent/feedback/reasons,实施方案v3 §3.2)。"""
    req = urllib.request.Request(f"{AGENT_SERVICE_URL}/agent/feedback/reasons", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return JSONResponse(status_code=resp.status,
                                content=json.loads(resp.read().decode("utf-8")))
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=200, content={"ok": False, "forwarded": False, "detail": str(e)[:200]})
