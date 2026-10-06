-- 02_agent.sql —— Agent 动态语义层 + 运行态(V1.2 §17 agent schema)
-- RawTag/PersonTag/Concept/映射/关系/审核队列 + 运行日志。
-- 注意:Concept 向量 1024 维,与 rag 层 1536 维为两个独立向量空间(§10.8)。

CREATE TABLE IF NOT EXISTS agent.raw_tags (
    tag_id          TEXT PRIMARY KEY,
    text            TEXT NOT NULL,              -- 用户原始文本,不得被 Concept 覆盖
    normalized_text TEXT NOT NULL UNIQUE,       -- 规范化判重
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent.person_tags (
    person_tag_id   TEXT PRIMARY KEY,
    person_id       TEXT NOT NULL,              -- 逻辑引用 public.people,不建外键跨 schema 约束写操作
    tag_id          TEXT NOT NULL REFERENCES agent.raw_tags(tag_id),
    source          TEXT NOT NULL DEFAULT 'self',  -- self / peer_review / admin
    approval        TEXT NOT NULL DEFAULT 'approved',  -- 他人标签需本人放行:pending / approved / rejected
    created_by      TEXT NOT NULL DEFAULT '',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent.concepts (
    concept_id      TEXT PRIMARY KEY,
    canonical_name  TEXT NOT NULL DEFAULT '',
    concept_type    TEXT NOT NULL DEFAULT 'domain',
    description     TEXT NOT NULL DEFAULT '',
    scope_department_id INTEGER,
    status          TEXT NOT NULL DEFAULT 'active',  -- seed/candidate/active/deprecated
    embedding       vector(512),                -- Concept 向量空间(512 维,bge-small-zh)
    embedding_model TEXT NOT NULL DEFAULT '',
    suggested_name  TEXT NOT NULL DEFAULT '',   -- Candidate 专有
    source_tags     TEXT[] NOT NULL DEFAULT '{}',  -- Candidate 专有
    version         INTEGER NOT NULL DEFAULT 1,
    valid_from      TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to        TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS agent.concept_aliases (
    alias_id        TEXT PRIMARY KEY,
    concept_id      TEXT NOT NULL REFERENCES agent.concepts(concept_id),
    alias           TEXT NOT NULL,              -- 规范化别名
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (concept_id, alias)
);

CREATE TABLE IF NOT EXISTS agent.tag_concept_map (
    map_id          TEXT PRIMARY KEY,
    tag_id          TEXT NOT NULL REFERENCES agent.raw_tags(tag_id),
    concept_id      TEXT NOT NULL REFERENCES agent.concepts(concept_id),
    mapping_type    TEXT NOT NULL,              -- exact_alias/near_alias/instance_of/...
    confidence      REAL NOT NULL DEFAULT 0,
    generated_by    TEXT NOT NULL,              -- rule/llm/human
    review_status   TEXT NOT NULL DEFAULT 'auto_approved',
    reason          TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tag_id, concept_id)
);

CREATE TABLE IF NOT EXISTS agent.concept_relations (
    relation_id     TEXT PRIMARY KEY,
    src_concept_id  TEXT NOT NULL REFERENCES agent.concepts(concept_id),
    dst_concept_id  TEXT NOT NULL REFERENCES agent.concepts(concept_id),
    relation_type   TEXT NOT NULL,              -- 白名单 9 种
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (src_concept_id, dst_concept_id, relation_type)
);

CREATE TABLE IF NOT EXISTS agent.concept_review_queue (
    review_id       TEXT PRIMARY KEY,
    item_type       TEXT NOT NULL,              -- low_confidence_mapping/ambiguous_mapping/candidate_concept/anomaly
    payload         JSONB NOT NULL DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'pending',
    resolution      JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at     TIMESTAMPTZ
);

-- 查询侧概念链接日志(§7.6 评测、§15.1 trace 串联)
CREATE TABLE IF NOT EXISTS agent.query_concept_logs (
    id              BIGSERIAL PRIMARY KEY,
    trace_id        TEXT NOT NULL,
    query           TEXT NOT NULL,
    link_trace      JSONB NOT NULL DEFAULT '[]',
    resolved_concepts JSONB NOT NULL DEFAULT '[]',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent.agent_traces (
    trace_id        TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL,
    session_id      TEXT,
    user_id         TEXT,
    original_query  TEXT NOT NULL DEFAULT '',
    total_latency_ms REAL,
    degraded        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent.agent_node_spans (
    id              BIGSERIAL PRIMARY KEY,
    trace_id        TEXT NOT NULL REFERENCES agent.agent_traces(trace_id),
    node_name       TEXT NOT NULL,
    latency_ms      REAL,
    status          TEXT NOT NULL DEFAULT 'ok',
    degraded        BOOLEAN NOT NULL DEFAULT FALSE,
    error_code      TEXT,
    llm_tokens      INTEGER NOT NULL DEFAULT 0,
    tool_calls      JSONB NOT NULL DEFAULT '[]',
    input_summary   TEXT NOT NULL DEFAULT '',
    output_summary  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS agent.agent_sessions (
    session_id      TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    state           JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 推荐记录(§功能详细说明v4:问题摘要/候选人员/排序证据/会话/消息/运行标识)
CREATE TABLE IF NOT EXISTS agent.agent_recommendation_logs (
    id              BIGSERIAL PRIMARY KEY,
    trace_id        TEXT NOT NULL,
    session_id      TEXT,
    message_id      TEXT,
    user_id         TEXT NOT NULL DEFAULT '',
    query_summary   TEXT NOT NULL DEFAULT '',   -- 问题摘要(非原文,可追溯可统计)
    query_type      TEXT,
    rank_policy     TEXT,
    ranked_candidates JSONB NOT NULL DEFAULT '[]',  -- 含排序证据
    gate_decision   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent.mcp_call_logs (
    id              BIGSERIAL PRIMARY KEY,
    trace_id        TEXT NOT NULL,
    tool            TEXT NOT NULL,
    params          JSONB NOT NULL DEFAULT '{}',
    ok              BOOLEAN NOT NULL DEFAULT TRUE,
    latency_ms      REAL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 用户反馈(§功能详细说明v4:回答与推荐卡片有帮助/没帮助互斥反馈,可取消;
-- 必须关联 session/message/trace;轻量内容反馈不替代推荐反馈)
CREATE TABLE IF NOT EXISTS agent.feedback_events (
    id              BIGSERIAL PRIMARY KEY,
    trace_id        TEXT NOT NULL DEFAULT '',
    session_id      TEXT,
    message_id      TEXT,
    user_id         TEXT NOT NULL DEFAULT '',
    feedback_type   TEXT NOT NULL,              -- like/dislike/report/interaction
    target_type     TEXT NOT NULL DEFAULT '',   -- answer/person/content/session
    target_id       TEXT NOT NULL DEFAULT '',
    value           TEXT NOT NULL DEFAULT '',   -- up/down/...(interaction 事件可为事件名)
    reason          TEXT NOT NULL DEFAULT '',   -- 点踩原因(点踩原因配置见 /agent/feedback/reasons)
    payload         JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- 同一用户对同一对象同一消息仅保留一种反馈(互斥;再次点击同值=取消,由应用层 DELETE)
CREATE UNIQUE INDEX IF NOT EXISTS idx_feedback_mutex
    ON agent.feedback_events(user_id, target_type, target_id, message_id)
    WHERE feedback_type IN ('like','dislike');
CREATE INDEX IF NOT EXISTS idx_feedback_target ON agent.feedback_events(target_type, target_id);

-- AGUI 会话消息持久化(问答页会话历史)
CREATE TABLE IF NOT EXISTS agent.agui_messages (
    id              BIGSERIAL PRIMARY KEY,
    message_id      TEXT NOT NULL,
    session_id      TEXT NOT NULL,
    run_id          TEXT NOT NULL DEFAULT '',
    trace_id        TEXT NOT NULL DEFAULT '',
    user_id         TEXT NOT NULL DEFAULT '',
    role            TEXT NOT NULL,              -- user/assistant
    text            TEXT NOT NULL DEFAULT '',
    analysis        JSONB,
    cards           JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_agui_messages_session ON agent.agui_messages(session_id, id);

CREATE INDEX IF NOT EXISTS idx_person_tags_person ON agent.person_tags(person_id) WHERE is_active;
CREATE INDEX IF NOT EXISTS idx_person_tags_tag ON agent.person_tags(tag_id) WHERE is_active;
CREATE INDEX IF NOT EXISTS idx_concepts_name_trgm ON agent.concepts USING gin (canonical_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_aliases_trgm ON agent.concept_aliases USING gin (alias gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_tcm_concept ON agent.tag_concept_map(concept_id);
CREATE INDEX IF NOT EXISTS idx_tcm_tag ON agent.tag_concept_map(tag_id);
CREATE INDEX IF NOT EXISTS idx_node_spans_trace ON agent.agent_node_spans(trace_id);
