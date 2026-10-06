-- 消息编辑（research-feishu-im-features.md 对标 P1：24h 内最多 20 次、带「已编辑」标记）
-- 幂等：可重复执行
ALTER TABLE im.messages
    ADD COLUMN IF NOT EXISTS edit_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS edited_at TIMESTAMPTZ;
