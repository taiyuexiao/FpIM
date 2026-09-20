# -*- coding: utf-8 -*-
"""构建 public.user2: 结构与 users 相同, domains/self_portrait 按规则重写, 其余列照抄当前 users。

规则(已获批准):
  domains      = seed.sql 出厂 domains ∪ 原始画像提炼的干净标签 ∪ 用户界面上自加的标签
                 (提炼: 括号保护拆分、去括号补充内容、去"主持/负责"等叙述动词、去轮岗/带教叙述句)
  self_portrait = 原始画像本身是通顺句子(含。或；) -> 原样保留(仅清理*号);
                  是短语串/标签串 -> 按"部门+岗位+职责"模板生成一句通顺的话
不修改 users 表, 只新建 user2。幂等: DROP 后重建。
"""
import os
import sys, io, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import psycopg2
from psycopg2.extras import Json

DB = dict(host="localhost", port=5432, user="postgres",
          password=os.environ["PGPASSWORD"], dbname="shouwenzeren_newdb")
SEED = r"C:\python\pycharm\shouwenzeren\_newdb\seed.sql"
REPORT = r"C:\python\pycharm\shouwenzeren\_newdb\user2_report.txt"
ROWS_JSON = r"C:\python\pycharm\shouwenzeren\_newdb\_user2_rows.json"

# ---------- 1. seed.sql 出厂 domains ----------
orig_domains = {}
in_u = False
with open(SEED, encoding="utf-8") as f:
    for ln in f:
        if ln.startswith("COPY public.users"):
            in_u = True
            continue
        if in_u:
            if ln.strip() == "\\.":
                break
            p = ln.rstrip("\n").split("\t")
            if len(p) > 10:
                try:
                    orig_domains[p[0]] = json.loads(p[9]) if p[9] not in ("\\N", "") else []
                except json.JSONDecodeError:
                    orig_domains[p[0]] = []

# ---------- 2. 标签提炼 ----------
PAREN = re.compile(r"[（(][^）)]*[）)]")
VERB = re.compile(r"^(主持|负责|分管|协管|从事|参与|牵头|统筹|主责)")

def split_protect(text):
    """按 、，,；;。. 和空白拆分, 但括号内的分隔符不拆"""
    parts, buf, depth = [], [], 0
    for ch in text:
        if ch in "(（":
            depth += 1
        elif ch in ")）":
            depth = max(0, depth - 1)
        if depth == 0 and ch in "、，,；;。. \t\r\n":
            if buf:
                parts.append("".join(buf))
                buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return parts

def extract_tags(portrait, dept_name):
    """从原始画像提炼干净标签"""
    tags = []
    for piece in split_protect(portrait or ""):
        t = piece.replace("*", "").strip(" 。；;，,、")
        if not t:
            continue
        if re.match(r"^当前在.*轮岗$", t):        # 轮岗叙述, 非标签
            continue
        if re.match(r"^由.+带教$", t):            # 带教叙述, 非标签
            continue
        t = PAREN.sub("", t)                       # 去括号补充说明
        t = VERB.sub("", t)                        # 去叙述动词前缀
        t = re.sub(r"相关工作$", "", t).strip(" 。；;，,、")
        if dept_name and t.startswith(dept_name) and len(t) > len(dept_name):
            t = t[len(dept_name):]                 # 去部门名前缀(标签不必带自家部门名)
        if not t or t == dept_name:
            continue
        if len(t) < 2 or len(t) > 16:              # 过短/过长(句子碎片)丢弃
            continue
        tags.append(t)
    return tags

def is_sentence(p):
    return ("。" in p) or ("；" in p) or (";" in p)

def gen_sentence(dept, role, portrait):
    cleaned = (portrait or "").strip().rstrip("。；; ")
    dept = dept or ""
    if role and "校招" in role:
        return f"{dept}{role}生，目前参与{cleaned}相关工作。"
    if role and ("负责人" in role or "总经理" in role):
        return f"{dept}{role}，主持{cleaned}。"
    rd = role if (role and role != dept) else "成员"
    return f"{dept}{rd}，负责{cleaned}。"

