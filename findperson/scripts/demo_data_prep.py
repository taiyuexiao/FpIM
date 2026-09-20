#!/usr/bin/env python3
"""TST-03 演示数据整备脚本

校验演示数据是否就绪（20+ 全画像人员 + 种子内容 + 种子评价），
并对已知数据质量问题做幂等修复（内容 status 中英文不一致）。

用法:
    python scripts/demo_data_prep.py            # 只校验 + 打印报告
    python scripts/demo_data_prep.py --fix      # 校验 + 修复已知问题

连接: 复用 docker-compose 的 swzr-pg（swzr_admin / shouwenzeren）。
"""
import argparse
import sys

import psycopg2

# 与 docker-compose.yml 一致；口令不入库，由 PGPASSWORD 环境变量提供
CONNINFO = "host=localhost port=5432 dbname=shouwenzeren user=swzr_admin"

# 目标阈值（低于则判定「未就绪」）
MIN_FULL_PROFILE_PEOPLE = 20
MIN_PUBLISHED_CONTENTS = 20
MIN_REVIEWS = 20

# 中文 → 英文状态（与 backend/app/api/v1/contents.py 的 _STATUS_MAP 一致）
_STATUS_CN_TO_EN = {
    "草稿": "draft",
    "待审核": "pending_review",
    "已发布": "published",
    "已驳回": "rejected",
}


def _connect():
    return psycopg2.connect(CONNINFO)


def _fix_status(cur):
    """把中文状态统一为英文（幂等）。"""
    total = 0
    for cn, en in _STATUS_CN_TO_EN.items():
        cur.execute("UPDATE public.contents SET status = %s WHERE status = %s", (en, cn))
        total += cur.rowcount
    return total


def collect(conn):
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM public.users WHERE active = true")
    total_people = cur.fetchone()[0]
    cur.execute(
        "SELECT count(*) FROM public.users WHERE active = true "
        "AND self_portrait IS NOT NULL AND domains IS NOT NULL AND role IS NOT NULL "
        "AND contact IS NOT NULL AND department_id IS NOT NULL"
    )
    full_profile = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM public.contents WHERE deleted_at IS NULL")
    total_contents = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM public.contents WHERE deleted_at IS NULL AND status = 'published'")
    published = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM public.peer_reviews")
    reviews = cur.fetchone()[0]
    cur.execute("SELECT status, count(*) FROM public.contents WHERE deleted_at IS NULL GROUP BY status ORDER BY status")
    status_dist = dict(cur.fetchall())
    cur.execute("SELECT count(*) FROM public.departments")
    depts = cur.fetchone()[0]
    return {
        "total_people": total_people,
        "full_profile": full_profile,
        "total_contents": total_contents,
        "published": published,
        "reviews": reviews,
        "status_dist": status_dist,
        "depts": depts,
    }


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="TST-03 演示数据整备校验")
    ap.add_argument("--fix", action="store_true", help="修复已知数据质量问题（status 中英文不一致）")
    args = ap.parse_args()

    conn = _connect()
    conn.autocommit = True
    cur = conn.cursor()

    fixed = 0
    if args.fix:
        fixed = _fix_status(cur)

    d = collect(conn)
    conn.close()

    checks = [
        ("20+ 全画像人员", d["full_profile"] >= MIN_FULL_PROFILE_PEOPLE, d["full_profile"]),
        ("种子内容（已发布 >= 20）", d["published"] >= MIN_PUBLISHED_CONTENTS, d["published"]),
        ("种子评价（>= 20）", d["reviews"] >= MIN_REVIEWS, d["reviews"]),
    ]

    print("=" * 56)
    print("演示数据整备校验报告 (TST-03)")
    print("=" * 56)
    print(f"  人员总数        : {d['total_people']}   (全画像 {d['full_profile']})")
    print(f"  部门数          : {d['depts']}")
    print(f"  内容总数        : {d['total_contents']}   (已发布 {d['published']})")
    print(f"  评价数          : {d['reviews']}")
    print(f"  内容状态分布    : {d['status_dist']}")
    print("-" * 56)
    all_ok = True
    for name, ok, val in checks:
        mark = "PASS" if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"  [{mark}] {name}: {val}")
    print("-" * 56)
    if args.fix:
        print(f"  --fix: 已修复 {fixed} 条中文状态 → 英文")
    print("  结论:", "演示数据已就绪 ✅" if all_ok else "演示数据未就绪 ❌（见 FAIL 项）")
    print("=" * 56)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
