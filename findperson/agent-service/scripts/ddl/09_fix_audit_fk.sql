-- 09_fix_audit_fk.sql — 审计日志外键对齐到当前用户主表
-- 背景：audit_logs.user_id 的外键建在老表 public.users 上，而当前业务用户主表是 user2
-- （ORM 模型 ForeignKey("user2.id") 也指向 user2）。/auth/register 新建的用户只落在 user2，
-- 导致这些用户的操作写审计日志时撞外键，被中间件静默吞掉（except: rollback）。
BEGIN;
ALTER TABLE public.audit_logs DROP CONSTRAINT IF EXISTS audit_logs_user_id_fkey;
ALTER TABLE public.audit_logs ADD CONSTRAINT audit_logs_user_id_fkey
  FOREIGN KEY (user_id) REFERENCES public.user2(id);
COMMIT;
