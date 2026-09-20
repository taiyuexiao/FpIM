from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ⚠️ 凭据一律从 .env 注入，不入库（.gitignore 已排除 .env）
    # 下方默认值只用于缺失配置时的可读报错，不含任何真实口令
    DATABASE_URL: str = "postgresql://swzr_admin@localhost:5432/fpim_dev"
    # DSN 约定不带口令（凭据不落 DSN）；口令由 PGPASSWORD 提供，database.py 装配时注入
    PGPASSWORD: str = ""
    JWT_SECRET: str = "dev-insecure-secret-set-JWT_SECRET-in-env"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 480
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:5174"
    BCRYPT_ROUNDS: int = 12

    AGENT_SERVICE_URL: str = "http://127.0.0.1:8100"  # AGUI 事件代理转发目标(integration)

    # IM 附件存储(本地磁盘,内容寻址: {root}/{sha4}/{sha6}/{sha}.{ext})
    FPIM_FILE_ROOT: str = "/data/fpim/files"

    # 开发/测试用：种子账号统一登录口令。仅 conftest 与自测脚本读取，不入库
    SEED_PASSWORD: str = ""

    # 邮件草稿(DeepSeek,OpenAI 兼容接口);真实 key 放 .env(.gitignore 已排除,不入库)
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    DEEPSEEK_TIMEOUT_SECONDS: float = 30.0

    # SMTP 发信(行外经个人邮箱中继投递 @bosc.cn;投产可切行内中继,改配置即可)
    SMTP_HOST: str = "smtp.163.com"
    SMTP_PORT: int = 465  # 465=SSL;587/25=STARTTLS
    SMTP_USER: str = ""   # 发件邮箱
    SMTP_PASSWORD: str = ""  # SMTP 授权码(非登录密码)
    SMTP_FROM_NAME: str = "首问必答平台"  # 发件人显示名

    # 收信(IMAP:与 SMTP 同一邮箱的授权码;后端按 MAIL_POLL_SECONDS 轮询收件箱)
    IMAP_HOST: str = "imap.163.com"
    IMAP_PORT: int = 993
    IMAP_USER: str = ""
    IMAP_PASSWORD: str = ""
    MAIL_POLL_SECONDS: int = 60  # 轮询间隔(秒);0=关闭收信

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
