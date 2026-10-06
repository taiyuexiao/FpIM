"""TST-01 — 当前用户接口单元测试（我的资料 / 改密）"""
from helpers import auth


def test_get_me(http, admin):
    r = http(lambda c: c.get("/api/v1/me", headers=auth(admin["token"])))
    assert r.status_code == 200
    assert r.json()["id"] == "P0001"


def test_get_me_no_auth_401(http):
    r = http(lambda c: c.get("/api/v1/me"))
    assert r.status_code == 401


def test_update_my_profile(http, temp_user):
    token, user_id, _ = temp_user
    r = http(lambda c: c.put("/api/v1/me/profile", json={
        "role": "新角色", "selfPortrait": "擅长 X 领域",
    }, headers=auth(token)))
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == user_id
    assert body["role"] == "新角色"


def test_update_my_profile_no_auth_401(http):
    r = http(lambda c: c.put("/api/v1/me/profile", json={"role": "x"}))
    assert r.status_code == 401


def test_change_my_password(http, temp_user):
    token, user_id, account = temp_user
    r = http(lambda c: c.post("/api/v1/auth/change-password", json={
        "old_password": "test123456", "new_password": "newpass999",
    }, headers=auth(token)))
    assert r.status_code == 200
    # 新密码可登录（登录按 id 匹配、大小写不敏感——register 生成的小写 hex id 也能登）
    r_new = http(lambda c: c.post("/api/v1/auth/login", json={
        "account": user_id, "password": "newpass999",
    }))
    assert r_new.status_code == 200


def test_change_my_password_wrong_old(http, temp_user):
    token, _, _ = temp_user
    r = http(lambda c: c.post("/api/v1/auth/change-password", json={
        "old_password": "wrong-old", "new_password": "newpass999",
    }, headers=auth(token)))
    assert r.status_code == 400
