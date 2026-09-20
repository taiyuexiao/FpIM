"""TST-01 — 人员/名片库接口单元测试"""
from helpers import auth


def test_list_people_public(http, user):
    # 名单/目录类接口现在也要登录（AuthMiddleware 全局鉴权，仅登录/文档/健康放行）
    r = http(lambda c: c.get("/api/v1/people", headers=auth(user["token"])))
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) > 0
    # 返回项含关键字段
    assert "id" in data[0] and "name" in data[0]


def test_list_people_search_by_account(http, user):
    r = http(lambda c: c.get("/api/v1/people", params={"keyword": "p0001"}, headers=auth(user["token"])))
    assert r.status_code == 200
    data = r.json()
    assert any(u["account"] == "p0001" for u in data)


def test_get_person(http, user):
    r = http(lambda c: c.get("/api/v1/people/P0001", headers=auth(user["token"])))
    assert r.status_code == 200
    assert r.json()["id"] == "P0001"
    assert r.json()["account"] == "p0001"


def test_get_person_not_found(http, user):
    r = http(lambda c: c.get("/api/v1/people/NO_SUCH_PERSON", headers=auth(user["token"])))
    assert r.status_code == 404


def test_update_person(http, temp_user, admin):
    # PATCH /people/{id} 是管理员专属（v4 §十：成员管理仅管理员），用 admin token 改临时用户
    _, user_id, _ = temp_user
    import uuid as _uuid
    phone = f"138{_uuid.uuid4().int % 10**8:08d}"  # user2.phone 有唯一约束
    r = http(lambda c: c.patch(
        f"/api/v1/people/{user_id}",
        json={"role": "测试角色", "phone": phone},
        headers=auth(admin["token"]),
    ))
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "测试角色"
    assert body["phone"] == phone


def test_get_person_reviews(http, user):
    r = http(lambda c: c.get("/api/v1/people/P0001/reviews", headers=auth(user["token"])))
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "total" in body
