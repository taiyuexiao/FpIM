-- 10_bot_user.sql — 「小管家」系统号（PRD：通知走 IM 内的系统号，而非短信/邮件）
-- id 固定为 'system'（与消息表 sender_id='system' 的约定一致）；
-- active=false：登录被拒 + 名片库（active=true 过滤）不展示，纯后台发送者。
INSERT INTO public.user2 (id, account, name, password_hash, system_role, active, created_at)
VALUES ('system', 'sysbot', '小管家', '$2b$12$disabled-bot-account-no-login', '系统', false, now())
ON CONFLICT (id) DO NOTHING;
