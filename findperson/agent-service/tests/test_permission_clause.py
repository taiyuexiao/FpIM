"""RAG 可见性过滤(permission_clause)单元测试 —— 纯函数,不依赖 DB。

规则与仓库 knowledge-service 对齐:
匿名仅 public;已认证 public/internal + 本部门/放行部门的 restricted。
"""
from app.contracts.agent_state import UserContext
from app.rag.retriever import permission_clause


def test_anonymous_public_only() -> None:
    sql, params = permission_clause(UserContext(user_id=""), 4)
    assert sql == "d.visibility = 'public'"
    assert params == []


def test_authenticated_without_department() -> None:
    sql, params = permission_clause(UserContext(user_id="p-0001"), 4)
    assert "'public','internal'" in sql
    assert params == []


def test_authenticated_with_department() -> None:
    sql, params = permission_clause(UserContext(user_id="p-0001", department_id=3), 4)
    assert "owner_department_id = $4" in sql
    assert "allowed_departments @> to_jsonb($4::int)" in sql
    assert params == [3]


def test_placeholder_index_offset() -> None:
    """占位符起始下标可偏移(与调用方 SQL 拼接)。"""
    sql, params = permission_clause(UserContext(user_id="p-1", department_id=7), 6)
    assert "$6" in sql and "$4" not in sql
    assert params == [7]
