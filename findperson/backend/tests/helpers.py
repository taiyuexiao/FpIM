"""测试公共 helper：鉴权头 + 临时数据物理清理（供各 test_*.py 与 conftest 复用）

purge_user 按外键依赖顺序删除临时用户及其全部关联数据（含会话/消息/日志等），
保证测试不留脏数据。所有表均在 public schema（rag.publish_events 在 rag schema）。
"""
from sqlalchemy import text

from app.core.database import SessionLocal


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _db():
    return SessionLocal()


def purge_user(user_id: str) -> None:
    """物理删除临时用户及其关联数据（按外键依赖顺序）。

    ⚠️ 双用户表：业务模型 User 映射到 `user2`，但老表 `public.users` 仍被
    contents/peer_reviews 等的外键引用。临时用户由 /auth/register 创建在 `user2`，
    所以删除以 `user2` 为主；`users` 侧兜底删一次（若无此行也无影响）。
    """
    db = _db()
    try:
        content_ids = [r[0] for r in db.execute(
            text("SELECT id FROM public.contents WHERE owner_id = :u"), {"u": user_id}
        )]
        if content_ids:
            db.execute(
                text("DELETE FROM rag.publish_events WHERE resource_id = ANY(:ids)"),
                {"ids": content_ids},
            )
        db.execute(text("DELETE FROM rag.publish_events WHERE created_by = :u"), {"u": user_id})
        # 子表 → 父表
        db.execute(text("DELETE FROM public.recommendation_logs WHERE user_id = :u OR person_id = :u"), {"u": user_id})
        db.execute(text("DELETE FROM public.feedback WHERE user_id = :u"), {"u": user_id})
        db.execute(text("DELETE FROM public.peer_reviews WHERE reviewer_id = :u OR person_id = :u"), {"u": user_id})
        db.execute(text("DELETE FROM public.messages WHERE user_id = :u"), {"u": user_id})
        db.execute(text("DELETE FROM public.query_logs WHERE user_id = :u"), {"u": user_id})
        db.execute(text("DELETE FROM public.sessions WHERE user_id = :u"), {"u": user_id})
        db.execute(text("DELETE FROM public.contents WHERE owner_id = :u"), {"u": user_id})
        db.execute(text("DELETE FROM public.audit_logs WHERE user_id = :u"), {"u": user_id})
        db.execute(text("DELETE FROM public.users WHERE id = :u"), {"u": user_id})
        db.execute(text("DELETE FROM public.user2 WHERE id = :u"), {"u": user_id})
        db.commit()
    finally:
        db.close()


def purge_content(content_id: str) -> None:
    """物理删除临时内容及其关联事件 / 审计。"""
    db = _db()
    try:
        db.execute(
            text("DELETE FROM rag.publish_events WHERE resource_id = :cid"),
            {"cid": content_id},
        )
        db.execute(text("DELETE FROM public.audit_logs WHERE resource_id = :cid"), {"cid": content_id})
        db.execute(text("DELETE FROM public.contents WHERE id = :cid"), {"cid": content_id})
        db.commit()
    finally:
        db.close()
