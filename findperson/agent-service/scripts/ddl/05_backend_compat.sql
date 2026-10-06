-- 05_backend_compat.sql —— backend 分支(FastAPI CRUD)对接兼容层
-- 原则:backend 代码零改动;users 为写侧事实源,people 由触发器同步(Agent 只读 people)。
-- 幂等:全部 IF NOT EXISTS / OR REPLACE,可重复执行。

-- ========== 1. departments 补齐 backend 所需列 ==========
ALTER TABLE public.departments ADD COLUMN IF NOT EXISTS level INTEGER NOT NULL DEFAULT 1;
ALTER TABLE public.departments ADD COLUMN IF NOT EXISTS leader_id TEXT;
ALTER TABLE public.departments ADD COLUMN IF NOT EXISTS responsibility TEXT;
ALTER TABLE public.departments ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE public.departments ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0;
ALTER TABLE public.departments ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
UPDATE public.departments SET sort_order = id WHERE sort_order = 0;

-- ========== 2. users(backend 写侧事实源) ==========
CREATE TABLE IF NOT EXISTS public.users (
    id               VARCHAR(32) PRIMARY KEY,
    account          VARCHAR(64) UNIQUE NOT NULL,
    name             VARCHAR(64) NOT NULL,
    password_hash    VARCHAR(256) NOT NULL,
    phone            VARCHAR(20),
    system_role      VARCHAR(32) NOT NULL DEFAULT '普通成员',
    department_id    INTEGER REFERENCES public.departments(id),
    role             VARCHAR(128),
    contact          VARCHAR(64),
    domains          TEXT[],
    self_portrait    TEXT,
    completeness     INTEGER DEFAULT 0,
    recommended_count INTEGER DEFAULT 0,
    active           BOOLEAN DEFAULT TRUE,
    last_login_at    TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ========== 3. users → people 同步触发器(Agent/OKF 只读 people) ==========
CREATE OR REPLACE FUNCTION public.sync_users_to_people() RETURNS trigger AS $$
BEGIN
    INSERT INTO public.people(id, account, phone, name, department, department_id,
                              role, role_type, contact, self_portrait, completeness,
                              status, updated_at)
    VALUES (NEW.id, NEW.account, NEW.phone, NEW.name,
            coalesce((SELECT name FROM public.departments WHERE id = NEW.department_id), ''),
            NEW.department_id, coalesce(NEW.role, ''), 'user', NEW.contact,
            coalesce(NEW.self_portrait, ''), coalesce(NEW.completeness, 0),
            CASE WHEN NEW.active THEN 'active' ELSE 'inactive' END, now())
    ON CONFLICT (id) DO UPDATE SET
        account        = EXCLUDED.account,
        phone          = EXCLUDED.phone,
        name           = EXCLUDED.name,
        department     = EXCLUDED.department,
        department_id  = EXCLUDED.department_id,
        role           = EXCLUDED.role,
        contact        = EXCLUDED.contact,
        self_portrait  = EXCLUDED.self_portrait,
        completeness   = EXCLUDED.completeness,
        status         = EXCLUDED.status,
        updated_at     = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_sync ON public.users;
CREATE TRIGGER trg_users_sync AFTER INSERT OR UPDATE ON public.users
    FOR EACH ROW EXECUTE FUNCTION public.sync_users_to_people();

-- ========== 4. contents 补齐 backend 所需列 ==========
ALTER TABLE public.contents ADD COLUMN IF NOT EXISTS summary TEXT NOT NULL DEFAULT '';
ALTER TABLE public.contents ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE public.contents ADD COLUMN IF NOT EXISTS pinned BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE public.contents ADD COLUMN IF NOT EXISTS published_at DATE;
ALTER TABLE public.contents ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ;
ALTER TABLE public.contents ADD COLUMN IF NOT EXISTS audit_trail JSONB NOT NULL DEFAULT '[]';
ALTER TABLE public.contents ADD COLUMN IF NOT EXISTS published_snapshot JSONB;
ALTER TABLE public.contents ADD COLUMN IF NOT EXISTS weekly_query_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE public.contents ADD COLUMN IF NOT EXISTS weekly_recommend_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE public.contents ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE;
-- V2 导入的存量内容:摘要取正文前 120 字,发布时间取创建日
UPDATE public.contents SET summary = left(body, 120) WHERE summary = '';
UPDATE public.contents SET published_at = created_at::date WHERE published_at IS NULL AND status = 'published';

-- ========== 5. 会话/消息/查询日志(backend 模型) ==========
CREATE TABLE IF NOT EXISTS public.sessions (
    id          VARCHAR(32) PRIMARY KEY,
    user_id     VARCHAR(32) NOT NULL REFERENCES public.users(id),
    title       VARCHAR(256) DEFAULT '新会话',
    summary     TEXT DEFAULT '',
    turn_count  INTEGER DEFAULT 0,
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.messages (
    id             VARCHAR(32) PRIMARY KEY,
    session_id     VARCHAR(32) NOT NULL REFERENCES public.sessions(id),
    user_id        VARCHAR(32) NOT NULL REFERENCES public.users(id),
    question       TEXT NOT NULL,
    intent         VARCHAR(64),
    reply_text     TEXT,
    confirm_status VARCHAR(16),
    action_type    VARCHAR(32),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.query_logs (
    id          SERIAL PRIMARY KEY,
    user_id     VARCHAR(32) REFERENCES public.users(id),
    query_type  VARCHAR(32) DEFAULT 'search',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ========== 6. peer_reviews 对齐 backend(补 tag_name;保留 Agent 侧 content 列) ==========
ALTER TABLE public.peer_reviews ADD COLUMN IF NOT EXISTS tag_name VARCHAR(64) NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_users_department ON public.users(department_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON public.sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_session ON public.messages(session_id);

-- ========== 7. 发布/变更事件(吸收 backend P5 优化) ==========
-- backend 在内容发布/变更/删除后写事件;agent-service 消费后增量重建 OKF/RAG 索引
CREATE TABLE IF NOT EXISTS rag.publish_events (
    id          BIGSERIAL PRIMARY KEY,
    event_type  TEXT NOT NULL,              -- content_published/content_changed/content_deleted
    resource_id TEXT NOT NULL,              -- 内容 ID
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending/consumed/failed
    created_by  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_publish_events_status ON rag.publish_events(status, id);
