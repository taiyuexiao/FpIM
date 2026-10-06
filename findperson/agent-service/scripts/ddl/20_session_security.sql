-- 会话安全（04-生产加固技术方案 §3.1）：token_version 递增即全端吊销
-- 幂等：可重复执行
ALTER TABLE public.user2
    ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0;
