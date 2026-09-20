"""首问必答平台 Agent 自测评测集(本地库真实数据为 ground truth)。

评测方案:
- 每条用例经完整 AGUI 链路(/api/agui/sessions → messages SSE);
- 判定点:一级意图正确 + 期望人员进推荐卡片 / 写操作卡片类型与预填正确 /
  闲聊正确闲聊 / 不存在领域诚实空答(不得编造);
- 输出逐条 PASS/FAIL + 总体准确率。
"""
import json
import re
import urllib.request

BASE = "http://127.0.0.1:8100"
USER = "p-0001"

# (问句, 期望意图, 期望命中人名列表(任一命中即过)/或行为断言, 说明)
CASES = [
    # ---- 找人:明确责任 ----
    ("谁负责出入境管理", "find_person", ["徐轩", "茅泽婉"], "exact 概念"),
    ("谁负责hadoop", "find_person", ["林凡然", "方墨川", "满佳辰"], "英文别名"),
    ("申请llm key 找谁", "find_person", ["储安奕", "郝子夏"], "别名+正式责任"),
    ("反欺诈谁在做", "find_person", ["干雪诺", "魏哲若", "梅桐文"], "归并概念"),
    # ---- 找人:兴趣/技能 ----
    ("谁喜欢打篮球", "find_person", ["茅泽婉"], "兴趣找人"),
    ("谁懂模型微调", "find_person", ["p-0037", "p-0068", "p-0129", "p-0134", "司空桐", "宁远", "韩明"], "技能找人"),
    # ---- 找人:联系方式 ----
    ("茅泽婉的电话是多少", "find_person", ["123312312313"], "联系方式(答案文本包含)"),
    # ---- 诚实空答 ----
    ("谁负责量子计算机维修", "find_person", ["__NONE__"], "不存在领域→诚实空答,不得编造"),
    # ---- 写操作 ----
    ("修改我的联系方式为13900000000", "edit:profile", ["13900000000"], "profile 卡预填 contact"),
    ("给徐轩增加标签：量子计算", "edit:review", ["徐轩", "量子计算"], "review 卡预填对象+事项"),
    ("给我自己添加标签：烘焙", "edit:profile", ["烘焙"], "自我标签归 profile"),
    ("发布一篇文章《投产变更窗口规范》", "edit:content", ["投产变更窗口规范"], "content 卡预填标题"),
    ("修改我的自画像为热爱技术的工程师", "edit:profile", ["热爱技术的工程师"], "自画像预填"),
    # ---- 闲聊/边界 ----
    ("你好", "chat", ["首问必答助手"], "问候"),
    ("今天天气怎么样", "chat", [], "无关问题→闲聊或澄清(不得乱找人)"),
]


def post(url, payload, timeout=90):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    return urllib.request.urlopen(req, timeout=timeout)


def run_case(query, session_id=None, assistant_id="a1"):
    sid = session_id
    if not sid:
        sess = json.loads(post(f"{BASE}/api/agui/sessions", {"title": "eval", "userId": USER}).read())
        sid = sess["sessionId"]
    raw = post(f"{BASE}/api/agui/sessions/{sid}/messages",
               {"message": {"id": "mu", "role": "user", "text": query},
                "context": {"userId": USER, "assistantMessageId": assistant_id}}).read().decode("utf-8")
    intent = (re.search(r'"intent":\s*"(\w+)"', raw) or [None, ""])[1]
    names = list(dict.fromkeys(re.findall(r'"name":\s*"([^"]+)"', raw)))
    answer = "".join(re.findall(r'"delta":\s*"((?:[^"\\]|\\.)*)"', raw))
    answer = answer.encode().decode("unicode_escape") if "\\u" in answer else answer
    card_type = (re.search(r'"actionType":\s*"(\w+)"', raw) or [None, None])[1]
    card_json = ""
    m = re.search(r'"type":\s*"confirmation_card".*', raw, re.S)
    if m:
        card_json = m.group(0)
    return {"sid": sid, "intent": intent, "names": names, "answer": answer,
            "card_type": card_type, "card": card_json, "raw": raw}


def main():
    passed = failed = 0
    report = []
    for query, expect, targets, note in CASES:
        try:
            r = run_case(query)
        except Exception as e:
            failed += 1
            report.append(f"[FAIL-ERR] {query} => {type(e).__name__}: {e}")
            continue
        ok = True
        detail = []
        if expect == "find_person":
            if r["intent"] != "find_person":
                ok = False; detail.append(f"意图={r['intent']}")
            if targets == ["__NONE__"]:
                if r["names"]:
                    ok = False; detail.append(f"编造了人:{r['names']}")
                if "没有找到" not in r["answer"] and "没有" not in r["answer"]:
                    ok = False; detail.append("未诚实空答")
            elif not any(t in r["names"] or t in r["answer"] or t in r["raw"] for t in targets):
                ok = False; detail.append(f"未命中 {targets},实际={r['names']}")
        elif expect == "chat":
            if r["intent"] not in ("chat", "unclear"):
                ok = False; detail.append(f"意图={r['intent']}")
            if targets and not any(t in r["answer"] for t in targets):
                ok = False; detail.append("问候语不符")
        elif expect.startswith("edit:"):
            want = expect.split(":")[1]
            if r["card_type"] != want:
                ok = False; detail.append(f"卡片类型={r['card_type']}")
            if not any(t in r["card"] for t in targets):
                ok = False; detail.append(f"预填缺失 {targets}")
        mark = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1
        report.append(f"[{mark}] {query} | {note} | {'; '.join(detail)}")

    # ---- 多轮追问(共享会话) ----
    try:
        sess = json.loads(post(f"{BASE}/api/agui/sessions", {"title": "eval-mt", "userId": USER}).read())
        run_case("徐轩是谁", session_id=sess["sessionId"], assistant_id="a1")
        r2 = run_case("他的电话呢", session_id=sess["sessionId"], assistant_id="a2")
        if "徐轩" in r2["answer"] or "电话" in r2["answer"]:
            passed += 1
            report.append("[PASS] 多轮追问『他的电话呢』(上下文人名补全)")
        else:
            failed += 1
            report.append(f"[FAIL] 多轮追问 => {r2['answer'][:60]}")
    except Exception as e:
        failed += 1
        report.append(f"[FAIL-ERR] 多轮追问 => {e}")

    total = passed + failed
    print("=" * 70)
    for line in report:
        print(line)
    print("=" * 70)
    print(f"总用例 {total} | 通过 {passed} | 失败 {failed} | 准确率 {passed/total*100:.1f}%")


if __name__ == "__main__":
    main()