# ---------- 3. 读当前 users + 备份画像 + 部门 ----------
conn = psycopg2.connect(**DB)
cur = conn.cursor()
cur.execute("SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='users' ORDER BY ordinal_position")
cols = [r[0] for r in cur.fetchall()]
cur.execute("SELECT * FROM public.users")
users = [dict(zip(cols, r)) for r in cur.fetchall()]
cur.execute("SELECT id, self_portrait FROM public._portrait_backup")
orig_portrait = {r[0]: (r[1] or "") for r in cur.fetchall()}
cur.execute("SELECT id, name FROM public.departments")
dept_name = {r[0]: r[1] for r in cur.fetchall()}

# ---------- 4. 逐人重写 ----------
out_rows = []
stats = {"kept": 0, "generated": 0, "user_added_kept": 0}
for u in users:
    uid = u["id"]
    portrait = orig_portrait.get(uid, "") or ""
    dept = dept_name.get(u.get("department_id"), "") or ""
    seed_d = list(orig_domains.get(uid, []))
    extracted = extract_tags(portrait, dept)
    # 用户自加标签: 当前 domains 里既不在出厂值、也不在画像原文里的
    cur_d = u.get("domains") or []
    if isinstance(cur_d, str):
        cur_d = json.loads(cur_d)
    user_added = [t for t in cur_d if t not in seed_d and t and t not in portrait]
    new_domains = list(dict.fromkeys([*seed_d, *extracted, *user_added]))
    stats["user_added_kept"] += len(user_added)

    if is_sentence(portrait):
        new_portrait = portrait.replace("*", "").strip()
        stats["kept"] += 1
    else:
        new_portrait = gen_sentence(dept, u.get("role"), portrait) if portrait.strip() else ""
        stats["generated"] += 1

    row = dict(u)
    row["domains"] = new_domains
    row["self_portrait"] = new_portrait
    out_rows.append(row)

# ---------- 5. 建表写入(幂等) ----------
cur.execute("DROP TABLE IF EXISTS public.user2")
cur.execute("CREATE TABLE public.user2 (LIKE public.users INCLUDING ALL)")
col_names = ",".join(cols)
ph = ",".join([f"%({c})s" for c in cols])
for row in out_rows:
    r = dict(row)
    r["domains"] = Json(r["domains"])
    cur.execute(f"INSERT INTO public.user2 ({col_names}) VALUES ({ph})", r)
conn.commit()

# ---------- 6. 报告 ----------
lines = [f"user2 构建完成: {len(out_rows)} 人",
         f"自画像: 原样保留 {stats['kept']} 人 / 模板生成 {stats['generated']} 人",
         f"用户自加标签保留: {stats['user_added_kept']} 个",
         f"domains 为空: {sum(1 for r in out_rows if not r['domains'])} 人", ""]
for uid in ("P0001", "P0005", "P0008", "P0010", "P0025"):
    r = next(x for x in out_rows if x["id"] == uid)
    lines.append(f"{uid} {r['name']}: domains={json.dumps(r['domains'], ensure_ascii=False)}")
    lines.append(f"   self_portrait={r['self_portrait']}")
with open(REPORT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("\n".join(lines))

# 供 Excel 导出用
slim = [{"id": r["id"], "name": r["name"], "dept": dept_name.get(r.get("department_id"), ""),
         "role": r.get("role"), "domains": r["domains"], "self_portrait": r["self_portrait"],
         "contact": r.get("contact") or r.get("phone")} for r in out_rows]
with open(ROWS_JSON, "w", encoding="utf-8") as f:
    json.dump(slim, f, ensure_ascii=False, indent=1)
conn.close()
print("\nJSON 已存:", ROWS_JSON)
