"""Agent 自测执行器 —— 真实 AGUI 链路 + 多维断言 + Markdown 报告。

用法: .\\venv\\Scripts\\python.exe scripts\\run_agent_tests.py [--cases scripts/agent_test_cases.py]
输出: agent_test_report.md(报告,UTF-8) + 控制台摘要。

特性:
- 每条用例一个真实会话,逐轮发送并解析 SSE 事件;
- 用例库独立(scripts/agent_test_cases.py),随时扩充;
- 判定覆盖:意图/卡片类型/内容包含/不得包含/续接通道/诚实空答。
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_test_cases import CASES  # noqa: E402

BASE = "http://127.0.0.1:8100"
USER = "P0001"  # 真实库工号(刘成彦,管理员)
REPORT = Path(__file__).resolve().parent / "agent_test_report.md"


def _post(url: str, payload: dict, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    return urllib.request.urlopen(req, timeout=timeout).read()


def send_turn(session_id: str | None, text: str, assistant_id: str) -> tuple[str, dict]:
    if not session_id:
        sess = json.loads(_post(f"{BASE}/api/agui/sessions", {"title": "auto-test", "userId": USER}))
        session_id = sess["sessionId"]
    raw = _post(f"{BASE}/api/agui/sessions/{session_id}/messages",
                {"message": {"id": f"u-{time.time()}", "role": "user", "text": text},
                 "context": {"userId": USER, "assistantMessageId": assistant_id}}).decode("utf-8")
    intent = (re.search(r'"intent":\s*"(\w+)"', raw) or [None, ""])[1]
    m = re.search(r'"type":\s*"confirmation_card".*', raw, re.S)
    card = m.group(0) if m else ""
    card_type = (re.search(r'"actionType":\s*"(\w+)"', card) or [None, None])[1] if card else None
    answer = "".join(re.findall(r'"delta":\s*"((?:[^"\\]|\\.)*)"', raw))
    names = list(dict.fromkeys(re.findall(r'"name":\s*"([^"]+)"', raw)))
    return session_id, {
        "intent": intent, "card_type": card_type, "card": card,
        "answer": answer, "names": names,
        "continuation": '"continuation": true' in raw,
        "has_rec_cards": "recommendation_cards" in raw,
    }


def evaluate(expect: dict, got: dict) -> tuple[bool, list[str]]:
    fails = []
    if "intent" in expect and got["intent"] != expect["intent"]:
        fails.append(f"意图={got['intent']}(期望{expect['intent']})")
    if "card_type" in expect and got["card_type"] != expect["card_type"]:
        fails.append(f"卡片={got['card_type']}(期望{expect['card_type']})")
    haystack = got["answer"] + got["card"] + " ".join(got["names"])
    if "contains" in expect and not any(k in haystack for k in expect["contains"]):
        fails.append(f"未命中{expect['contains']}")
    if "not_contains" in expect:
        bad = [k for k in expect["not_contains"] if k in haystack]
        if bad:
            fails.append(f"不应出现{bad}")
    if "card_contains" in expect:
        missing = [k for k in expect["card_contains"] if k not in got["card"]]
        if missing:
            fails.append(f"卡片缺{missing}")
    if "continuation" in expect and got["continuation"] != expect["continuation"]:
        fails.append(f"续接={got['continuation']}(期望{expect['continuation']})")
    if "answer_has" in expect and not any(k in got["answer"] for k in expect["answer_has"]):
        fails.append(f"回答缺{expect['answer_has']}")
    if expect.get("no_card") and (got["card"] or got["has_rec_cards"]):
        fails.append("不应出卡片")
    if expect.get("honest_empty"):
        if got["names"] or got["has_rec_cards"]:
            fails.append(f"编造了推荐{got['names']}")
        if "没有" not in got["answer"]:
            fails.append("未诚实空答")
    return (not fails), fails


def main() -> int:
    only = ""
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]
    cases = [c for c in CASES if not only or only in c["name"] or only in c["category"]]
    lines = ["# Agent 自测报告", f"- 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"- 用例: {len(cases)} 条", ""]
    total = passed = 0
    cat_stats: dict[str, list[int]] = {}
    for case in cases:
        lines.append(f"## [{case['category']}] {case['name']}")
        sid = None
        for i, turn in enumerate(case["session"], 1):
            total += 1
            try:
                sid, got = send_turn(sid, turn["q"], f"a-{case['name']}-{i}")
                ok, fails = evaluate(turn["expect"], got)
            except Exception as e:  # noqa: BLE001
                ok, fails, got = False, [f"异常 {type(e).__name__}: {e}"], None
            passed += ok
            stat = cat_stats.setdefault(case["category"], [0, 0])
            stat[0] += ok
            stat[1] += 1
            mark = "✅ PASS" if ok else "❌ FAIL"
            lines.append(f"- T{i} 「{turn['q']}」 {mark}")
            if not ok:
                lines.append(f"  - 失败原因: {'; '.join(fails)}")
                if got:
                    lines.append(f"  - 实际: 意图={got['intent']} 卡片={got['card_type']} 人选={got['names'][:5]}")
        lines.append("")
    lines.append("## 汇总")
    lines.append(f"- 总轮次: {total}  通过: {passed}  失败: {total - passed}  **准确率: {passed/total*100:.1f}%**")
    lines.append("")
    lines.append("| 分类 | 通过/总数 |")
    lines.append("|---|---|")
    for cat, (p, t) in cat_stats.items():
        lines.append(f"| {cat} | {p}/{t} |")
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"total={total} passed={passed} acc={passed/total*100:.1f}% -> {REPORT}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
