"""一次性数据迁移：把 users.self_portrait 里的内容按中文标点拆分成标签，
合并进 users.domains(jsonb 数组)，去重保序。

背景：真实通讯录数据里 self_portrait 存的是「顿号/分号分隔的关键词/职责短语」，
而 domains 大多为空，导致名片标签与「他画像」可选项过少。本脚本把 self_portrait
的内容拆成标签回填到 domains，让标签与画像体系有数据可验证。

安全：仅合并追加(去重)，不删除 domains 已有标签；可重复执行(幂等)。
"""
import json
import os
import re

import psycopg2

# 口令不入库：由 PGPASSWORD 环境变量提供（libpq 自动读取）
DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql://swzr_admin@localhost:5432/shouwenzeren"
)

# 分隔符：顿号/逗号/分号/句号及空白；句号常作结尾，一并剔除
_SPLIT_RE = re.compile(r"[、，,；;。.\s]+")


def split_tags(text):
    if not text:
        return []
    return [t for t in _SPLIT_RE.split(text) if t.strip()]


def main():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT id, self_portrait, domains FROM users")
    rows = cur.fetchall()

    updated = 0
    for uid, self_portrait, domains in rows:
        # psycopg2 读 jsonb 通常已反序列化为 list；兼容 str 情况
        if isinstance(domains, str):
            try:
                domains = json.loads(domains)
            except json.JSONDecodeError:
                domains = []
        existing = domains if isinstance(domains, list) else []
        new_tags = split_tags(self_portrait)
        merged = list(dict.fromkeys([*existing, *new_tags]))  # 去重保序
        if merged == existing:
            continue
        cur.execute(
            "UPDATE users SET domains = %s WHERE id = %s",
            (json.dumps(merged, ensure_ascii=False), uid),
        )
        updated += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"迁移完成：共更新 {updated} 人")


if __name__ == "__main__":
    main()
