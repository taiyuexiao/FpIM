"""全局配置:从 .env 读取,所有模块统一经此入口取配置,密钥不写死在代码里。"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置,对应 V1.2 §23 待确认事项中的可替换 Adapter 配置。"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1/chat/completions"
    llm_model: str = "deepseek-chat"
    llm_use_mock: bool = False
    llm_timeout_ms: int = 30000

    # Embedding
    # provider: mock(离线确定性) / fastembed(本地 ONNX,仅 ≤1024 维模型)
    #           / openai_compatible(行内 OpenAI 兼容服务,如 text-embedding-v4,1536 维)
    embedding_use_mock: bool = False  # 兼容旧开关;为 True 时等价 provider=mock
    embedding_provider: str = "mock"
    embedding_base_url: str = ""      # OpenAI 兼容服务地址,如 https://dashscope.aliyuncs.com/compatible-mode/v1
    embedding_api_key: str = ""
    embedding_model_path: str = ""    # fastembed 本地 ONNX 模型目录(可选)
    embedding_model: str = "text-embedding-v4"
    rag_embedding_dim: int = 1536     # RAG 向量空间:与仓库 knowledge-service 对齐 1536
    concept_embedding_dim: int = 512  # Concept 独立向量空间(仅 Agent 内部使用)
    rag_embedding_model: str = "text-embedding-v4"
    concept_embedding_model: str = "BAAI/bge-small-zh-v1.5"

    # 用户反馈回流:排序微调权重(0 关闭;正/负反馈按此上限调整候选得分)
    feedback_rank_weight: float = 0.1

    # PostgreSQL
    pghost: str = "localhost"
    pgport: int = 5432
    pgdatabase: str = "shouwenzeren_v2"
    pguser: str = "postgres"
    pgpassword: str = ""
    legacy_pgdatabase: str = "shouwenzeren"

    # 服务
    app_host: str = "127.0.0.1"
    app_port: int = 8100

    # CORS:前端 Vite dev 端口(逗号分隔;改端口时须与 backend/.env 的 CORS_ORIGINS 同步)
    agent_cors_origins: str = (
        "http://localhost:5173,http://localhost:5174,http://localhost:5175,"
        "http://127.0.0.1:5173,http://127.0.0.1:5174,http://127.0.0.1:5175"
    )

    # OKF 仓库
    okf_repo_dir: str = "knowledge-okf"

    # MCP
    mcp_use_mock: bool = True
    mcp_timeout_ms: int = 3000

    @property
    def pg_dsn(self) -> str:
        """SQLAlchemy asyncpg DSN。"""
        return (
            f"postgresql+asyncpg://{self.pguser}:{self.pgpassword}"
            f"@{self.pghost}:{self.pgport}/{self.pgdatabase}"
        )


@lru_cache
def get_settings() -> Settings:
    """配置单例。"""
    return Settings()
