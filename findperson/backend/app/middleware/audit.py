"""操作审计日志中间件（P3 ADM-06）：记录已登录用户的关键写操作到 public.audit_logs"""
import re

from starlette.middleware.base import BaseHTTPMiddleware

from ..core.database import SessionLocal
from ..models.admin import AuditLog

# 需要审计的 HTTP 方法
_AUDIT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# 跳过审计的路径前缀（登录/探活/文档等）
_AUDIT_SKIP_PREFIX = ("/health", "/docs", "/redoc", "/openapi.json", "/api/v1/auth/")

# method → 基础动作
_METHOD_ACTION = {"POST": "create", "PUT": "update", "PATCH": "update", "DELETE": "delete"}

# 资源名复数 → 单数
_RESOURCE_SINGULAR = {
    "contents": "content",
    "people": "person",
    "reviews": "review",
    "sessions": "session",
    "departments": "department",
}

# 路径解析：/api/v1/contents/C00001 → resource=contents, rid=C00001
_RESOURCE_RE = re.compile(r"/api/v1/(?P<resource>[a-z]+)(?:/(?P<rid>[^/]+))?")


def _infer_action(method: str, path: str) -> str:
    """从路径关键字覆盖基础动作映射，使审计语义更准确"""
    if "/audit" in path:
        return "audit"
    if "/submit" in path:
        return "submit"
    if "/pin" in path:
        return "pin"
    if "/change-password" in path or path.endswith("/password"):
        return "change_password"
    return _METHOD_ACTION.get(method, method.lower())


class AuditMiddleware(BaseHTTPMiddleware):
    """在业务处理完成后，把关键写操作落一条 audit_logs 记录。

    注意：本中间件在 AuthMiddleware 之后（内层）执行，依赖其注入的 request.state.user_id。
    """

    async def dispatch(self, request, call_next):
        response = await call_next(request)

        method = request.method
        path = request.url.path
        if method in _AUDIT_METHODS and not path.startswith(_AUDIT_SKIP_PREFIX):
            user_id = getattr(request.state, "user_id", None)
            if user_id:  # 只审计已登录用户的操作
                m = _RESOURCE_RE.match(path)
                resource = m.group("resource") if m else None
                log = AuditLog(
                    user_id=user_id,
                    action=_infer_action(method, path),
                    resource_type=_RESOURCE_SINGULAR.get(resource, resource),
                    resource_id=(m.group("rid") if m else None),
                    method=method,
                    path=path,
                    ip=request.client.host if request.client else None,
                )
                db = SessionLocal()
                try:
                    db.add(log)
                    db.commit()
                except Exception:
                    db.rollback()
                finally:
                    db.close()

        return response
