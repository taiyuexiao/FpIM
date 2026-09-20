#!/usr/bin/env python3
"""
首问责任平台 Seed 数据生成脚本
────────────────────────────────
输入:  scripts/state_data.json (由 state.js 提取)
      模拟数据/synthetic_people_200.jsonl
      模拟数据/synthetic_articles.jsonl
      模拟数据/concepts_and_relations.json
输出:  scripts/seed.sql (可直接 psql -f 导入)

规模: 300 人 + 30 部门 + 607 篇文章 + 30 概念 + 标签体系
"""

import json
import os
import random
import bcrypt
import textwrap
from datetime import date, datetime, timedelta
from pathlib import Path

random.seed(20260810)

BASE = Path(__file__).resolve().parent.parent
SCRIPTS = BASE / "scripts"
OUTPUT = SCRIPTS / "seed.sql"
SIMU = BASE / "模拟数据"

# 内容状态：前端/state.js 中文 → DB 英文（与 backend/app/api/v1/contents.py 的 _STATUS_MAP 一致）
_STATUS_CN_TO_EN = {
    "草稿": "draft",
    "待审核": "pending_review",
    "已发布": "published",
    "已驳回": "rejected",
}

# ── helpers ──────────────────────────────────────────────────────────────

def sql_quote(s):
    """Escape a string for SQL '' quoting."""
    if s is None:
        return "NULL"
    return "'" + str(s).replace("'", "''") + "'"

def jsonb(arr):
    """Format a Python list/dict as JSONB literal."""
    if arr is None:
        return "'[]'"
    return sql_quote(json.dumps(arr, ensure_ascii=False))

def ts(dt):
    """Format a datetime as TIMESTAMPTZ literal."""
    if dt is None:
        return "NULL"
    if isinstance(dt, str):
        return sql_quote(dt)
    return sql_quote(dt.strftime("%Y-%m-%d %H:%M:%S+08"))

def hash_pw(pw=None):
    """Bcrypt hash matching backend BcryptHashContext(rounds=12).

    口令不入库：由 SEED_PASSWORD 环境变量提供。
    """
    pw = pw or os.environ.get("SEED_PASSWORD")
    if not pw:
        raise RuntimeError("缺少 SEED_PASSWORD：请在 .env 中配置种子账号初始口令")
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=12)).decode()

def first_n(text, n=200):
    """Truncate text to first N chars."""
    if not text:
        return ""
    return text[:n]

# ── load inputs ───────────────────────────────────────────────────────────

print("Loading state_data.json ...")
with open(SCRIPTS / "state_data.json", encoding="utf-8") as f:
    state = json.load(f)

