-- 问题跟踪 + 知识沉淀 + 邮件往来(后端业务表,可重复执行)
-- 链路: 对话同步问题 → 邮件联系(发出/收回信) → LLM 分析 + 用户确认 → 沉淀候选 → FAQ
-- 用法: cat 07_issues_knowledge.sql | docker exec -i swzr-pg psql -U swzr_admin -d shouwenzeren_newdb

-- 1) 问题跟踪(个人中心「我的问题」)
CREATE TABLE IF NOT EXISTS public.issues (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,                              -- 提问人(user2.id)
    session_id TEXT,
    message_id TEXT,                                    -- agent.agui_messages.message_id(用户消息)
    question TEXT NOT NULL,                             -- 原始问题
    summary TEXT,                                       -- LLM 归一化问题(一句话)
    status TEXT NOT NULL DEFAULT 'not_contacted',       -- not_contacted 未联系 / processing 处理中 / resolved 已解决 / unresolved 未解决
    assignee_person_id TEXT,                            -- 责任人(默认取该轮首推)
    repeated_count INTEGER NOT NULL DEFAULT 1,          -- 同一问题被重复提问的次数(沉淀打分用)
    source TEXT NOT NULL DEFAULT 'sync',                -- sync 对话同步 / manual 手动 / mail 邮件
    last_action_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    resolution_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_issues_user ON public.issues(user_id, status, last_action_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_issues_message ON public.issues(message_id) WHERE message_id IS NOT NULL;

-- 2) 问题时间线(同步/改状态/发信/收信/备注)
CREATE TABLE IF NOT EXISTS public.issue_events (
    id BIGSERIAL PRIMARY KEY,
    issue_id BIGINT NOT NULL REFERENCES public.issues(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,                           -- created / status_changed / mail_sent / mail_received / mail_analyzed / note
    detail TEXT,
    payload JSONB,
    operator_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_issue_events_issue ON public.issue_events(issue_id, created_at);

-- 3) 邮件往来(发出与收回,与问题关联)
CREATE TABLE IF NOT EXISTS public.mail_messages (
    id BIGSERIAL PRIMARY KEY,
    direction TEXT NOT NULL,                            -- out 发出 / in 收到
    message_id TEXT,                                    -- Message-ID 头
    in_reply_to TEXT,
    from_addr TEXT,
    to_addr TEXT,
    subject TEXT,
    body_text TEXT,
    issue_id BIGINT REFERENCES public.issues(id) ON DELETE SET NULL,
    sent_by TEXT,                                       -- 发信人(user2.id;out 才有)
    analysis JSONB,                                     -- LLM 对回信的分析(reply_relevant/seems_resolved/suggested_status/reason)
    received_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_mail_message_id ON public.mail_messages(message_id) WHERE message_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_mail_issue ON public.mail_messages(issue_id, created_at DESC);

-- 4) 知识沉淀候选池(问答 → 待确认 FAQ/文章)
CREATE TABLE IF NOT EXISTS public.knowledge_candidates (
    id BIGSERIAL PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    summary TEXT,
    score INTEGER NOT NULL DEFAULT 0,
    signals JSONB,                                      -- 打分依据(解决/重复/点赞/点踩...)
    status TEXT NOT NULL DEFAULT 'pending',             -- pending / approved / rejected / merged
    source_issue_ids JSONB,                             -- [issue_id, ...]
    target_faq_id BIGINT,                               -- 确认成 FAQ 时指向 faqs.id
    target_content_id TEXT,                             -- 确认成文章草稿时指向 contents.id(如 C00319)
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- 老库补列(approve 二选一:FAQ / 文章草稿)
ALTER TABLE public.knowledge_candidates ADD COLUMN IF NOT EXISTS target_content_id TEXT;
CREATE INDEX IF NOT EXISTS idx_kc_status ON public.knowledge_candidates(status, score DESC);

-- 5) FAQ 知识条目(沉淀结果;后续由 OKF 发布进检索)
CREATE TABLE IF NOT EXISTS public.faqs (
    id BIGSERIAL PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    tags JSONB,
    owner_person_id TEXT,                               -- 责任人
    scope_department_ids JSONB,                         -- 可见范围(空=全公司)
    source TEXT,                                        -- issue / candidate / manual
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'published',           -- draft / published / archived
    asked_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_faqs_status ON public.faqs(status, updated_at DESC);
