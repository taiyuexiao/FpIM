-- 会话偏好 + 表情回应（research-feishu-im-features.md 对标：会话管理 P0 + 表情回应 P0）
-- conversation_members 追加：置顶/免打扰/清空记录游标（都是"我与会话的关系"，per-user）
-- message_reactions：消息表情回应（同一用户同 emoji 唯一，再点即撤回）
-- 幂等：可重复执行

ALTER TABLE im.conversation_members
    ADD COLUMN IF NOT EXISTS pinned boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS muted boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS cleared_seq bigint NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS im.message_reactions (
    id          BIGSERIAL PRIMARY KEY,
    message_id  BIGINT NOT NULL REFERENCES im.messages(id) ON DELETE CASCADE,
    user_id     VARCHAR(32) NOT NULL REFERENCES public.user2(id),
    emoji       VARCHAR(32) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (message_id, user_id, emoji)
);

CREATE INDEX IF NOT EXISTS idx_message_reactions_msg ON im.message_reactions(message_id);
