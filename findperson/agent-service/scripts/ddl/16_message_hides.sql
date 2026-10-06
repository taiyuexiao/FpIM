-- 仅自己删除消息（research-feishu-im-features.md 对标 P1：删除仅对自己生效）
-- 与"清空聊天记录"同思路：留痕数据不删，per-user 隐藏
-- 幂等：可重复执行
CREATE TABLE IF NOT EXISTS im.message_hides (
    message_id BIGINT NOT NULL REFERENCES im.messages(id) ON DELETE CASCADE,
    user_id    VARCHAR(32) NOT NULL REFERENCES public.user2(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (message_id, user_id)
);
