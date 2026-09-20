"""TST-01 — 内容接口单元测试（创建 / 编辑 / 提交 / 审核 / 删除）

注意：contents.owner_id 外键指向 public.users（不是 user2）。
pytest 临时用户只落在 user2，用它当 owner 会撞外键，
所以内容一律用种子账号 `user`（p0002，两表都在）创建，并在 teardown 按 id 物理清理。
"""
from helpers import auth, purge_content


def test_create_content(http, user):
    cid = None
    try:
        r = http(lambda c: c.post("/api/v1/contents", json={
            "title": "测试内容标题", "summary": "测试摘要",
            "tags": ["测试"], "body": "正文", "status": "草稿",
        }, headers=auth(user["token"])))
        assert r.status_code == 201
        body = r.json()
        cid = body["id"]
        assert cid.startswith("C")
        assert body["status"] == "草稿"
        assert body["ownerId"]
    finally:
        if cid:
            purge_content(cid)


def test_create_and_get_content(http, user):
    cid = None
    try:
        cid = http(lambda c: c.post("/api/v1/contents", json={
            "title": "详情测试", "summary": "摘要", "body": "正文",
        }, headers=auth(user["token"]))).json()["id"]
        r = http(lambda c: c.get(f"/api/v1/contents/{cid}", headers=auth(user["token"])))
        assert r.status_code == 200
        assert r.json()["id"] == cid
    finally:
        if cid:
            purge_content(cid)


def test_update_content(http, user):
    cid = None
    try:
        cid = http(lambda c: c.post("/api/v1/contents", json={
            "title": "原标题", "summary": "摘要",
        }, headers=auth(user["token"]))).json()["id"]
        r = http(lambda c: c.put(f"/api/v1/contents/{cid}", json={
            "title": "改后标题", "summary": "改后摘要",
        }, headers=auth(user["token"])))
        assert r.status_code == 200
        assert r.json()["title"] == "改后标题"
    finally:
        if cid:
            purge_content(cid)


def test_submit_and_audit_approve(http, user, admin):
    cid = None
    try:
        cid = http(lambda c: c.post("/api/v1/contents", json={
            "title": "待发布", "summary": "摘要",
        }, headers=auth(user["token"]))).json()["id"]
        # 提交审核
        r_sub = http(lambda c: c.post(f"/api/v1/contents/{cid}/submit", headers=auth(user["token"])))
        assert r_sub.status_code == 200
        assert r_sub.json()["status"] == "待审核"
        # admin 审核通过 → 已发布
        r_aud = http(lambda c: c.post(f"/api/v1/contents/{cid}/audit", json={
            "action": "approve", "reason": "合格",
        }, headers=auth(admin["token"])))
        assert r_aud.status_code == 200
        assert r_aud.json()["status"] == "已发布"
    finally:
        if cid:
            purge_content(cid)


def test_audit_reject(http, user, admin):
    cid = None
    try:
        cid = http(lambda c: c.post("/api/v1/contents", json={
            "title": "待驳回", "summary": "摘要",
        }, headers=auth(user["token"]))).json()["id"]
        http(lambda c: c.post(f"/api/v1/contents/{cid}/submit", headers=auth(user["token"])))
        r = http(lambda c: c.post(f"/api/v1/contents/{cid}/audit", json={
            "action": "reject", "reason": "不合格",
        }, headers=auth(admin["token"])))
        assert r.status_code == 200
        assert r.json()["status"] == "已驳回"
    finally:
        if cid:
            purge_content(cid)


def test_delete_content_soft(http, user):
    cid = None
    try:
        cid = http(lambda c: c.post("/api/v1/contents", json={
            "title": "待删除", "summary": "摘要",
        }, headers=auth(user["token"]))).json()["id"]
        r = http(lambda c: c.delete(f"/api/v1/contents/{cid}", headers=auth(user["token"])))
        assert r.status_code == 200
        # 软删除后详情 404（需带鉴权，否则中间件先返回 401）
        r2 = http(lambda c: c.get(f"/api/v1/contents/{cid}", headers=auth(user["token"])))
        assert r2.status_code == 404
    finally:
        if cid:
            purge_content(cid)


def test_list_contents(http, user):
    r = http(lambda c: c.get("/api/v1/contents", headers=auth(user["token"])))
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_create_content_requires_auth(http):
    r = http(lambda c: c.post("/api/v1/contents", json={
        "title": "无鉴权", "summary": "摘要",
    }))
    assert r.status_code == 401
