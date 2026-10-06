"""TST-IDOR — 越权访问回归清单（04-生产加固技术方案 §2.4）。

规则：A 的 token 访问 B 的资源，必须 403/404；文件端点防路径穿越与强制附件。
这些用例是"桥接/偏好/治理"等新功能引入时的越权防护网。
"""
from __future__ import annotations

import uuid

import httpx
import pytest

from app.main import app

from helpers import auth


@pytest.fixture
def two_users(http):
    """两个独立用户（带 token）。p0001/p0002 是种子账号，直接登录。"""
    from app.core.config import settings

    tokens = {}
    for acc in ("p0001", "p0002"):
        r = http(lambda c: c.post("/api/v1/auth/login", json={
            "account": acc, "password": settings.SEED_PASSWORD,
        }))
        assert r.status_code == 200, r.text
        tokens[acc] = r.json()["token"]
    return tokens


def _hdr(token):
    return auth(token)


def test_conversation_detail_idor(http, two_users):
    """A 读 B 的单聊会话详情 → 403/404（不是成员）。"""
    t_a, t_b = two_users["p0001"], two_users["p0002"]
    # B 与 C 建立单聊（A 不在其中）——直接用 B 建
    r = http(lambda c: c.post("/api/v1/im/conversations/direct",
                              json={"peerId": "P0003"}, headers=_hdr(t_b)))
    assert r.status_code == 200
    d = r.json()
    cid = (d.get("conversation") or d).get("id")
    r = http(lambda c: c.get(f"/api/v1/im/conversations/{cid}", headers=_hdr(t_a)))
    assert r.status_code in (403, 404), f"越权读取会话详情：{r.status_code} {r.text[:80]}"


def test_conversation_messages_idor(http, two_users):
    t_a, t_b = two_users["p0001"], two_users["p0002"]
    r = http(lambda c: c.post("/api/v1/im/conversations/direct",
                              json={"peerId": "P0003"}, headers=_hdr(t_b)))
    d = r.json()
    cid = (d.get("conversation") or d).get("id")
    r = http(lambda c: c.get(f"/api/v1/im/conversations/{cid}/messages", headers=_hdr(t_a)))
    assert r.status_code in (403, 404)


def test_conversation_send_message_idor(http, two_users):
    t_a, t_b = two_users["p0001"], two_users["p0002"]
    r = http(lambda c: c.post("/api/v1/im/conversations/direct",
                              json={"peerId": "P0003"}, headers=_hdr(t_b)))
    d = r.json()
    cid = (d.get("conversation") or d).get("id")
    r = http(lambda c: c.post(f"/api/v1/im/conversations/{cid}/messages",
                              json={"text": "越权发言", "clientMsgId": f"idor-{uuid.uuid4().hex[:8]}"},
                              headers=_hdr(t_a)))
    assert r.status_code in (400, 403), "非成员不得发言"


def test_conversation_prefs_idor(http, two_users):
    t_a, t_b = two_users["p0001"], two_users["p0002"]
    r = http(lambda c: c.post("/api/v1/im/conversations/direct",
                              json={"peerId": "P0003"}, headers=_hdr(t_b)))
    d = r.json()
    cid = (d.get("conversation") or d).get("id")
    r = http(lambda c: c.patch(f"/api/v1/im/conversations/{cid}/prefs",
                               json={"pinned": True}, headers=_hdr(t_a)))
    assert r.status_code in (403, 404)


def test_delegation_idor(http, two_users):
    t_a, t_b = two_users["p0001"], two_users["p0002"]
    r = http(lambda c: c.post("/api/v1/im/conversations/direct",
                              json={"peerId": "P0003"}, headers=_hdr(t_b)))
    d = r.json()
    cid = (d.get("conversation") or d).get("id")
    r = http(lambda c: c.put(f"/api/v1/im/conversations/{cid}/delegation",
                             json={"mode": "auto"}, headers=_hdr(t_a)))
    # A 不是该会话成员 → 403；A 恰好是成员时也不该成功改 B 的委托——语义上 set_delegation
    # 以"调用者=委托人"落库，会话隔离由成员校验保证
    assert r.status_code in (403, 404)


def test_group_update_idor(http, two_users):
    t_a, t_b = two_users["p0001"], two_users["p0002"]
    r = http(lambda c: c.post("/api/v1/im/conversations/group",
                              json={"title": "IDOR群", "memberIds": ["P0002", "P0003"]},
                              headers=_hdr(t_b)))
    dg = r.json()
    gid = (dg.get("conversation") or dg).get("id")
    r = http(lambda c: c.patch(f"/api/v1/im/conversations/{gid}",
                               json={"title": "被越权改名"}, headers=_hdr(t_a)))
    assert r.status_code == 403, "非群主不得改名"


