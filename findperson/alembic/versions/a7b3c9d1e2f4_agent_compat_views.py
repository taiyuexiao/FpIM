"""agent 兼容层：people 视图 + 责任表补列 + rag_index_pointer

Revision ID: a7b3c9d1e2f4
Revises: f1a2b3c4d5e6
Create Date: 2026-08-14

打通 agent-service / knowledge-service 的数据契约（以 shouwenzeren 库为准）：
1. 建 public.people 视图，映射 public.users，补齐 agent 只读查询需要的列
   （department 冗余列、status text、role_type 等）。
2. public.responsibility_assignments 补列，补齐 agent 检索需要的「完整责任事项」字段，
   并从 agent.concepts + public.users 回填 title/description/owner 等。
3. 补 rag.rag_index_pointer（agent 索引器/检索器的版本指针表）。

rag 其余表结构差异（rag_documents/rag_chunks/rag_index_jobs 两套列名/index_version 类型）
不在本迁移处理，保持我们 rag 表不动，由 agent 团队改其 rag SQL 适配。
"""
from alembic import op

revision: str = 'a7b3c9d1e2f4'
down_revision: str = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- A1: public.people 视图（映射 users，供 agent 只读查询）----
    op.execute("""
        CREATE VIEW public.people AS
        SELECT
            u.id,
            u.account,
            u.phone,
            u.name,
            d.name AS department,
            u.department_id,
            COALESCE(u.role, '') AS role,
            CASE WHEN u.system_role = '管理员' THEN 'admin' ELSE 'user' END AS role_type,
            u.contact,
            COALESCE(u.self_portrait, '') AS self_portrait,
            COALESCE(u.completeness, 0) AS completeness,
            CASE WHEN u.active THEN 'active' ELSE 'inactive' END AS status,
            u.created_at,
            u.updated_at
        FROM public.users u
        LEFT JOIN public.departments d ON d.id = u.department_id
    """)

    # ---- A2: 责任表补列（补齐 agent 检索需要的完整责任事项字段）----
    op.execute("""
        ALTER TABLE public.responsibility_assignments
            ADD COLUMN title TEXT NOT NULL DEFAULT '',
            ADD COLUMN description TEXT NOT NULL DEFAULT '',
            ADD COLUMN intake_department_id INTEGER REFERENCES public.departments(id),
            ADD COLUMN owner_department_id INTEGER REFERENCES public.departments(id),
            ADD COLUMN owner_person_id VARCHAR(32) REFERENCES public.users(id),
            ADD COLUMN owner_role TEXT NOT NULL DEFAULT '',
            ADD COLUMN time_limit TEXT NOT NULL DEFAULT '',
            ADD COLUMN transfer_condition TEXT NOT NULL DEFAULT '',
            ADD COLUMN escalation_path TEXT NOT NULL DEFAULT '',
            ADD COLUMN version INTEGER NOT NULL DEFAULT 1
    """)

    # 回填：title/description 取 agent.concepts，owner 取 person_id/users 冗余
    op.execute("""
        UPDATE public.responsibility_assignments ra
        SET title = c.name,
            description = c.description,
            owner_person_id = ra.person_id,
            owner_role = COALESCE(u.role, ''),
            intake_department_id = u.department_id,
            owner_department_id = u.department_id
        FROM agent.concepts c, public.users u
        WHERE c.id = ra.concept_id
          AND u.id = ra.person_id
    """)

    # ---- A3: rag.rag_index_pointer（agent 索引器/检索器版本指针）----
    op.execute("""
        CREATE TABLE rag.rag_index_pointer (
            id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
            active_version INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("INSERT INTO rag.rag_index_pointer (id, active_version) VALUES (1, 0)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS rag.rag_index_pointer")
    op.execute("""
        ALTER TABLE public.responsibility_assignments
            DROP COLUMN IF EXISTS title,
            DROP COLUMN IF EXISTS description,
            DROP COLUMN IF EXISTS intake_department_id,
            DROP COLUMN IF EXISTS owner_department_id,
            DROP COLUMN IF EXISTS owner_person_id,
            DROP COLUMN IF EXISTS owner_role,
            DROP COLUMN IF EXISTS time_limit,
            DROP COLUMN IF EXISTS transfer_condition,
            DROP COLUMN IF EXISTS escalation_path,
            DROP COLUMN IF EXISTS version
    """)
    op.execute("DROP VIEW IF EXISTS public.people")
