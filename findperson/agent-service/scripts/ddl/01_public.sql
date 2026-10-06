-- 01_public.sql —— 业务事实层(V1.2 §17 public schema)
-- 人员、部门、内容、评价、正式责任关系。Agent/LLM 不得直接覆盖这些事实。

CREATE TABLE IF NOT EXISTS public.departments (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    parent_id       INTEGER REFERENCES public.departments(id),
    path            TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS public.people (
    id              TEXT PRIMARY KEY,           -- p-0001 ...
    account         TEXT UNIQUE,
    phone           TEXT,
    name            TEXT NOT NULL,
    department      TEXT NOT NULL,
    department_id   INTEGER REFERENCES public.departments(id),
    role            TEXT NOT NULL,
    role_type       TEXT NOT NULL DEFAULT 'user',
    contact         TEXT,
    self_portrait   TEXT NOT NULL DEFAULT '',   -- 自画像正文(可进 OKF)
    completeness    INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'active',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.contents (
    id              TEXT PRIMARY KEY,           -- content-0001 ...
    title           TEXT NOT NULL,
    body            TEXT NOT NULL DEFAULT '',
    owner_id        TEXT REFERENCES public.people(id),
    content_type    TEXT NOT NULL DEFAULT 'article',
    tags            TEXT[] NOT NULL DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'published',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.peer_reviews (
    id              TEXT PRIMARY KEY,
    person_id       TEXT NOT NULL REFERENCES public.people(id),  -- 被评价人
    reviewer_id     TEXT REFERENCES public.people(id),           -- 评价人
    content         TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 正式责任关系:唯一事实源(V1.2 §10.5)。Agent 主路径不直读,经 OKF 发布。
CREATE TABLE IF NOT EXISTS public.responsibility_assignments (
    id                  TEXT PRIMARY KEY,       -- ra-0001 ...
    title               TEXT NOT NULL,          -- 责任事项,如 Dify平台运维
    description         TEXT NOT NULL DEFAULT '',
    intake_department_id INTEGER REFERENCES public.departments(id),  -- 受理部门
    owner_department_id  INTEGER REFERENCES public.departments(id),  -- 最终责任部门
    owner_person_id      TEXT REFERENCES public.people(id),          -- 责任人
    owner_role           TEXT NOT NULL DEFAULT '',                   -- 责任岗位
    time_limit           TEXT NOT NULL DEFAULT '',                   -- 时限
    transfer_condition   TEXT NOT NULL DEFAULT '',                   -- 转办条件
    escalation_path      TEXT NOT NULL DEFAULT '',                   -- 升级路径
    status               TEXT NOT NULL DEFAULT 'active',
    version              INTEGER NOT NULL DEFAULT 1,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_people_department ON public.people(department_id);
CREATE INDEX IF NOT EXISTS idx_contents_owner ON public.contents(owner_id);
CREATE INDEX IF NOT EXISTS idx_reviews_person ON public.peer_reviews(person_id);
CREATE INDEX IF NOT EXISTS idx_ra_owner ON public.responsibility_assignments(owner_person_id);