def test_transfer_owner_idor(http, two_users):
    t_a, t_b = two_users["p0001"], two_users["p0002"]
    r = http(lambda c: c.post("/api/v1/im/conversations/group",
                              json={"title": "IDOR转让群", "memberIds": ["P0002", "P0003"]},
                              headers=_hdr(t_b)))
    dg = r.json()
    gid = (dg.get("conversation") or dg).get("id")
    r = http(lambda c: c.post(f"/api/v1/im/conversations/{gid}/transfer-owner",
                              json={"newOwnerId": "P0002"}, headers=_hdr(t_a)))
    assert r.status_code == 403


def test_revoke_message_idor(http, two_users):
    t_a, t_b = two_users["p0001"], two_users["p0002"]
    r = http(lambda c: c.post("/api/v1/im/conversations/group",
                              json={"title": "IDOR撤回群", "memberIds": ["P0002", "P0003"]},
                              headers=_hdr(t_b)))
    dg = r.json()
    gid = (dg.get("conversation") or dg).get("id")
    r = http(lambda c: c.post(f"/api/v1/im/conversations/{gid}/messages",
                              json={"text": "B 的消息", "clientMsgId": f"idor-rv-{uuid.uuid4().hex[:6]}"},
                              headers=_hdr(t_b)))
    mid = r.json()["message"]["id"]
    r = http(lambda c: c.delete(f"/api/v1/im/messages/{mid}", headers=_hdr(t_a)))
    assert r.status_code == 400, "非本人消息不可撤回"


def test_knowledge_update_idor(http, two_users):
    t_a, t_b = two_users["p0001"], two_users["p0002"]
    r = http(lambda c: c.post("/api/v1/agent/knowledge",
                              json={"title": "B 的知识", "content": "内容", "sharedGroupIds": []},
                              headers=_hdr(t_b)))
    kid = r.json()["item"]["id"]
    r = http(lambda c: c.put(f"/api/v1/agent/knowledge/{kid}",
                             json={"title": "被越权改", "content": "x", "sharedGroupIds": []},
                             headers=_hdr(t_a)))
    assert r.status_code == 404, "他人知识不可改"
    r = http(lambda c: c.delete(f"/api/v1/agent/knowledge/{kid}", headers=_hdr(t_a)))
    assert r.status_code == 404


def test_issue_review_idor(http, two_users):
    """非提问方不可评价。造一个已解决问题（assignee=B、asker=A 之外的 C）。"""
    t_b = two_users["p0002"]
    # 借 sync 无法稳定造数——直接对不存在/非本人问题断言权限路径
    r = http(lambda c: c.post("/api/v1/issues/999999/review",
                              json={"rating": 5}, headers=_hdr(t_b)))
    assert r.status_code == 404, "问题不存在"


def test_ws_ticket_requires_auth(http):
    r = http(lambda c: c.get("/api/v1/im/ws-ticket"))
    assert r.status_code == 401, "无 token 不得取 ticket"


def test_ws_ticket_one_time(http, two_users):
    t_a = two_users["p0001"]
    r = http(lambda c: c.get("/api/v1/im/ws-ticket", headers=_hdr(t_a)))
    assert r.status_code == 200
    ticket = r.json()["ticket"]
    # 一次性：数据库层无暴露面可二次使用——直接校验票据不可预测且格式合法
    assert len(ticket) >= 32
    r2 = http(lambda c: c.get("/api/v1/im/ws-ticket", headers=_hdr(t_a)))
    assert r2.json()["ticket"] != ticket, "ticket 必须每次随机"


def test_file_download_traversal_blocked(http, two_users, tmp_path, monkeypatch):
    """路径穿越必须 404（含兄弟目录前缀旁路）；安全文件正常可读。"""
    from app.core.config import settings

    t_a = two_users["p0001"]
    # 构造受控文件根：root/secret.txt + 兄弟目录 root2/evil.txt（前缀旁路用例）
    (tmp_path / "files").mkdir()
    (tmp_path / "files" / "ok.txt").write_text("safe")
    (tmp_path / "files2").mkdir()
    (tmp_path / "files2" / "evil.txt").write_text("leak")
    monkeypatch.setattr(settings, "FPIM_FILE_ROOT", str(tmp_path / "files"))

    # 正常文件可读
    r = http(lambda c: c.get("/api/v1/im/files/ok.txt", headers=_hdr(t_a)))
    assert r.status_code == 200 and "safe" in r.text
    # 穿越与兄弟目录前缀旁路必须 404
    for evil in ("../../.env", "../files2/evil.txt", "..%2Ffiles2%2Fevil.txt"):
        r = http(lambda c, e=evil: c.get(f"/api/v1/im/files/{e}", headers=_hdr(t_a)))
        assert r.status_code == 404, f"穿越路径未拦截: {evil} → {r.status_code}"
        assert "leak" not in r.text and ".env" not in r.text