print("Loading synthetic_people_200.jsonl ...")
syn_people = []
with open(SIMU / "synthetic_people_200.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            syn_people.append(json.loads(line))

print("Loading synthetic_articles.jsonl ...")
syn_articles = []
with open(SIMU / "synthetic_articles.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            syn_articles.append(json.loads(line))

print("Loading concepts_and_relations.json ...")
with open(SIMU / "concepts_and_relations.json", encoding="utf-8") as f:
    concepts_data = json.load(f)

print(f"  state: {len(state['people'])} people, {len(state['departments'])} depts, "
      f"{len(state['contents'])} contents, {len(state['manuals'])} manuals")
print(f"  synthetic: {len(syn_people)} people, {len(syn_articles)} articles, "
      f"{len(concepts_data['concepts'])} concepts")

# ── 1. DEPARTMENTS (from state.js, 30 nodes) ──────────────────────────────

# Build ID map: dept name → integer ID
dept_list = state["departments"]  # ordered: root first, then children
dept_name_to_id = {}
dept_rows = []

for i, d in enumerate(dept_list):
    did = i + 1  # 1-based
    dept_name_to_id[d["name"]] = did

for i, d in enumerate(dept_list):
    did = i + 1
    parent_id = dept_name_to_id.get(
        d["path"][-2] if len(d.get("path", [])) >= 2 else None
    )
    dept_rows.append({
        "id": did,
        "name": d["name"],
        "level": len(d.get("path", [])),
        "parent_id": parent_id,
        "leader_id": d.get("leaderId") or None,  # will remap after users built
        "path": json.dumps(d.get("path", []), ensure_ascii=False),
        "responsibility": d.get("responsibility", ""),
        "status": "active",
    })

# Identify leaf departments (departments with no children)
parent_ids = {d["parent_id"] for d in dept_rows if d["parent_id"] is not None}
leaf_dept_ids = [d["id"] for d in dept_rows if d["id"] not in parent_ids]

print(f"  30 departments: {len(leaf_dept_ids)} leaf nodes for random assignment")

# ── 2. USERS ──────────────────────────────────────────────────────────────
# Strategy:
#   P0001-P0200: from 模拟数据/ (200 people), random dept assignment
#   P0201-P0300: from state.js (100 people → fit into 65 slots) + 35 generated
#   state.js has 100 people but we only need 65 slots to reach 300 total
#   Actually: 200 (syn) + 100 (state) = 300 exactly! No need to generate extra.
#   Wait, the user said 300 total with 65 from state.js + 35 extra.
#   But state_data.json has 100 people. Let me re-read the user's request...
#   "方案C吧，但是我要300人，也就是说把state.js那65人也要放进来"
#   So user thinks state.js has ~65. But it actually has 100 (after dynamic generation).
#   Let me use all 100 state.js people + 200 syn = 300. Perfect.

ALL_PEOPLE_COUNT = 300  # 200 syn + 100 state

# Password hash (same for all dev accounts, bcrypt rounds=12); 口令由 SEED_PASSWORD 提供
DEV_PW_HASH = hash_pw()

# Build user rows
user_rows = []
used_ids = set()
used_accounts = set()

# ── 2a. Synthetic 200 people (P0001-P0200) ──
for sp in syn_people:
    pid = sp["person_id"]  # P0001-P0200
    used_ids.add(pid)

    # Randomly assign a leaf department
    dept_id = random.choice(leaf_dept_ids)
    dept_name = next((d["name"] for d in dept_rows if d["id"] == dept_id), None)

    account = pid.lower()  # p0001
    used_accounts.add(account)

    # Determine system_role: a few admins
    system_role = "管理员" if pid in ("P0001", "P0010", "P0050", "P0100", "P0150") else "普通成员"

    user_rows.append({
        "id": pid,
        "account": account,
        "phone": sp.get("phone", ""),
        "password_hash": DEV_PW_HASH,
        "name": sp["name"],
        "system_role": system_role,
        "department_id": dept_id,
        "role": sp.get("job_title", sp.get("duty_name", "")),
        "contact": sp.get("phone", ""),
        "domains": json.dumps(
            [sp.get("primary_concept_name", "")] +
            [c.replace("concept-", "") for c in sp.get("secondary_concept_ids", [])],
            ensure_ascii=False
        ),
        "self_portrait": sp.get("self_intro", ""),
        "completeness": random.randint(70, 98),
        "recommended_count": random.randint(0, 120),
        "active": True,
        "source": "synthetic",
        # Extra fields for tag extraction
        "_self_tags": sp.get("self_tags", []),
        "_peer_tags": sp.get("peer_tags", []),
        "_department_name": dept_name,
        "_primary_concept_id": sp.get("primary_concept_id"),
    })

# ── 2b. State.js 100 people → remap to P0201-P0300 ──
state_id_map = {}  # old_id → new_id
for i, sp in enumerate(state["people"]):
    new_id = f"P{201 + i:04d}"  # P0201-P0300
    state_id_map[sp["id"]] = new_id
    used_ids.add(new_id)

    # Map department name → ID
    dept_name = sp.get("department", "")
    dept_id = dept_name_to_id.get(dept_name)
    if dept_id is None:
        # Assign random leaf if department not found
        dept_id = random.choice(leaf_dept_ids)

    account = new_id.lower()
    # Handle potential account collision
    while account in used_accounts:
        account = f"{new_id.lower()}x"
    used_accounts.add(account)

    # system_role: department heads → 部门负责人 role mapping
    system_role = "普通成员"
    if sp.get("id", "").startswith("p-dept-leader-") or "负责人" in sp.get("role", ""):
        system_role = "普通成员"  # 部门负责人 is a position, not necessarily admin
    if sp["id"] == "p-chen":
        system_role = "管理员"

    # domains: flat list from state.js
    domains = sp.get("domains", [])

    # recommended_count from map
    rec_count = state.get("recommended", {}).get(sp["id"], random.randint(0, 80))

    user_rows.append({
        "id": new_id,
        "account": account,
        "phone": sp.get("contact", ""),
        "password_hash": DEV_PW_HASH,
        "name": sp["name"],
        "system_role": system_role,
        "department_id": dept_id,
        "role": sp.get("role", "专员"),
        "contact": sp.get("contact", ""),
        "domains": json.dumps(domains, ensure_ascii=False),
        "self_portrait": sp.get("selfPortrait", ""),
        "completeness": sp.get("completeness", 80),
        "recommended_count": rec_count,
        "active": True,
        "source": "statejs",
        "_self_tags": domains,  # flat domains as tags
        "_peer_tags": [],
        "_department_name": dept_name,
        "_primary_concept_id": None,
    })

# After building all users, remap department leader_id references
for d in dept_rows:
    if d["leader_id"] and d["leader_id"] in state_id_map:
        d["leader_id"] = state_id_map[d["leader_id"]]

# Also remap leader_id for departments that reference synthetic people
# (state.js leaderId like "p-chen" → P0201; synthetic people keep P0001 etc.)

print(f"  {len(user_rows)} users built ({sum(1 for u in user_rows if u['source']=='synthetic')} syn + "
      f"{sum(1 for u in user_rows if u['source']=='statejs')} state)")

# ── 3. CONTENTS ──────────────────────────────────────────────────────────

content_rows = []

# ── 3a. 593 articles from 模拟数据/ ──
for sa in syn_articles:
    aid = sa["article_id"]  # A00001-A00593
    author_id = sa["author_id"]  # P0001-P0200 (kept as-is)
    # Department: use author's assigned department
    author = next((u for u in user_rows if u["id"] == author_id), None)
    dept_id = author["department_id"] if author else None

    # Determine status: all synthetic articles are "published"
    status = "published"

    content_rows.append({
        "id": aid,
        "owner_id": author_id,
        "title": sa["title"],
        "tags": json.dumps(sa.get("hidden_tags", []), ensure_ascii=False),
        "summary": first_n(sa.get("body", ""), 200),
        "body": sa.get("body", ""),
        "status": status,
        "version": 1,
        "submitted_at": None,
        "audit_trail": json.dumps([], ensure_ascii=False),
        "published_snapshot": None,
        "deleted_at": None,
        "pinned": False,
        "published_at": sa.get("publish_date"),
        "weekly_query_count": random.randint(0, 30),
        "weekly_recommend_count": random.randint(0, 15),
    })

# ── 3b. 14 articles from state.js → A00594-A00607 ──
for i, sc in enumerate(state["contents"]):
    old_owner = sc.get("ownerId", "")
    new_owner = state_id_map.get(old_owner, user_rows[0]["id"])

    content_rows.append({
        "id": f"A{594 + i:05d}",
        "owner_id": new_owner,
        "title": sc.get("title", ""),
        "tags": json.dumps(sc.get("tags", []), ensure_ascii=False),
        "summary": sc.get("summary", ""),
        "body": sc.get("body", ""),
        "status": _STATUS_CN_TO_EN.get(sc.get("status"), sc.get("status") or "published"),
        "version": 1,
        "submitted_at": None,
        "audit_trail": json.dumps([], ensure_ascii=False),
        "published_snapshot": None,
        "deleted_at": None,
        "pinned": sc.get("pinned", False),
        "published_at": sc.get("publishedAt", "2025-01-01"),
        "weekly_query_count": sc.get("weeklyQueryCount", 0),
        "weekly_recommend_count": sc.get("weeklyRecommendCount", 0),
    })

print(f"  {len(content_rows)} contents ({len(syn_articles)} syn + {len(state['contents'])} state)")

# ── 4. MANUALS ───────────────────────────────────────────────────────────

manual_rows = []
for i, m in enumerate(state["manuals"]):
    manual_rows.append({
        "title": m.get("title", ""),
        "body": m.get("body", ""),
        "sort_order": i + 1,
    })

print(f"  {len(manual_rows)} manuals")

# ── 5. PEER REVIEWS ─────────────────────────────────────────────────────

# Generate some peer reviews: ~200 entries
review_rows = []
all_user_ids = [u["id"] for u in user_rows]
for _ in range(200):
    reviewer = random.choice(all_user_ids)
    target = random.choice([u for u in all_user_ids if u != reviewer])
    # Tag from state.js domain dictionary or from concepts
    tag_pool = list(state.get("domains", {}).keys()) or ["协同流转", "问题处理", "技术咨询", "流程优化"]
    tag = random.choice(tag_pool)
    review_rows.append({
        "id": f"rv-{random.randint(10000, 99999)}",
        "person_id": target,
        "reviewer_id": reviewer,
        "reviewer_name": next((u["name"] for u in user_rows if u["id"] == reviewer), ""),
        "tag_name": tag,
        "created_at": datetime(2025, random.randint(1, 12), random.randint(1, 28), 10, 0, 0),
    })

# Deduplicate review IDs
seen_rids = set()
unique_reviews = []
for r in review_rows:
    if r["id"] not in seen_rids:
        seen_rids.add(r["id"])
        unique_reviews.append(r)
review_rows = unique_reviews

print(f"  {len(review_rows)} peer reviews")

# ── 6. AGENT: CONCEPTS ──────────────────────────────────────────────────

concept_rows = []
concept_relation_rows = []
concept_name_to_id = {}

for c in concepts_data["concepts"]:
    cid = c["id"]
    concept_name_to_id[c["name"]] = cid
    # Also map aliases
    for alias in c.get("aliases", []):
        concept_name_to_id[alias] = cid

    concept_rows.append({
        "id": cid,
        "name": c["name"],
        "description": "; ".join(c.get("diagnostics", c.get("keywords", []))),
        "embedding": None,  # no actual vectors in seed
        "embedding_model": None,
        "status": "active",
    })

# Build relations from parent references
for c in concepts_data["concepts"]:
    parent_name = c.get("parent")
    if parent_name and parent_name in concept_name_to_id:
        concept_relation_rows.append({
            "source_concept_id": c["id"],
            "relation_type": "child_of",
            "target_concept_id": concept_name_to_id[parent_name],
            "confidence": 1.0,
            "source": "seed",
        })

print(f"  {len(concept_rows)} concepts, {len(concept_relation_rows)} relations")

# ── 7. AGENT: RAW TAGS + PERSON TAGS ────────────────────────────────────

# Extract all unique tags from synthetic people + state.js people
raw_tag_set = {}  # normalized_text → {tag_text, system_part, role_part, duty_part, source_type}

def parse_tag(tag_text):
    """Parse a tag into system/role/duty parts.
    Format: "系统-角色-职责" (e.g., "JVM-总体负责人")
    """
    parts = tag_text.split("-")
    if len(parts) >= 3:
        return parts[0], parts[1], "-".join(parts[2:])
    elif len(parts) == 2:
        return parts[0], parts[1], None
    else:
        return tag_text, None, None

for u in user_rows:
    # Self tags
    for tag in u.get("_self_tags", []):
        tag = str(tag).strip()
        if not tag or len(tag) > 200:
            continue
        norm = tag.lower()
        if norm not in raw_tag_set:
            sys_p, role_p, duty_p = parse_tag(tag)
            raw_tag_set[norm] = {
                "tag_text": tag,
                "normalized_text": norm,
                "source_type": "self",
                "system_part": sys_p,
                "role_part": role_p,
                "duty_part": duty_p,
            }

    # Peer tags
    for tag in u.get("_peer_tags", []):
        tag = str(tag).strip()
        if not tag or len(tag) > 200:
            continue
        norm = tag.lower()
        if norm not in raw_tag_set:
            sys_p, role_p, duty_p = parse_tag(tag)
            raw_tag_set[norm] = {
                "tag_text": tag,
                "normalized_text": norm,
                "source_type": "review",
                "system_part": sys_p,
                "role_part": role_p,
                "duty_part": duty_p,
            }

# Assign tag IDs
raw_tag_rows = []
tag_norm_to_id = {}
for i, (norm, t) in enumerate(sorted(raw_tag_set.items())):
    tid = i + 1
    tag_norm_to_id[norm] = tid
    raw_tag_rows.append({
        "id": tid,
        "tag_text": t["tag_text"],
        "normalized_text": t["normalized_text"],
        "source_type": t["source_type"],
        "system_part": t["system_part"],
        "role_part": t["role_part"],
        "duty_part": t["duty_part"],
        "ref_count": 0,
        "status": "active",
        "created_by": None,
    })

print(f"  {len(raw_tag_rows)} unique raw tags")

# Build person_tags
person_tag_rows = []
pt_id = 0
for u in user_rows:
    all_tags = [str(t).strip().lower() for t in u.get("_self_tags", [])]
    for tag_norm in sorted(set(all_tags)):
        if tag_norm in tag_norm_to_id:
            pt_id += 1
            person_tag_rows.append({
                "id": pt_id,
                "person_id": u["id"],
                "tag_id": tag_norm_to_id[tag_norm],
                "tag_kind": "self_tag",
                "given_by": None,
                "status": "active",
            })

    # Peer tags
    peer_tags = [str(t).strip().lower() for t in u.get("_peer_tags", [])]
    for tag_norm in sorted(set(peer_tags)):
        if tag_norm in tag_norm_to_id:
            pt_id += 1
            person_tag_rows.append({
                "id": pt_id,
                "person_id": u["id"],
                "tag_id": tag_norm_to_id[tag_norm],
                "tag_kind": "review_tag",
                "given_by": random.choice([x for x in all_user_ids if x != u["id"]]),
                "status": "active",
            })

print(f"  {len(person_tag_rows)} person-tag links")

# ── 8. AGENT: TAG-CONCEPT MAP ───────────────────────────────────────────

tag_concept_rows = []
tcm_id = 0
# Match tags to concepts by name overlap
for tag_row in raw_tag_rows:
    tag_name = tag_row["tag_text"].lower()
    for c in concepts_data["concepts"]:
        c_name = c["name"].lower()
        c_aliases = [a.lower() for a in c.get("aliases", [])]
        # Check if tag text contains concept name or alias
        if c_name in tag_name or any(a in tag_name for a in c_aliases):
            tcm_id += 1
            tag_concept_rows.append({
                "tag_id": tag_row["id"],
                "concept_id": c["id"],
                "confidence": 0.9,
                "map_source": "auto_exact",
            })
            break

print(f"  {len(tag_concept_rows)} tag-concept mappings")

# ── 9. CONFIG TABLES ────────────────────────────────────────────────────

# Intent rules
intent_rules = [
    (1, "find_person", "keyword", "找|谁负责|负责人|联系|咨询|处理|负责", True, "找责任人"),
    (2, "update_profile", "keyword", "修改|更新|变更|改为|改成", True, "维护本人资料"),
    (3, "publish_content", "keyword", "发布|发表|发布.*文章|写.*文章", True, "发布内容"),
    (4, "review_peer", "keyword", "画像|评价|补充.*画像", True, "为他人画像"),
]

# Feedback reason options
feedback_reasons = [
    ("NOT_RELEVANT", "推荐不相关", "ticket", True, 1),
    ("WRONG_INFO", "信息有误", "ticket", True, 2),
    ("OUTDATED", "内容已过时", "ticket", True, 3),
    ("ABILITY_MISMATCH", "能力不匹配", "ticket", True, 4),
    ("CONTACT_WRONG", "联系方式错误", "ticket", True, 5),
    ("OTHER", "其他原因", "review", True, 6),
]

# Tag policy: per department (min 2 tags, require duty tag)
tag_policies = [
    {"department_id": d["id"], "min_tags": 2, "require_duty_tag": True}
    for d in dept_rows[:10]  # Top 10 departments
]

# ── 10. RESPONSIBILITY ASSIGNMENTS ──────────────────────────────────────

resp_rows = []
for u in user_rows:
    if u.get("_primary_concept_id") and random.random() < 0.3:
        resp_rows.append({
            "person_id": u["id"],
            "concept_id": u["_primary_concept_id"],
            "verified_by": random.choice(all_user_ids[:5]),
            "status": "active",
        })

print(f"  {len(resp_rows)} responsibility assignments")

# ═══════════════════════════════════════════════════════════════════════════
# SQL GENERATION
# ═══════════════════════════════════════════════════════════════════════════

print("\nGenerating SQL ...")

sql = []
sql.append("-- ============================================================")
sql.append("-- 首问责任平台 Seed Data")
sql.append(f"-- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
sql.append(f"-- 规模: {len(user_rows)} 人, {len(dept_rows)} 部门, {len(content_rows)} 篇内容")
sql.append(f"--      {len(concept_rows)} 概念, {len(raw_tag_rows)} 标签")
sql.append("-- ============================================================")
sql.append("BEGIN;")
sql.append("")

# ── TRUNCATE (idempotent re-run) ──
sql.append("-- 清空现有数据（可重复执行）")
truncate_order = [
    "public.responsibility_assignments",
    "public.peer_reviews",
    "public.recommendation_logs",
    "public.query_logs",
    "public.feedback",
    "public.messages",
    "public.contents",
    "public.manuals",
    "public.sessions",
    "public.users",
    "public.departments",
    "agent.person_tags",
    "agent.tag_concept_map",
    "agent.concept_relations",
    "agent.raw_tags",
    "agent.concepts",
    "agent.intent_rules",
    "agent.feedback_reason_options",
    "agent.tag_policy",
]
for t in truncate_order:
    sql.append(f"DELETE FROM {t};")
# Reset SERIAL sequences
sql.append("ALTER SEQUENCE public.departments_id_seq RESTART WITH 31;")
sql.append("")

# ── departments ──
sql.append("-- ============================================================")
sql.append("-- 1. public.departments (30 rows)")
sql.append("-- ============================================================")
for d in dept_rows:
    # leader_id set to NULL initially to avoid FK violation; updated after users INSERT
    sql.append(
        f"INSERT INTO public.departments (id, name, level, parent_id, leader_id, path, responsibility, status) "
        f"VALUES ({d['id']}, {sql_quote(d['name'])}, {d['level']}, {d['parent_id'] or 'NULL'}, "
        f"NULL, {sql_quote(d['path'])}, {sql_quote(d['responsibility'])}, 'active');"
    )
sql.append("")

# ── users ──
sql.append("-- ============================================================")
sql.append(f"-- 2. public.users ({len(user_rows)} rows)")
sql.append("-- ============================================================")
for u in user_rows:
    sql.append(
        f"INSERT INTO public.users (id, account, phone, password_hash, name, system_role, "
        f"department_id, role, contact, domains, self_portrait, completeness, recommended_count, active) "
        f"VALUES ({sql_quote(u['id'])}, {sql_quote(u['account'])}, {sql_quote(u['phone'])}, "
        f"{sql_quote(u['password_hash'])}, {sql_quote(u['name'])}, {sql_quote(u['system_role'])}, "
        f"{u['department_id']}, {sql_quote(u['role'])}, {sql_quote(u['contact'])}, "
        f"{sql_quote(u['domains'])}, {sql_quote(u['self_portrait'])}, "
        f"{u['completeness']}, {u['recommended_count']}, {'TRUE' if u['active'] else 'FALSE'});"
    )
sql.append("")

# ── update department leader_id after users exist ──
sql.append("-- 2b. Update department leader_id references")
for d in dept_rows:
    if d["leader_id"]:
        sql.append(
            f"UPDATE public.departments SET leader_id = {sql_quote(d['leader_id'])} "
            f"WHERE id = {d['id']};"
        )
sql.append("")

# ── contents ──
sql.append("-- ============================================================")
sql.append(f"-- 3. public.contents ({len(content_rows)} rows)")
sql.append("-- ============================================================")
for c in content_rows:
    body = c.get("body", "") or ""
    # Use dollar quoting to avoid escaping markdown
    body_literal = f"$${body}$$" if body else "NULL"
    sql.append(
        f"INSERT INTO public.contents (id, owner_id, title, tags, summary, body, status, version, "
        f"published_at, pinned, weekly_query_count, weekly_recommend_count, audit_trail) "
        f"VALUES ({sql_quote(c['id'])}, {sql_quote(c['owner_id'])}, {sql_quote(c['title'])}, "
        f"{sql_quote(c['tags'])}, {sql_quote(c['summary'])}, {body_literal}, "
        f"{sql_quote(c['status'])}, {c['version']}, "
        f"{sql_quote(c['published_at'])}, {'TRUE' if c['pinned'] else 'FALSE'}, "
        f"{c['weekly_query_count']}, {c['weekly_recommend_count']}, "
        f"{sql_quote(c['audit_trail'])});"
    )
sql.append("")

# ── manuals ──
sql.append("-- ============================================================")
sql.append(f"-- 4. public.manuals ({len(manual_rows)} rows)")
sql.append("-- ============================================================")
for m in manual_rows:
    body = m["body"] or ""
    body_literal = f"$${body}$$" if body else "NULL"
    sql.append(
        f"INSERT INTO public.manuals (title, body, sort_order) "
        f"VALUES ({sql_quote(m['title'])}, {body_literal}, {m['sort_order']});"
    )
sql.append("")

# ── peer_reviews ──
sql.append("-- ============================================================")
sql.append(f"-- 5. public.peer_reviews ({len(review_rows)} rows)")
sql.append("-- ============================================================")
for r in review_rows:
    sql.append(
        f"INSERT INTO public.peer_reviews (id, person_id, reviewer_id, reviewer_name, tag_name, created_at) "
        f"VALUES ({sql_quote(r['id'])}, {sql_quote(r['person_id'])}, {sql_quote(r['reviewer_id'])}, "
        f"{sql_quote(r['reviewer_name'])}, {sql_quote(r['tag_name'])}, {ts(r['created_at'])});"
    )
sql.append("")

# ── responsibility_assignments ──
sql.append("-- ============================================================")
sql.append(f"-- 6. public.responsibility_assignments ({len(resp_rows)} rows)")
sql.append("-- ============================================================")
for r in resp_rows:
    sql.append(
        f"INSERT INTO public.responsibility_assignments (person_id, concept_id, verified_by, status) "
        f"VALUES ({sql_quote(r['person_id'])}, {sql_quote(r['concept_id'])}, "
        f"{sql_quote(r['verified_by'])}, 'active');"
    )
sql.append("")

# ── agent.concepts ──
sql.append("-- ============================================================")
sql.append(f"-- 7. agent.concepts ({len(concept_rows)} rows)")
sql.append("-- ============================================================")
for c in concept_rows:
    sql.append(
        f"INSERT INTO agent.concepts (id, name, description, status) "
        f"VALUES ({sql_quote(c['id'])}, {sql_quote(c['name'])}, "
        f"{sql_quote(c['description'])}, {sql_quote(c['status'])});"
    )
sql.append("")

# ── agent.concept_relations ──
sql.append("-- ============================================================")
sql.append(f"-- 8. agent.concept_relations ({len(concept_relation_rows)} rows)")
sql.append("-- ============================================================")
for r in concept_relation_rows:
    sql.append(
        f"INSERT INTO agent.concept_relations (source_concept_id, relation_type, target_concept_id, confidence, source) "
        f"VALUES ({sql_quote(r['source_concept_id'])}, {sql_quote(r['relation_type'])}, "
        f"{sql_quote(r['target_concept_id'])}, {r['confidence']}, {sql_quote(r['source'])});"
    )
sql.append("")

# ── agent.raw_tags ──
sql.append("-- ============================================================")
sql.append(f"-- 9. agent.raw_tags ({len(raw_tag_rows)} rows)")
sql.append("-- ============================================================")
for t in raw_tag_rows:
    sql.append(
        f"INSERT INTO agent.raw_tags (id, tag_text, normalized_text, source_type, "
        f"system_part, role_part, duty_part, ref_count, status) "
        f"VALUES ({t['id']}, {sql_quote(t['tag_text'])}, {sql_quote(t['normalized_text'])}, "
        f"{sql_quote(t['source_type'])}, {sql_quote(t['system_part'])}, "
        f"{sql_quote(t['role_part'])}, {sql_quote(t['duty_part'])}, {t['ref_count']}, 'active');"
    )
sql.append("")

# ── agent.person_tags ──
sql.append("-- ============================================================")
sql.append(f"-- 10. agent.person_tags ({len(person_tag_rows)} rows)")
sql.append("-- ============================================================")
for pt in person_tag_rows:
    given_by = sql_quote(pt["given_by"]) if pt["given_by"] else "NULL"
    sql.append(
        f"INSERT INTO agent.person_tags (id, person_id, tag_id, tag_kind, given_by, status) "
        f"VALUES ({pt['id']}, {sql_quote(pt['person_id'])}, {pt['tag_id']}, "
        f"{sql_quote(pt['tag_kind'])}, {given_by}, 'active');"
    )
sql.append("")

# ── agent.tag_concept_map ──
sql.append("-- ============================================================")
sql.append(f"-- 11. agent.tag_concept_map ({len(tag_concept_rows)} rows)")
sql.append("-- ============================================================")
for tc in tag_concept_rows:
    sql.append(
        f"INSERT INTO agent.tag_concept_map (tag_id, concept_id, confidence, map_source) "
        f"VALUES ({tc['tag_id']}, {sql_quote(tc['concept_id'])}, {tc['confidence']}, {sql_quote(tc['map_source'])});"
    )
sql.append("")

# ── agent.intent_rules ──
sql.append("-- ============================================================")
sql.append(f"-- 12. agent.intent_rules ({len(intent_rules)} rows)")
sql.append("-- ============================================================")
for ir in intent_rules:
    sql.append(
        f"INSERT INTO agent.intent_rules (priority, intent, pattern_type, pattern, enabled, note) "
        f"VALUES ({ir[0]}, {sql_quote(ir[1])}, {sql_quote(ir[2])}, "
        f"{sql_quote(ir[3])}, {'TRUE' if ir[4] else 'FALSE'}, {sql_quote(ir[5])});"
    )
sql.append("")

# ── agent.feedback_reason_options ──
sql.append("-- ============================================================")
sql.append(f"-- 13. agent.feedback_reason_options ({len(feedback_reasons)} rows)")
sql.append("-- ============================================================")
for fr in feedback_reasons:
    sql.append(
        f"INSERT INTO agent.feedback_reason_options (reason_code, display_text, action_type, enabled, sort) "
        f"VALUES ({sql_quote(fr[0])}, {sql_quote(fr[1])}, {sql_quote(fr[2])}, "
        f"{'TRUE' if fr[3] else 'FALSE'}, {fr[4]});"
    )
sql.append("")

# ── agent.tag_policy ──
sql.append("-- ============================================================")
sql.append(f"-- 14. agent.tag_policy ({len(tag_policies)} rows)")
sql.append("-- ============================================================")
for tp in tag_policies:
    sql.append(
        f"INSERT INTO agent.tag_policy (department_id, min_tags, require_duty_tag) "
        f"VALUES ({tp['department_id']}, {tp['min_tags']}, {'TRUE' if tp['require_duty_tag'] else 'FALSE'});"
    )
sql.append("")

sql.append("COMMIT;")
sql.append("")
sql.append("-- ============================================================")
sql.append("-- Seed 导入完成")
sql.append("-- 验证: SELECT count(*) FROM public.users;  -- should be 300")
sql.append("--       SELECT count(*) FROM public.contents; -- should be 607")
sql.append("-- ============================================================")

# ── Write output ──
output_sql = "\n".join(sql)
with open(OUTPUT, "w", encoding="utf-8") as f:
    f.write(output_sql)

# Collect final stats
stat_lines = output_sql.count("\n")
file_size_mb = len(output_sql.encode("utf-8")) / (1024 * 1024)

print(f"\n[OK] Written: {OUTPUT}")
print(f"  {stat_lines} lines, {file_size_mb:.1f} MB")
print(f"\nSummary:")
print(f"  departments:          {len(dept_rows)}")
print(f"  users:                {len(user_rows)}")
print(f"  contents:             {len(content_rows)}")
print(f"  manuals:              {len(manual_rows)}")
print(f"  peer_reviews:         {len(review_rows)}")
print(f"  responsibility_assign: {len(resp_rows)}")
print(f"  concepts:             {len(concept_rows)}")
print(f"  concept_relations:    {len(concept_relation_rows)}")
print(f"  raw_tags:             {len(raw_tag_rows)}")
print(f"  person_tags:          {len(person_tag_rows)}")
print(f"  tag_concept_map:      {len(tag_concept_rows)}")
print(f"  intent_rules:         {len(intent_rules)}")
print(f"  feedback_reasons:     {len(feedback_reasons)}")
print(f"  tag_policy:           {len(tag_policies)}")
print(f"\n  Next: psql -U swzr_admin -d shouwenzeren -f scripts/seed.sql")
