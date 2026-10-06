-- Agent 知识库绑定（二期 agent-knowledge，必须需求 #1）
-- owner 预提供知识；shared_group_ids=授权代答的群（能读≠能分享：只有授权群允许代答引用）
-- 幂等：可重复执行
CREATE TABLE IF NOT EXISTS public.agent_knowledge (
    id                BIGSERIAL PRIMARY KEY,
    owner_person_id   VARCHAR(32) NOT NULL REFERENCES public.user2(id),
    title             TEXT NOT NULL,
    content           TEXT NOT NULL,
    domains           JSONB NOT NULL DEFAULT '[]',
    shared_group_ids  JSONB NOT NULL DEFAULT '[]',
    status            VARCHAR(16) NOT NULL DEFAULT 'active',
    created_by        VARCHAR(32) NOT NULL REFERENCES public.user2(id),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_knowledge_owner ON public.agent_knowledge(owner_person_id);
