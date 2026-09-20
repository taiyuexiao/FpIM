"""TST-02 — 7 条验收路径集成测试

路径映射（后端可测范围）：
  1. 找负责人   → AGUI 问答收口（Agent 未接入时走降级 SSE）
  2. 发布内容   → 创建 → 提交 → 审核通过 → 已发布 + publish_events
  3. 审核       → 驳回（reject）状态流转 + 审核轨迹
  4. 改资料     → PUT /me/profile
  5. 评价       → 打标签 + 标签汇总
  6. 名片库     → 人员列表 + 详情
  7. 统计       → 统计快照 + 管理看板

数据约束：
- contents.owner_id / peer_reviews.reviewer_id 等外键指向老表 public.users；
  pytest 临时用户（user2）不能当 owner/reviewer → 内容/评价一律用种子账号 `user`（p0005）。
- 只读接口在全局 AuthMiddleware 下也要带 token。
"""
import uuid

from sqlalchemy import text

from app.core.database import SessionLocal
from helpers import auth, purge_content


def _count_events(resource_id):
    db = SessionLocal()
    try:
        return db.execute(
            text("SELECT count(*) FROM rag.publish_events WHERE resource_id = :c"),
            {"c": resource_id},
        ).scalar()
    finally:
        db.close()


def _purge_review(tag):
    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM public.peer_reviews WHERE tag_name = :t"), {"t": tag})
        db.commit()
    finally:
        db.close()


def test_path_01_find_person(http, user):
    """找负责人：AGUI 问答收口链路。

    ⚠️ 现架构：AGUI 会话由 agent-service（8100）直接承载，backend 只做事件回传代理。
    本用例打真实 agent-service（契约：sessionId 字段 + X-User-Id 头 + SSE 帧）；
    8100 不在时跳过（CI 可不依赖它）。
    """
    import httpx as _httpx
    import pytest

    AGENT = "http://127.0.0.1:8100"
    try:
        _httpx.get(f"{AGENT}/health", timeout=3)
    except Exception:
        pytest.skip("agent-service (8100) 不在，跳过 AGUI 链路验收")

    # 用种子用户：agent-service 建会话时要按 X-User-Id 查 user2，临时 hex id 会 500
    user_id = user["user"]["id"]

    def agent_call(method, path, body=None):
        req = _httpx.request(method, AGENT + path, json=body,
                             headers={"X-User-Id": user_id}, timeout=90)
        return req

    r = agent_call("POST", "/api/agui/sessions", {"title": "验收-找负责人", "userId": user_id})
    assert r.status_code == 200
    sid = r.json()["sessionId"]

    r2 = agent_call("POST", f"/api/agui/sessions/{sid}/messages", {
        "message": {"role": "user", "text": "谁负责公积金提取业务？"},
        "context": {},
    })
    assert r2.status_code == 200
    sse = r2.text
    assert "run_started" in sse and "run_finished" in sse


def test_path_02_publish_content(http, user, admin):
    """发布内容：创建 → 提交 → 审核通过 → 已发布 + 事件信号"""
    cid = None
    try:
        cid = http(lambda c: c.post("/api/v1/contents", json={
            "title": "验收-发布内容", "summary": "验收摘要", "tags": ["验收"],
        }, headers=auth(user["token"]))).json()["id"]

        assert _count_events(cid) == 0  # 草稿不触发事件

        http(lambda c: c.post(f"/api/v1/contents/{cid}/submit", headers=auth(user["token"])))
        assert _count_events(cid) == 0  # 提交不触发事件

        r = http(lambda c: c.post(f"/api/v1/contents/{cid}/audit", json={
            "action": "approve", "reason": "验收通过",
        }, headers=auth(admin["token"])))
        assert r.status_code == 200
        assert r.json()["status"] == "已发布"
        assert _count_events(cid) == 1  # 发布触发 content_published
    finally:
        if cid:
            purge_content(cid)


def test_path_03_audit(http, user, admin):
    """审核：驳回流转 + 审核轨迹"""
    cid = None
    try:
        cid = http(lambda c: c.post("/api/v1/contents", json={
            "title": "验收-审核驳回", "summary": "摘要",
        }, headers=auth(user["token"]))).json()["id"]
        http(lambda c: c.post(f"/api/v1/contents/{cid}/submit", headers=auth(user["token"])))

        r = http(lambda c: c.post(f"/api/v1/contents/{cid}/audit", json={
            "action": "reject", "reason": "材料不全",
        }, headers=auth(admin["token"])))
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "已驳回"
        assert body["auditTrail"] and body["auditTrail"][-1]["result"] == "rejected"
    finally:
        if cid:
            purge_content(cid)


def test_path_04_update_profile(http, temp_user):
    """改资料：更新自己资料"""
    token, user_id, _ = temp_user
    r = http(lambda c: c.put("/api/v1/me/profile", json={
        "role": "公积金业务经办", "selfPortrait": "负责公积金提取与贷款",
        "phone": f"139{uuid.uuid4().int % 10**8:08d}",  # 唯一手机号：user2.phone 有唯一约束
    }, headers=auth(token)))
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == user_id
    assert body["role"] == "公积金业务经办"


def test_path_05_review(http, user):
    """评价：为他人打标签 + 标签汇总"""
    tag = f"验收标签_{uuid.uuid4().hex[:6]}"
    try:
        r = http(lambda c: c.post("/api/v1/reviews", json={
            "personId": "P0002", "tag": tag,
        }, headers=auth(user["token"])))
        assert r.status_code == 201
        assert r.json()["tag"] == tag

        r2 = http(lambda c: c.get("/api/v1/reviews/person/P0002", headers=auth(user["token"])))
        assert r2.status_code == 200
        assert tag in r2.json()["tags"]
    finally:
        _purge_review(tag)


def test_path_06_business_card_library(http, user):
    """名片库：人员列表 + 详情"""
    r = http(lambda c: c.get("/api/v1/people", headers=auth(user["token"])))
    assert r.status_code == 200
    assert isinstance(r.json(), list) and len(r.json()) > 0

    r2 = http(lambda c: c.get("/api/v1/people/P0001", headers=auth(user["token"])))
    assert r2.status_code == 200
    assert r2.json()["id"] == "P0001"


def test_path_07_statistics(http, admin):
    """统计：统计快照 + 管理看板"""
    r = http(lambda c: c.get("/api/v1/admin/statistics/data", headers=auth(admin["token"])))
    assert r.status_code == 200
    assert isinstance(r.json(), list)

    r2 = http(lambda c: c.get("/api/v1/admin/dashboard", headers=auth(admin["token"])))
    assert r2.status_code == 200
    body = r2.json()
    assert body["peopleCount"] >= 0 and body["contentCount"] >= 0
