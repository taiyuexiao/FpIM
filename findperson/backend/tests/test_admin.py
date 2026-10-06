"""TST-01 — 管理后台接口单元测试（看板 / 统计 / 审计 / 权限）"""
from helpers import auth


def test_dashboard_admin(http, admin):
    r = http(lambda c: c.get("/api/v1/admin/dashboard", headers=auth(admin["token"])))
    assert r.status_code == 200
    body = r.json()
    for k in ("peopleCount", "contentCount", "domainCount", "weeklyRecommendationTotal"):
        assert k in body
        assert body[k] >= 0


def test_dashboard_normal_user_403(http, user):
    r = http(lambda c: c.get("/api/v1/admin/dashboard", headers=auth(user["token"])))
    assert r.status_code == 403


def test_dashboard_no_auth_401(http):
    r = http(lambda c: c.get("/api/v1/admin/dashboard"))
    assert r.status_code == 401


def test_metrics_admin(http, admin):
    r = http(lambda c: c.get("/api/v1/admin/metrics", headers=auth(admin["token"])))
    assert r.status_code == 200
    assert "peopleCount" in r.json()


def test_statistics_data_admin(http, admin):
    r = http(lambda c: c.get("/api/v1/admin/statistics/data", headers=auth(admin["token"])))
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_audit_logs_capture_write(http, admin, temp_user):
    token, user_id, _ = temp_user
    # 触发一次写操作（改资料 → 审计中间件落库）
    r = http(lambda c: c.put("/api/v1/me/profile", json={
        "role": "审计测试角色",
    }, headers=auth(token)))
    assert r.status_code == 200
    # admin 查审计日志
    r2 = http(lambda c: c.get("/api/v1/admin/audit-logs", headers=auth(admin["token"])))
    assert r2.status_code == 200
    body = r2.json()
    assert body["total"] >= 1
    assert any(item["userId"] == user_id for item in body["items"])


def test_audit_logs_normal_user_403(http, user):
    r = http(lambda c: c.get("/api/v1/admin/audit-logs", headers=auth(user["token"])))
    assert r.status_code == 403


def test_recommend_ranking_admin(http, admin):
    r = http(lambda c: c.get("/api/v1/admin/rankings/recommend", headers=auth(admin["token"])))
    assert r.status_code == 200
    assert isinstance(r.json(), list)
