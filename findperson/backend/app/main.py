"""首问责任平台 — FastAPI 入口"""
import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .core.config import settings
from .core.database import engine
from .api.v1 import auth, me, people, contents, reviews, admin, departments, sessions
from .api.v1 import agui_proxy, mail, issues, im
from .middleware.auth import AuthMiddleware
from .services import mail_inbox
from .ws import im_gateway


def _ensure_issue_tables() -> None:
    """启动兜底:确保问题跟踪/知识沉淀表存在(幂等)。

    DDL 单一来源:agent-service/scripts/ddl/07_issues_knowledge.sql;
    找不到该文件时跳过(全新环境请先执行该 DDL)。
    """
    ddl_path = (Path(__file__).resolve().parents[2]
                / "agent-service" / "scripts" / "ddl" / "07_issues_knowledge.sql")
    if not ddl_path.exists():
        return
    try:
        with engine.begin() as conn:
            conn.execute(text(ddl_path.read_text(encoding="utf-8")))
    except Exception as exc:  # noqa: BLE001 —— 建表失败不阻断启动(表通常已由 DDL 脚本建好)
        logging.getLogger("app").warning("问题跟踪表自检跳过: %s", exc)


def _ensure_im_tables() -> None:
    """启动兜底:确保 IM 内核表(im schema)存在(幂等)。

    DDL 单一来源:agent-service/scripts/ddl/08_im.sql;
    找不到该文件时跳过(全新环境请先执行该 DDL)。
    """
    ddl_path = (Path(__file__).resolve().parents[2]
                / "agent-service" / "scripts" / "ddl" / "08_im.sql")
    if not ddl_path.exists():
        return
    try:
        with engine.begin() as conn:
            conn.execute(text(ddl_path.read_text(encoding="utf-8")))
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("app").warning("IM 表自检跳过: %s", exc)



@asynccontextmanager
async def lifespan(_app: FastAPI):
    """启动兜底:确保 email 列存在(幂等)。

    本项目 User 模型映射 user2(users 为历史同构表),两表都要补;
    缺列时 SQLAlchemy 一查即挂(人员列表整体不可用)。
    显式迁移见 scripts/add_user_email.py,此处仅兜底,任何环境拉代码即可启动。
    """
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE IF EXISTS public.users ADD COLUMN IF NOT EXISTS email VARCHAR(128)"))
        # user2 在部署环境可能是 users 的兼容视图(视图不可 ALTER):仅当它是实体表时补列
        conn.execute(text(
            "DO $$ BEGIN "
            "  IF EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "             WHERE n.nspname = 'public' AND c.relname = 'user2' AND c.relkind = 'r') THEN "
            "    ALTER TABLE public.user2 ADD COLUMN IF NOT EXISTS email VARCHAR(128); "
            "  END IF; "
            "END $$;"
        ))
    _ensure_issue_tables()
    _ensure_im_tables()
    # 收信轮询(IMAP 配置齐全且 MAIL_POLL_SECONDS>0 时生效)
    stop = asyncio.Event()
    poller = asyncio.create_task(mail_inbox.run_mail_poller(stop))
    try:
        yield
    finally:
        stop.set()
        poller.cancel()
        with suppress(asyncio.CancelledError):
            await poller


app = FastAPI(
    title="首问责任平台 API",
    description="First-Responsibility Platform Backend",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# 操作审计中间件（ADM-06）：先 add（Starlette 后 add 的为外层，先 add 的执行更靠内层），
# 依赖 AuthMiddleware 注入的 request.state.user_id；只审计已登录用户的写操作
from .middleware.audit import AuditMiddleware  # noqa: E402
app.add_middleware(AuditMiddleware)

# JWT 认证中间件(integration 分支补全:注入 request.state.user_id/user_role)
app.add_middleware(AuthMiddleware)

# CORS — 开发模式：允许任意 localhost 端口
origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth.router, prefix="/api/v1")
app.include_router(me.router, prefix="/api/v1")
app.include_router(people.router, prefix="/api/v1")
app.include_router(contents.router, prefix="/api/v1")
app.include_router(reviews.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(departments.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(mail.router, prefix="/api/v1")  # 邮件草稿(DeepSeek)+SMTP 发送
app.include_router(issues.router, prefix="/api/v1")  # 问题跟踪 + 知识沉淀
app.include_router(im.router, prefix="/api/v1")  # IM 即时通讯(REST:历史/建会话/上传)
app.include_router(im_gateway.router, prefix="/api/v1")  # IM 实时网关(WebSocket: /api/v1/ws/im)
app.include_router(agui_proxy.router, prefix="/api/v1")  # AGUI 事件代理 → agent-service


@app.get("/")
def root():
    return {"service": "首问责任平台", "version": "0.1.0", "status": "running"}


@app.get("/health")
def health():
    return {"status": "ok"}
