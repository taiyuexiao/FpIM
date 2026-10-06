-- 群治理 + 置顶消息（research-feishu-im-features.md 对标 P1）
-- speak_permission: all=所有成员可发言 | owner=仅群主可发言（简化版「发言权限」）
-- pinned_message_id: 会话内置顶的唯一一条消息
-- 幂等：可重复执行
ALTER TABLE im.conversations
    ADD COLUMN IF NOT EXISTS speak_permission VARCHAR(16) NOT NULL DEFAULT 'all',
    ADD COLUMN IF NOT EXISTS pinned_message_id BIGINT REFERENCES im.messages(id);
