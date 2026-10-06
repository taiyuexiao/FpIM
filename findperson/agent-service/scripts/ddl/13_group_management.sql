-- 群管理（research-feishu-im-features.md 对标 P0：群信息编辑/群公告/退出与移出）
-- 幂等：可重复执行
ALTER TABLE im.conversations
    ADD COLUMN IF NOT EXISTS announcement TEXT NOT NULL DEFAULT '';
