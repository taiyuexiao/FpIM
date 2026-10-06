from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import settings


def _with_password(url: str, password: str) -> str:
    """DSN 约定不带口令；若确实没有且 PGPASSWORD 已配置，则装配时注入。

    这样 .env 只写一份 PGPASSWORD，uvicorn / pytest / 脚本等所有入口都不用再额外 export。
    """
    if not password:
        return url
    parts = urlsplit(url)
    if parts.password:
        return url
    user = parts.username or ""
    host = parts.hostname or "localhost"
    netloc = f"{user}:{password}@{host}" + (f":{parts.port}" if parts.port else "")
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


engine = create_engine(
    _with_password(settings.DATABASE_URL, settings.PGPASSWORD),
    pool_pre_ping=True, pool_size=10, max_overflow=20,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI 依赖：获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
