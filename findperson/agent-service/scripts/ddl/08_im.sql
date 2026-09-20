-- IM 即时通讯内核(独立 schema,可重复执行)
-- 链路: AI 搜人 → 一键发起会话 → 沟通全程留痕 → 标记解决/未解决 → 沉淀进报表
--
-- 设计约束(与主方案一致):
--   1) 参与者统一用 public.user2.id(TEXT),与 issues.user_id / assignee_person_id 同源,不做 id 转换
--   2) 消息与问题同库同事务 —— 报表口径恒等于聊天记录
--   3) 会话内 last_read_seq 供红点(会被覆盖);问题侧首次已读写 issue_events(唯一索引兜底,永不覆盖)
--   4) 不引入好友关系:任何两人可直接建单聊
--
-- 用法: docker exec -i swzr-pg psql -U swzr_admin -d <db> < 08_im.sql

CREATE SCHEMA IF NOT EXISTS im;

-- ============================================================
-- 1) 会话
-- ============================================================
CREATE TABLE IF NOT EXISTS im.conversations (
    id              BIGSERIAL PRIMARY KEY,
    type            TEXT        NOT NULL,           -- direct 单聊 / group 群聊(≤100 人)
    direct_key      TEXT,                           -- 单聊去重键:两个 user_id 升序拼接;群聊为 NULL
    title           TEXT,                           -- 群名;单聊留空(前端显示对方姓名)
    owner_id        TEXT,                           -- 群主(user2.id);单聊为空
    created_by      TEXT        NOT NULL,           -- 建会话的人
    -- 问题关联:一个会话可聊出多个问题(1:N),这里的 issue_id 是"主问题"锚点
    issue_id        BIGINT,
    last_seq        BIGINT      NOT NULL DEFAULT 0, -- 会话内消息序号分配器
    last_message_id BIGINT,
    last_message_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 单聊唯一:同两人只有一条单聊(空 direct_key 不参与唯一,群聊不受影响)
CREATE UNIQUE INDEX IF NOT EXISTS uq_conv_direct_key ON im.conversations(direct_key) WHERE direct_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_conv_last_msg ON im.conversations(last_message_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_conv_issue ON im.conversations(issue_id) WHERE issue_id IS NOT NULL;

-- ============================================================
-- 2) 会话成员
-- ============================================================
CREATE TABLE IF NOT EXISTS im.conversation_members (
    conversation_id      BIGINT      NOT NULL REFERENCES im.conversations(id) ON DELETE CASCADE,
    user_id              TEXT        NOT NULL,
    member_role          TEXT        NOT NULL DEFAULT 'member',  -- owner 群主 / member 成员
    last_read_seq        BIGINT      NOT NULL DEFAULT 0,         -- 已读游标(供红点,可覆盖)
    last_read_at         TIMESTAMPTZ,
    unread_count         INTEGER     NOT NULL DEFAULT 0,         -- 冗余未读数,免每次 COUNT
    muted                BOOLEAN     NOT NULL DEFAULT false,
    pinned               BOOLEAN     NOT NULL DEFAULT false,     -- 置顶会话
    joined_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    left_at              TIMESTAMPTZ,
    PRIMARY KEY (conversation_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_member_user ON im.conversation_members(user_id) WHERE left_at IS NULL;

-- ============================================================
-- 3) 消息
-- ============================================================
CREATE TABLE IF NOT EXISTS im.messages (
    id              BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT      NOT NULL REFERENCES im.conversations(id) ON DELETE CASCADE,
    seq             BIGINT      NOT NULL,           -- 会话内严格递增序号(排序/增量拉取的唯一依据)
    sender_id       TEXT        NOT NULL,
    msg_type        TEXT        NOT NULL,           -- text|image|file|audio|video|system
                                                    -- |issue_card|resolve_confirm|report_card
    content         JSONB       NOT NULL DEFAULT '{}'::jsonb,  -- {"text":"..."} / {"url":..,"name":..,"size":..}
    client_msg_id   TEXT,                           -- 客户端幂等键:同发送方重复提交只落一条
    reply_to_id     BIGINT,
    issue_id        BIGINT,                         -- 该条消息挂到哪个问题(用于"从消息立项/留痕")
    revoked         BOOLEAN     NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_msg_conv_seq       ON im.messages(conversation_id, seq);
-- 幂等:同一发送方 + 同一 client_msg_id 只会存在一条
CREATE UNIQUE INDEX IF NOT EXISTS uq_msg_client_idem    ON im.messages(sender_id, client_msg_id) WHERE client_msg_id IS NOT NULL;
CREATE INDEX        IF NOT EXISTS idx_msg_conv_id_desc  ON im.messages(conversation_id, id DESC);
CREATE INDEX        IF NOT EXISTS idx_msg_issue          ON im.messages(issue_id) WHERE issue_id IS NOT NULL;

-- ============================================================
-- 4) 附件(内容寻址,本地磁盘物理存储)
-- ============================================================
CREATE TABLE IF NOT EXISTS im.attachments (
    id            BIGSERIAL PRIMARY KEY,
    sha256        TEXT        NOT NULL,             -- 内容哈希:天然去重 + 秒传
    ext           TEXT,
    mime          TEXT,
    size_bytes    BIGINT      NOT NULL DEFAULT 0,
    original_name TEXT,
    rel_path      TEXT        NOT NULL,             -- {yyyy}/{mm}/{sha前2位}/{sha256}.{ext}
    uploader_id   TEXT,
    ref_count     INTEGER     NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_attach_sha ON im.attachments(sha256);

-- ============================================================
-- 5) 与问题闭环打通
-- ============================================================
-- 问题 → 会话:发起会话时回填,使"该问题在哪聊的"可一键跳转
ALTER TABLE public.issues ADD COLUMN IF NOT EXISTS conversation_id BIGINT;
CREATE INDEX IF NOT EXISTS idx_issues_conversation ON public.issues(conversation_id) WHERE conversation_id IS NOT NULL;
-- 被问方的会话视角(个人待办:我作为责任人被问了哪些)
ALTER TABLE public.issues ADD COLUMN IF NOT EXISTS first_read_at TIMESTAMPTZ;
ALTER TABLE public.issues ADD COLUMN IF NOT EXISTS first_response_at TIMESTAMPTZ;

-- 首次已读事件"不可覆盖"由数据库兜底:
-- 同一问题 + 同一人 + read 事件只允许一条,应用层无需判重
CREATE UNIQUE INDEX IF NOT EXISTS uq_ev_read_per_actor
    ON public.issue_events(issue_id, operator_id)
    WHERE event_type = 'read' AND operator_id IS NOT NULL;
