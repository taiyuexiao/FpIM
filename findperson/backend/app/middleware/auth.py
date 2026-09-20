"""JWT 认证中间件(integration 分支补全)。

解析 Authorization: Bearer <token>,注入 request.state.user_id / user_role,
供 middleware/deps.py 的 get_current_user 使用。
公开路径(登录/健康/文档)直接放行。
"""
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.requests import Request

from ..core.config import settings

PUBLIC_PREFIXES = ("/api/v1/auth/login", "/docs", "/redoc", "/openapi.json", "/health")
PUBLIC_EXACT = {"/"}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or path in PUBLIC_EXACT or path.startswith(PUBLIC_PREFIXES):
            return await call_next(request)
        # AGUI 代理由 agent-service 自行鉴权(Demo 适配器),这里放行转发
        if path.startswith("/api/v1/agui"):
            return await call_next(request)
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"message": "Not authenticated"})
        try:
            payload = jwt.decode(auth[7:], settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
            request.state.user_id = payload.get("sub")
            request.state.user_role = payload.get("role", "")
        except JWTError:
            return JSONResponse(status_code=401, content={"message": "登录状态已失效"})
        return await call_next(request)
