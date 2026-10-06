-- 私聊代理委托（二期 R2，必须需求 #2）
-- mode: off=关闭 | draft=仅起草（发给本人） | auto=自动处理（未读期间自主代答）
-- 幂等：可重复执行
CREATE TABLE IF NOT EXISTS public.agent_delegations (
    conversation_id BIGINT PRIMARY KEY REFERENCES im.conversations(id) ON DELETE CASCADE,
    owner_person_id VARCHAR(32) NOT NULL REFERENCES public.user2(id),
    mode            VARCHAR(16) NOT NULL DEFAULT 'off',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
