-- 03_rag.sql —— RAG 在线检索层(V1.2 §17 rag schema)
-- OKF 派生的在线索引,不是事实源。RAG 向量 512 维(本地 fastembed bge-small-zh-v1.5,
-- 离线确定性;与 Concept 独立向量空间互不可比,§10.8)。

CREATE TABLE IF NOT EXISTS rag.rag_documents (
    document_id     TEXT NOT NULL,
    index_version   INTEGER NOT NULL,           -- 索引版本(§10.6 原子切换)
    okf_type        TEXT NOT NULL,              -- responsibilities/people/...
    title           TEXT NOT NULL DEFAULT '',
    okf_version     INTEGER NOT NULL,           -- 对应 OKF version
    content_hash    TEXT NOT NULL,              -- 对应 OKF content_hash
    source_uri      TEXT NOT NULL DEFAULT '',
    owner_department_id INTEGER,
    visibility      TEXT NOT NULL DEFAULT 'internal',  -- public/internal/restricted
    allowed_departments JSONB NOT NULL DEFAULT '[]',   -- visibility=restricted 时额外放行的部门 id
    sensitivity     INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'active',  -- active/invalidated
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (document_id, index_version)
);

CREATE TABLE IF NOT EXISTS rag.rag_chunks (
    chunk_id        TEXT NOT NULL,
    index_version   INTEGER NOT NULL,
    document_id     TEXT NOT NULL,
    section_path    TEXT NOT NULL DEFAULT '',
    content         TEXT NOT NULL,
    metadata        JSONB NOT NULL DEFAULT '{}',
    token_count     INTEGER NOT NULL DEFAULT 0,
    embedding       vector(512),                -- RAG 向量空间(512 维,bge-small-zh 本地模型)
    embedding_model TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (chunk_id, index_version)
);

CREATE TABLE IF NOT EXISTS rag.rag_index_jobs (
    job_id          TEXT PRIMARY KEY,
    job_type        TEXT NOT NULL,              -- incremental/full_rebuild
    index_version   INTEGER NOT NULL,
    status          TEXT NOT NULL DEFAULT 'running',  -- running/smoke_test/published/failed/rolled_back
    stats           JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at    TIMESTAMPTZ
);

-- 当前生效的索引版本(原子切换的落点)
CREATE TABLE IF NOT EXISTS rag.rag_index_pointer (
    id              INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    active_version  INTEGER NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO rag.rag_index_pointer (id, active_version) VALUES (1, 0)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS rag.rag_query_logs (
    id              BIGSERIAL PRIMARY KEY,
    trace_id        TEXT NOT NULL,
    query           TEXT NOT NULL,
    hits            JSONB NOT NULL DEFAULT '[]',
    latency_ms      REAL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc ON rag.rag_chunks(document_id, index_version);
CREATE INDEX IF NOT EXISTS idx_chunks_fts ON rag.rag_chunks USING gin (content gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_docs_version ON rag.rag_documents(index_version, status);
