import os

from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = None

# ── 首问责任平台：三 schema 配置 ──
# 在 autogenerate 时包含 public / agent / rag 三个 schema
# 运行时通过 connect_args 设置 search_path
DB_SCHEMAS = ["public", "agent", "rag"]


def include_object(obj, name, type_, reflected, compare_to):
    """过滤不需要迁移的对象（如第三方扩展）"""
    if type_ == "table" and name.startswith("pg_"):
        return False
    return True


def _db_password() -> str:
    """数据库口令一律由环境变量提供（不入库）；缺失时给出明确提示。"""
    password = os.environ.get("DB_PASSWORD")
    if not password:
        raise RuntimeError(
            "缺少 DB_PASSWORD：请在 .env 中配置数据库口令后再执行 alembic 迁移"
        )
    return password


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    if url:
        url = url.replace("${DB_PASSWORD}", _db_password())
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema="public",
        include_schemas=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    section = config.get_section(config.config_ini_section, {})
    # 展开 alembic.ini 中的 ${DB_PASSWORD}
    url = section.get("sqlalchemy.url", "")
    if url:
        section["sqlalchemy.url"] = url.replace(
            "${DB_PASSWORD}", _db_password()
        )

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={
            "options": f"-c search_path={','.join(DB_SCHEMAS)}"
        },
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema="public",
            include_schemas=True,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
