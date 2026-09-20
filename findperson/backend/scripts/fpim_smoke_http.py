"""IM 内核端到端自测（HTTP 层）。

链路：登录 → 取或建单聊 → 发消息（含幂等）→ 拉历史/增量 → 未读 → 已读 → 建群 → 越权拒绝。

用法：
    # 起服务（另开终端）—— 口令不入库，由环境变量提供
    DATABASE_URL="postgresql://swzr_admin@localhost:5432/fpim_dev" \
      PGPASSWORD=<数据库口令> \
      venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8002

    # 清数据后跑（推荐：脚本本身是状态无关的，但历史消息累积会让条数断言失真）
    venv/bin/python scripts/fpim_smoke_http.py --reset
    venv/bin/python scripts/fpim_smoke_http.py http://127.0.0.1:8002

凭据来源：脚本会读取 backend/.env（不入库）；也可用环境变量覆盖：
    SEED_PASSWORD  种子账号登录口令（必填）
    FPIM_DSN       开发库连接串（默认不带口令，由 PGPASSWORD 提供）
    PGPASSWORD     数据库口令（libpq 自动读取）

退出码：0 = 全通过，1 = 有失败，2 = 缺少凭据。
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def _load_env() -> None:
    """读取 backend/.env（不入库）；已存在的环境变量优先。"""
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_env()

DEFAULT_BASE = "http://127.0.0.1:8002"
# 口令不入库：DSN 不带口令，由 PGPASSWORD 提供
DEFAULT_DSN = os.environ.get("FPIM_DSN", "postgresql://swzr_admin@localhost:5432/fpim_dev")
ACCOUNTS = {"A": "P0004", "B": "P0005", "C": "P0006"}
PASSWORD = os.environ.get("SEED_PASSWORD", "")

# 沙箱/公司网络常注入 HTTP_PROXY，本地回环请求必须绕开，否则会被代理拦成 502
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
urllib.request.install_opener(_opener)


def reset_dev_data(dsn: str) -> None:
    """清空 IM 业务数据 + 复位 issues 的会话/留痕字段（仅用于开发库）。"""
    import psycopg2  # 延迟导入：仅在 --reset 时需要

    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE im.conversations, im.messages, "
                    "im.conversation_members, im.attachments RESTART IDENTITY CASCADE")
        cur.execute("UPDATE public.issues SET conversation_id = NULL, "
                    "first_read_at = NULL, first_response_at = NULL")
        # 清掉历次自测产生的问题与事件，避免断言受历史数据影响
        cur.execute("DELETE FROM public.knowledge_candidates")
        cur.execute("DELETE FROM public.issue_events WHERE detail IN "
                    "('责任人首次查看','在会话内立项') OR event_type = 'read'")
        cur.execute("DELETE FROM public.issues WHERE source = 'chat'")
    print("♻️  已重置开发库 IM 数据")


class Client:
    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def call(self, method, path, token=None, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with _opener.open(req, timeout=10) as resp:
                raw = resp.read().decode()
                return resp.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()[:300]

    def login(self, account):
        st, data = self.call("POST", "/api/v1/auth/login",
                             body={"account": account, "password": PASSWORD})
        assert st == 200, f"登录 {account} 失败 {st}: {data}"
        return data["token"], data["user"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base", nargs="?", default=DEFAULT_BASE)
    ap.add_argument("--reset", action="store_true", help="先清空开发库 IM 数据")
    ap.add_argument("--dsn", default=DEFAULT_DSN, help="--reset 使用的数据库连接串")
    args = ap.parse_args()

    if args.reset:
        reset_dev_data(args.dsn)

    c = Client(args.base)
    ok = fail = 0

    def check(label, cond, extra=""):
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  ✅ {label}")
        else:
            fail += 1
            print(f"  ❌ {label} {extra}")

    print("=" * 62)
    print("1. 登录三个用户")
    t_a, u_a = c.login(ACCOUNTS["A"])
    t_b, u_b = c.login(ACCOUNTS["B"])
    t_c, u_c = c.login(ACCOUNTS["C"])
    print(f"   A={u_a['id']} {u_a['name']} | B={u_b['id']} {u_b['name']} | C={u_c['id']} {u_c['name']}")

    print("\n2. 取或建单聊（免加好友）")
    st, conv = c.call("POST", "/api/v1/im/conversations/direct", t_a, {"peerId": ACCOUNTS["B"]})
    check("建单聊 200", st == 200, conv)
    cid = conv["id"] if st == 200 else None
    print(f"   conversationId={cid} type={conv.get('type')} peer={conv.get('peer', {}).get('name')}")

    print("\n3. 单聊去重：同两人任何方向都只有一条")
    st2, conv2 = c.call("POST", "/api/v1/im/conversations/direct", t_a, {"peerId": ACCOUNTS["B"]})
    check("同方向复用同一会话", st2 == 200 and conv2["id"] == cid, f"{conv2.get('id')} vs {cid}")
    st3, conv3 = c.call("POST", "/api/v1/im/conversations/direct", t_b, {"peerId": ACCOUNTS["A"]})
    check("反方向命中也同一会话", st3 == 200 and conv3["id"] == cid, f"{conv3.get('id')} vs {cid}")

    print("\n4. A 发消息")
    st, r1 = c.call("POST", f"/api/v1/im/conversations/{cid}/messages", t_a,
                    {"text": "报销系统的权限申请走哪个流程？", "clientMsgId": "e2e-001"})
    check("发消息 200", st == 200, r1)
    msg1 = r1["message"] if st == 200 else {}
    print(f"   seq={msg1.get('seq')} sender={msg1.get('senderId')} id={msg1.get('id')}")

    print("\n5. 幂等：同 clientMsgId 重发不产生第二条")
    st, r2 = c.call("POST", f"/api/v1/im/conversations/{cid}/messages", t_a,
                    {"text": "报销系统的权限申请走哪个流程？", "clientMsgId": "e2e-001"})
    check("重发返回同一条消息", st == 200 and r2["message"]["id"] == msg1.get("id")
          and r2.get("created") is False, r2)

    print("\n6. B 回消息")
    st, r3 = c.call("POST", f"/api/v1/im/conversations/{cid}/messages", t_b,
                    {"text": "走 OA 的费用报销模块，先提申请再找部门负责人审批。", "clientMsgId": "e2e-002"})
    check("B 发消息 200", st == 200, r3)
    msg2 = r3["message"] if st == 200 else {}
    check("seq 严格递增", msg2.get("seq", 0) > msg1.get("seq", 0),
          f"{msg1.get('seq')} → {msg2.get('seq')}")

    print("\n7. 拉历史消息")
    st, hist = c.call("GET", f"/api/v1/im/conversations/{cid}/messages", t_a)
    items = hist["items"] if st == 200 else []
    check("历史含 2 条", st == 200 and len(items) == 2, f"实际 {len(items)} 条")
    check("按 seq 升序", [m["seq"] for m in items] == sorted(m["seq"] for m in items))

    print("\n8. 增量拉取（afterSeq）")
    st, inc = c.call("GET", f"/api/v1/im/conversations/{cid}/messages?afterSeq={msg1.get('seq')}", t_a)
    check("增量只返回 1 条", st == 200 and len(inc["items"]) == 1, f"实际 {len(inc['items'])} 条")

    print("\n9. 会话列表与未读")
    st, lst = c.call("GET", "/api/v1/im/conversations", t_a)
    mine = next((x for x in lst["items"] if x["id"] == cid), None)
    check("会话出现在列表", mine is not None)
    check("最后一条消息已带出", bool(mine and mine.get("lastMessage")),
          mine.get("lastMessage") if mine else None)
    check("A 未读为 1（B 的那条）", bool(mine and mine["unreadCount"] == 1),
          f"unreadCount={mine.get('unreadCount') if mine else None}")

    print("\n10. 已读游标")
    st, rr = c.call("POST", f"/api/v1/im/conversations/{cid}/read", t_a, {"seq": msg2.get("seq", 0)})
    check("已读 200 且未读归零", st == 200 and rr.get("unreadCount") == 0, rr)

    print("\n11. 非成员不能读会话")
    st, _ = c.call("GET", f"/api/v1/im/conversations/{cid}/messages", t_c)
    check("非成员被拒 403", st == 403, f"实际 {st}")

    print("\n12. 建群（上限 100）")
    st, grp = c.call("POST", "/api/v1/im/conversations/group", t_a,
                     {"title": "报销权限问题会诊",
                      "memberIds": [ACCOUNTS["B"], ACCOUNTS["C"], "P0007"]})
    check("建群 200", st == 200, grp)
    if st == 200:
        check("成员 4 人（含群主）", len(grp.get("members", [])) == 4,
              [m["name"] for m in grp.get("members", [])])
        st, over = c.call("POST", "/api/v1/im/conversations/group", t_a,
                          {"title": "超限群",
                           "memberIds": [ACCOUNTS["B"]] + [f"P{i:04d}" for i in range(10, 115)]})
        check("超 100 人被拒 400", st == 400, f"实际 {st} {over}")

    print("\n13. 会话详情")
    st, detail = c.call("GET", f"/api/v1/im/conversations/{cid}", t_a)
    check("详情 200 且带 peer", st == 200 and detail.get("peer", {}).get("id") == ACCOUNTS["B"], detail)

    # ── 问题闭环：会话内立项 → 自动挂接 → 留痕 → 解决确认 ──
    print("\n14. 会话内立项（单聊默认对方为责任人）")
    st, res = c.call("POST", f"/api/v1/im/conversations/{cid}/issues", t_a,
                     {"question": "报销系统的权限申请该走哪个流程？"})
    check("立项 200", st == 200, res)
    issue = res.get("issue", {}) if st == 200 else {}
    iid = issue.get("id")
    check("默认责任人为对方", issue.get("assigneePersonId") == ACCOUNTS["B"],
          f"实际 {issue.get('assigneePersonId')}")
    check("状态即 processing（立项卡本身就是联系动作）", issue.get("status") == "processing")
    check("立项卡消息已插入（issue_card）",
          res.get("message", {}).get("msgType") == "issue_card", res.get("message"))

    print("\n15. 立项后普通消息自动挂接问题")
    st, r = c.call("POST", f"/api/v1/im/conversations/{cid}/messages", t_a,
                   {"text": "想确认一下这个流程", "clientMsgId": "loop-1"})
    check("自动挂接活跃问题", st == 200 and r["message"].get("issueId") == iid, r.get("message"))

    print("\n16. 责任人回复 → first_response_at 落库")
    st, r = c.call("POST", f"/api/v1/im/conversations/{cid}/messages", t_b,
                   {"text": "走 OA 费用报销模块，先提申请。", "clientMsgId": "loop-2"})
    st, brief = c.call("GET", f"/api/v1/im/conversations/{cid}/issues", t_a)
    iss = next((i for i in brief.get("items", []) if i["id"] == iid), {})
    check("firstResponseAt 已记录", bool(iss.get("firstResponseAt")), iss)

    print("\n17. 问题级首次已读：只认责任人、不可覆盖")
    st, r1 = c.call("POST", f"/api/v1/im/issues/{iid}/read", t_b)
    st, r2 = c.call("POST", f"/api/v1/im/issues/{iid}/read", t_b)
    st, r3 = c.call("POST", f"/api/v1/im/issues/{iid}/read", t_a)
    check("责任人首次=已记录", r1.get("recorded") is True, r1)
    check("责任人重复=忽略", r2.get("recorded") is False, r2)
    check("非责任人=不记", r3.get("recorded") is False, r3)

    print("\n18. 提问方标记已解决 → resolve_confirm 消息 + 沉淀候选")
    st, upd = c.call("PATCH", f"/api/v1/issues/{iid}", t_a,
                     {"status": "resolved", "resolutionNote": "走 OA 费用报销模块即可"})
    check("标记解决 200", st == 200, upd)
    st, hist = c.call("GET", f"/api/v1/im/conversations/{cid}/messages?afterSeq=0&limit=50", t_a)
    rc = [m for m in hist.get("items", []) if m.get("msgType") == "resolve_confirm"]
    check("resolve_confirm 恰好 1 条且 sender=system",
          len(rc) == 1 and rc[0].get("senderId") == "system",
          [(m["msgType"], m.get("senderId")) for m in hist.get("items", [])])
    check("resolve_confirm 挂接问题", bool(rc and rc[0].get("issueId") == iid))

    print("\n19. 解决后消息不再自动挂接（已结问题不被闲谈污染）")
    st, r = c.call("POST", f"/api/v1/im/conversations/{cid}/messages", t_a,
                   {"text": "好的搞定了", "clientMsgId": "loop-3"})
    check("解决后 issueId 为空", st == 200 and r["message"].get("issueId") is None,
          r.get("message"))

    print("\n20. 闭环权限边界")
    st, r = c.call("PATCH", f"/api/v1/issues/{iid}", t_b, {"status": "resolved"})
    check("非提问方不能标记已解决 403", st == 403, r)
    st, res = c.call("POST", f"/api/v1/im/conversations/{cid}/issues", t_a,
                     {"question": "权限校验专用问题", "assigneePersonId": ACCOUNTS["B"]})
    iid2 = res.get("issue", {}).get("id")
    st, r = c.call("POST", f"/api/v1/im/conversations/{cid}/issues", t_a,
                   {"question": "自问自答？", "assigneePersonId": ACCOUNTS["A"]})
    check("责任人不能是自己 400", st == 400, r)
    st, r = c.call("POST", f"/api/v1/im/conversations/{cid}/issues", t_c, {"question": "越权"})
    check("非成员不能立项 403", st == 403, r)

    print("\n21. 群聊立项：必须显式指定责任人")
    st, grp = c.call("POST", "/api/v1/im/conversations/group", t_a,
                     {"title": "会诊群", "memberIds": [ACCOUNTS["B"], ACCOUNTS["C"]]})
    gid = grp.get("id") if st == 200 else None
    st, r = c.call("POST", f"/api/v1/im/conversations/{gid}/issues", t_a,
                   {"question": "不指定责任人试试"})
    check("群聊不带责任人被拒 400", st == 400, r)
    st, r = c.call("POST", f"/api/v1/im/conversations/{gid}/issues", t_a,
                   {"question": "跨部门报销权限怎么协调", "assigneePersonId": ACCOUNTS["C"]})
    check("群聊指定责任人后立项成功", st == 200, r)

    print("\n22. 待办视角（/issues/assigned）")
    st, r = c.call("GET", "/api/v1/issues/assigned", t_b)
    check("assigned 200 且不被 /issues/{id} 吞掉", st == 200 and "items" in r, r)
    mine_b = [i for i in (r.get("items") or []) if i.get("id") == iid]
    check("B 名下含 A 立项的问题", bool(mine_b), f"B 名下 {len(r.get('items') or [])} 个")
    check("assigned 项带 conversationId + askerId",
          bool(mine_b and mine_b[0].get("conversationId") == cid
               and mine_b[0].get("askerId") == ACCOUNTS["A"]), mine_b)
    st, r = c.call("GET", "/api/v1/issues/assigned", t_a)
    check("提问方自己的 assigned 不含该问题", all(i.get("id") != iid for i in (r.get("items") or [])))
    st, r = c.call("GET", "/api/v1/issues", t_a)
    mine_a = next((i for i in (r.get("items") or []) if i.get("id") == iid), {})
    check("/issues 也带闭环字段（firstReadAt/firstResponseAt/conversationId）",
          "firstReadAt" in mine_a and mine_a.get("conversationId") == cid, mine_a)

    # ── 数据画像 + 看板 + 拼音搜索 ──
    print("\n23. 数据画像 / 帮助榜 / 缺口地图 / 拼音搜索")
    st, s = c.call("GET", f"/api/v1/people/{ACCOUNTS['B']}/profile-stats", t_a)
    check("画像 200 且字段齐全", st == 200 and all(
        k in s for k in ("askedCount", "resolvedCount", "helpRank", "faqCount", "period", "last30d")), s)
    check("画像计数与立项一致（B 名下 ≥1 被问）", st == 200 and s.get("askedCount", 0) >= 1,
          f"asked={s.get('askedCount')}")
    st, s0 = c.call("GET", "/api/v1/people/P0007/profile-stats", t_a)
    check("无数据者 rank=null 不报错", st == 200 and s0.get("askedCount") == 0
          and s0.get("helpRank") is None, s0)
    st, _ = c.call("GET", "/api/v1/people/NO_SUCH/profile-stats", t_a)
    check("不存在的人 404", st == 404)
    st, lb = c.call("GET", "/api/v1/issues/leaderboard", t_a)
    check("帮助榜 200 且按解决数降序", st == 200 and [
        i["resolvedCount"] for i in lb.get("items", [])
    ] == sorted([i["resolvedCount"] for i in lb.get("items", [])], reverse=True), lb)
    st, gm = c.call("GET", "/api/v1/issues/gap-map", t_a)
    check("缺口地图 200", st == 200 and "items" in gm, gm)
    st, py = c.call("GET", "/api/v1/people?keyword=yuhaohan", t_a)
    check("拼音全拼搜到 于浩瀚", st == 200 and any(p["id"] == ACCOUNTS["B"] for p in py),
          [p.get("name") for p in (py or [])])
    st, py = c.call("GET", "/api/v1/people?keyword=yhh", t_a)
    check("拼音首字母搜到 于浩瀚", st == 200 and any(p["id"] == ACCOUNTS["B"] for p in py),
          [p.get("name") for p in (py or [])])

    # ── 小管家通知（系统号） ──
    print("\n24. 小管家通知（立项/解决都通知责任人，同一栏累积）")
    # §18 已把 iid 标记为已解决 → 为干净起见另立一个
    st, res = c.call("POST", f"/api/v1/im/conversations/{cid}/issues", t_a,
                     {"question": "小管家验证：差旅报销的审批人是谁？"})
    check("立项响应带 notify", st == 200 and res.get("notify", {}).get("toUserId") == ACCOUNTS["B"],
          res.get("notify"))
    ncid = res.get("notify", {}).get("conversationId") if st == 200 else None
    st, lst = c.call("GET", "/api/v1/im/conversations", t_b)
    bot = [x for x in (lst.get("items") or []) if (x.get("peer") or {}).get("id") == "system"]
    check("责任人列表出现小管家且 peer 名字正确", bool(bot) and bot[0]["peer"]["name"] == "小管家",
          [(x.get("peer") or {}).get("name") for x in (lst.get("items") or [])])
    check("小管家栏未读 ≥1", bool(bot) and bot[0].get("unreadCount", 0) >= 1)
    if ncid:
        st, msgs = c.call("GET", f"/api/v1/im/conversations/{ncid}/messages", t_b)
        texts = [m.get("content", {}).get("text", "") for m in msgs.get("items", [])]
        check("通知内容含提问人与问题", any("师沛琳" in t and "差旅报销" in t for t in texts), texts)
    st, res2 = c.call("POST", f"/api/v1/im/conversations/{cid}/issues", t_a,
                      {"question": "小管家验证：第二个问题"})
    check("再立项仍同一个小管家会话（direct_key 去重）",
          st == 200 and res2.get("notify", {}).get("conversationId") == ncid)
    st, r = c.call("POST", "/api/v1/auth/login", body={"account": "system", "password": "x"})
    check("bot 不能登录（401/403）", st in (401, 403), st)
    st, ppl = c.call("GET", "/api/v1/people?page_size=500", t_a)
    check("bot 不出现在名片库", st == 200 and all(p.get("id") != "system" for p in ppl))

    print("\n" + "=" * 62)
    print(f"结果：{ok} 通过 / {fail} 失败")
    return 1 if fail else 0


if __name__ == "__main__":
    if not PASSWORD:
        print("缺少 SEED_PASSWORD：种子账号登录口令不入库。")
        print("请在 backend/.env 中设置 SEED_PASSWORD，或直接导出该环境变量后重试。")
        sys.exit(2)
    sys.exit(main())
