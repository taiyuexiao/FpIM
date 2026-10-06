"""raw_tags 乱码修复(本地/服务器通用,UTF-8 被 latin-1 误读):
latin-1 编回字节 → UTF-8 解码;已有同规范文本正确行则合并重挂后删除乱码行。
"""
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.core import db  # noqa: E402

CJK = re.compile(r'[一-鿿]')
MOJI = re.compile(r'[-ÿ]')


def repair(s: str) -> str | None:
    if not s or CJK.search(s) or not MOJI.search(s):
        return None
    try:
        fixed = s.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None
    return fixed if CJK.search(fixed) else None


async def main() -> None:
    await db.init_pool()
    fixed_n, merged_n = 0, 0
    rows = await db.fetch("SELECT tag_id, text FROM agent.raw_tags ORDER BY tag_id")
    for row in rows:
        fixed = repair(row["text"])
        if fixed is None:
            continue
        norm = " ".join(fixed.split()).lower()
        existing = await db.fetchrow(
            "SELECT tag_id FROM agent.raw_tags WHERE normalized_text=$1 AND tag_id<>$2",
            norm, row["tag_id"])
        if existing:
            await db.execute("UPDATE agent.person_tags SET tag_id=$1 WHERE tag_id=$2",
                             existing["tag_id"], row["tag_id"])
            await db.execute("UPDATE agent.tag_concept_map SET tag_id=$1 WHERE tag_id=$2",
                             existing["tag_id"], row["tag_id"])
            await db.execute("DELETE FROM agent.raw_tags WHERE tag_id=$1", row["tag_id"])
            merged_n += 1
            print(f"merged {row['tag_id']} -> {existing['tag_id']}")
        else:
            await db.execute(
                "UPDATE agent.raw_tags SET text=$1, normalized_text=$2 WHERE tag_id=$3",
                fixed, norm, row["tag_id"])
            fixed_n += 1
            print(f"fixed {row['tag_id']}")
    print(f"done: fixed={fixed_n} merged={merged_n}")
    await db.close_pool()

asyncio.run(main())
