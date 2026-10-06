-- 06_manager.sql —— 人员直接上级(manager_id,树状汇报关系)
-- 验收#7:每个人都有自己的上级。幂等,可重复执行。

-- ========== 1. 表结构 ==========
ALTER TABLE public.users  ADD COLUMN IF NOT EXISTS manager_id VARCHAR(32) REFERENCES public.users(id);
ALTER TABLE public.people ADD COLUMN IF NOT EXISTS manager_id VARCHAR(32);
CREATE INDEX IF NOT EXISTS idx_users_manager ON public.users(manager_id);

-- ========== 2. users → people 同步触发器补 manager_id ==========
CREATE OR REPLACE FUNCTION public.sync_users_to_people() RETURNS trigger AS $$
BEGIN
    INSERT INTO public.people(id, account, phone, name, department, department_id,
                              role, role_type, contact, self_portrait, completeness,
                              status, manager_id, updated_at)
    VALUES (NEW.id, NEW.account, NEW.phone, NEW.name,
            coalesce((SELECT name FROM public.departments WHERE id = NEW.department_id), ''),
            NEW.department_id, coalesce(NEW.role, ''), 'user', NEW.contact,
            coalesce(NEW.self_portrait, ''), coalesce(NEW.completeness, 0),
            CASE WHEN NEW.active THEN 'active' ELSE 'inactive' END, NEW.manager_id, now())
    ON CONFLICT (id) DO UPDATE SET
        account        = EXCLUDED.account,
        phone          = EXCLUDED.phone,
        name           = EXCLUDED.name,
        department     = EXCLUDED.department,
        department_id  = EXCLUDED.department_id,
        role           = EXCLUDED.role,
        contact        = EXCLUDED.contact,
        self_portrait  = EXCLUDED.self_portrait,
        completeness   = EXCLUDED.completeness,
        status         = EXCLUDED.status,
        manager_id     = EXCLUDED.manager_id,
        updated_at     = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ========== 3. 存量回填:上级 = 本部门负责人;本人即负责人则取上级部门负责人 ==========
UPDATE public.users u SET manager_id = d.leader_id
FROM public.departments d
WHERE u.department_id = d.id AND d.leader_id IS NOT NULL AND d.leader_id <> u.id
  AND u.manager_id IS NULL;

UPDATE public.users u SET manager_id = pd.leader_id
FROM public.departments d
JOIN public.departments pd ON pd.id = d.parent_id
WHERE u.department_id = d.id AND d.leader_id = u.id
  AND pd.leader_id IS NOT NULL AND pd.leader_id <> u.id
  AND u.manager_id IS NULL;
