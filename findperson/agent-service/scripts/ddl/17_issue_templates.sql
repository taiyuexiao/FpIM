-- 解决模板（二期 agent-knowledge 第一切片）
-- 问题解决后沉淀为「处理套路+责任人」的可转发模板；private=个人库 / public=公共库
-- 幂等：可重复执行
CREATE TABLE IF NOT EXISTS public.issue_templates (
    id               BIGSERIAL PRIMARY KEY,
    source_issue_id  BIGINT REFERENCES public.issues(id) ON DELETE SET NULL,
    title            TEXT NOT NULL,
    question         TEXT NOT NULL,
    solution         TEXT NOT NULL,
    tags             JSONB NOT NULL DEFAULT '[]',
    owner_person_id  VARCHAR(32) REFERENCES public.user2(id),
    visibility       VARCHAR(16) NOT NULL DEFAULT 'private',
    created_by       VARCHAR(32) NOT NULL REFERENCES public.user2(id),
    use_count        INTEGER NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_issue_templates_owner ON public.issue_templates(owner_person_id);
CREATE INDEX IF NOT EXISTS idx_issue_templates_visibility ON public.issue_templates(visibility);
