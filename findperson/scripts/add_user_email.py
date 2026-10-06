# -*- coding: utf-8 -*-
"""人员表 email 列迁移 + 邮箱生成(幂等,可重复执行)。

兼容双表:自动探测 public.users / public.user2,存在的表都会处理
(本地库=users;部署服务器历史遗留=user2;以真实通讯录库为准)。

规则(行内真实规律,样例:刘成彦=liuchy、冉紫萱=ranzx):
  姓全拼 + 名声母(zh/ch/sh 保留双字母) + @bosc.cn
  如 刘成彦 -> liu+ch+y -> liuchy@bosc.cn(成=cheng 声母 ch,非 c);
     冉紫萱 -> ran+z+x -> ranzx@bosc.cn;单名 卢易 -> lu+y -> luy@bosc.cn
  零声母字(如 安)取全拼首字母。
冲突:同拼者后缀从 1 递增(如 wangjj、wangjj1、wangjj2)
例外(人工指定):师沛琳=shipl2@bosc.cn、胡申民=hushm1@bosc.cn

依赖:pip install pypinyin psycopg2-binary
用法:python scripts/add_user_email.py
"""
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import psycopg2
from pypinyin import Style, lazy_pinyin

DB = dict(
    host=os.environ.get("PGHOST", "localhost"),
    port=int(os.environ.get("PGPORT", "5432")),
    user=os.environ.get("PGUSER", "swzr_admin"),
    password=os.environ.get("PGPASSWORD", ""),  # 口令不入库
    dbname=os.environ.get("PGDATABASE", "shouwenzeren_newdb"),
)

# 人工指定的例外(按姓名匹配)
OVERRIDES = {
    "师沛琳": "shipl2@bosc.cn",
    "胡申民": "hushm1@bosc.cn",
}


def _initial(char: str) -> str:
    """单字声母(zh/ch/sh 保留双字母);零声母取全拼首字母。"""
    ini = lazy_pinyin(char, style=Style.INITIALS, errors="ignore")
    if ini and ini[0]:
        return ini[0]
    full = lazy_pinyin(char, style=Style.NORMAL, errors="ignore")
    return full[0][:1] if full else ""


def build_email(name: str, used: set) -> str:
    """姓全拼+名声母;冲突后缀 1,2,3..."""
    full = lazy_pinyin(name or "", style=Style.NORMAL)
    if not full:
        return ""
    surname = full[0]
    initials = "".join(_initial(c) for c in (name or "")[1:])
    base = (surname + initials).lower()
    candidate, seq = base, 0
    while f"{candidate}@bosc.cn" in used:
        seq += 1
        candidate = f"{base}{seq}"
    return f"{candidate}@bosc.cn"


def migrate_table(cur, table: str) -> None:
    """对单张表幂等加列并生成全部邮箱。"""
    cur.execute(f"ALTER TABLE public.{table} ADD COLUMN IF NOT EXISTS email VARCHAR(128)")
    cur.execute(f"SELECT id, name FROM public.{table} ORDER BY id")
    rows = cur.fetchall()

    # 例外先占位,避免与生成值撞车
    used = set(OVERRIDES.values())
    results = []
    for uid, name in rows:
        if name in OVERRIDES:
            email = OVERRIDES[name]
        else:
            email = build_email(name, used)
            used.add(email)
        results.append((uid, name, email))
        cur.execute(f"UPDATE public.{table} SET email = %s WHERE id = %s", (email, uid))

    print(f"[{table}] 完成:共 {len(rows)} 人(规则:姓全拼+名声母,例外 {len(OVERRIDES)} 人)")
    for uid, name, email in results[:5]:
        print("  ", uid, name, email)
    for uid, name, email in results:
        if name in OVERRIDES:
            print("  例外:", uid, name, email)
    cur.execute(f"SELECT count(*) FROM public.{table} WHERE email IS NULL OR email = ''")
    print("  仍缺邮箱:", cur.fetchone()[0], "人")


conn = psycopg2.connect(**DB)
cur = conn.cursor()

# 探测存在的表(users 优先,历史遗留 user2 兼容)
cur.execute("SELECT to_regclass('public.users'), to_regclass('public.user2')")
users_t, user2_t = cur.fetchone()
tables = [t for t, exists in (("users", users_t), ("user2", user2_t)) if exists]
if not tables:
    print("错误:public.users / public.user2 均不存在,请确认连接的数据库")
    sys.exit(1)
print("探测到人员表:", ", ".join(tables))

for table in tables:
    migrate_table(cur, table)

conn.commit()
conn.close()
