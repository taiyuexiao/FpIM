"""人员标签 → Agent 标签体系同步(核心业务流程 §四.7:画像/负责领域参与后续推荐)。

raw_tags 判重 → person_tags 激活/新建 → 概念链接:
精确命中概念(canonical/alias)直接建映射;未命中走 agent-service 的
RawTagConceptLinker(§7.4 五级召回 + LLM 受约束消歧,原始标签归并到中间概念层);
agent 不可达时按 seed_concepts.py 冷启动逻辑兜底建档(不影响业务写入)。
与调用方同一事务,失败随业务回滚。

供 reviews.py(他画像,source=peer_review)与 me.py(负责领域,source=self)共用。

重要:Agent 标签体系(agent schema)由 Agent 团队设计,列结构与早期后端桥接代码
的假设存在差异。此处的同步对业务(人员/画像/领域)而言是"尽力而为":同步失败
只记告警,绝不阻断调用方的业务写入。业务数据(users.domains / peer_reviews)
的持久化由调用方自身的 db.commit() 保证。
"""
import json
import logging
import urllib.request
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.config import settings

logger = logging.getLogger(__name__)


def _normalize(tag: str) -> str:
    return " ".join(tag.split()).lower()


def _ensure_raw_tag(db: Session, tag: str) -> str:
    normalized = _normalize(tag)
    row = db.execute(text("SELECT tag_id FROM agent.raw_tags WHERE normalized_text=:n"),
                     {"n": normalized}).first()
    if row:
        return row[0]
    tag_id = f"tag-{uuid.uuid4().hex[:8]}"
    db.execute(text("INSERT INTO agent.raw_tags(tag_id, text, normalized_text)"
                    " VALUES(:i, :t, :n)"),
               {"i": tag_id, "t": tag, "n": normalized})
    return tag_id


def _ensure_seed_concept(db: Session, tag_text: str) -> str:
    """未命中现有概念时增量建 Seed Concept(概念名=标签原文,status='seed')。

    与标准结构 scripts/seed_concepts.py 冷启动行为一致:seed 概念进入检索侧
    (ConceptRegistry.load_concepts 含 seed),新标签立即可被 ConceptLinker exact 级命中。
    """
    cid = f"concept-auto-{uuid.uuid4().hex[:8]}"
    db.execute(
        text("INSERT INTO agent.concepts(concept_id, canonical_name, concept_type, description, status)"
             " VALUES(:i, :n, 'domain', :d, 'seed')"),
        {"i": cid, "n": tag_text,
         "d": "自动建档:画像/负责领域新标签增量 seed"})
    return cid


def _link_via_agent(tag_text: str) -> str | None:
    """调用 agent-service 的概念链接(§7.4);不可达/失败返回 None(调用方兜底)。"""
    try:
        req = urllib.request.Request(
            f"{settings.AGENT_SERVICE_URL}/agent/tags/link",
            data=json.dumps({"text": tag_text}).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("concept_id")
    except Exception:  # noqa: BLE001
        return None


def _auto_map_concept(db: Session, tag_id: str, normalized: str, *, tag_text: str = "") -> None:
    """精确命中概念/别名时直接建映射(快速确定性路径);
    未命中:不在请求链路里做 LLM(慢且曾致写入超时/重复),也不盲目建碎片概念,
    留为未映射,由 agent-service 的 tag_link_sweep 每30s 做 LLM 归并
    (能挂已有概念就挂,确认是新事物才建新 seed 概念)。
    """
    row = db.execute(
        text("SELECT c.concept_id FROM agent.concepts c"
             " WHERE c.status IN ('seed','active') AND lower(c.canonical_name)=:n"
             " UNION SELECT a.concept_id FROM agent.concept_aliases a"
             " WHERE lower(a.alias)=:n LIMIT 1"),
        {"n": normalized}).first()
    if not row:
        logger.info("概念映射留待 LLM 归并(tag_link_sweep): %s", tag_text or normalized)
        return
    db.execute(text("INSERT INTO agent.tag_concept_map"
                    " (map_id, tag_id, concept_id, mapping_type, confidence,"
                    "  generated_by, review_status, reason)"
                    " VALUES(:i, :t, :c, 'exact_alias', 1.0, 'rule', 'auto_approved', '标准名精确匹配')"
                    " ON CONFLICT (tag_id, concept_id) DO NOTHING"),
               {"i": f"map-{uuid.uuid4().hex[:8]}", "t": tag_id, "c": row[0]})


def sync_tag_to_agent(db: Session, *, person_id: str, tag: str, active: bool,
                      source: str = "peer_review", created_by: str = "review-api",
                      approval: str = "approved") -> None:
    """单个标签同步:raw_tags 判重 → person_tags 激活/新建 → 精确命中建映射。

    approval:他人标签未放行时写 'pending'(检索降权,视图分档);本人/管理员/已放行 'approved'。

    与 Agent 体系同步为"尽力而为",失败仅记告警,不阻断业务写入。
    """
    if not tag or not tag.strip():
        return
    tag = tag.strip()
    try:
        with db.begin_nested():
            tag_id = _ensure_raw_tag(db, tag)
            pt = db.execute(text("SELECT person_tag_id, approval FROM agent.person_tags"
                                 " WHERE person_id=:p AND tag_id=:t AND source=:s"),
                            {"p": person_id, "t": tag_id, "s": source}).first()
            if pt:
                # 已存在:只更新激活态,不降级放行状态(approved 不因重复打标变回 pending)
                db.execute(text("UPDATE agent.person_tags SET is_active=:a WHERE person_tag_id=:i"),
                           {"a": active, "i": pt[0]})
            elif active:
                db.execute(text("INSERT INTO agent.person_tags"
                                " (person_tag_id, person_id, tag_id, source, created_by, is_active, approval)"
                                " VALUES(:i, :p, :t, :s, :c, TRUE, :ap)"),
                           {"i": f"pt-{uuid.uuid4().hex[:8]}", "p": person_id, "t": tag_id,
                            "s": source, "c": created_by, "ap": approval})
            if active:
                _auto_map_concept(db, tag_id, _normalize(tag), tag_text=tag)
    except Exception:  # noqa: BLE001
        logger.warning("标签同步到 Agent 体系失败(已忽略): person=%s tag=%s",
                       person_id, tag, exc_info=True)


def sync_article_tags(db: Session, *, person_id: str) -> None:
    """文章自打标签回流(声明类证据,与自填负责领域同权,§信任分级本人声明)。

    取作者全部「已发布」文章的标签并集 → person_tags(source='self_article') 全量同步:
    - 文章发布/过审:标签激活进检索体系;
    - 文章撤下(转待审核/驳回/删除)或标签被编辑:不再被任何已发布文章覆盖的标签自动停用;
    - PCE 视图 ELSE 分支 = self_declared_scope/explicit_self_tag,与 source='self' 同权重(0.8);
    - 不写入 users.domains,不影响名片「负责领域」展示,只参与检索证据。

    与 Agent 体系同步为"尽力而为",失败仅记告警,不阻断业务写入。
    """
    try:
        with db.begin_nested():
            rows = db.execute(text(
                "SELECT DISTINCT jsonb_array_elements_text(c.tags) AS tag"
                " FROM public.contents c"
                " WHERE c.owner_id=:p AND c.status='published' AND c.is_deleted=FALSE"),
                {"p": person_id}).all()
            desired = {_normalize(r[0]) for r in rows if r[0] and r[0].strip()}
            existing = db.execute(
                text("SELECT pt.person_tag_id, rt.normalized_text FROM agent.person_tags pt"
                     " JOIN agent.raw_tags rt ON rt.tag_id = pt.tag_id"
                     " WHERE pt.person_id=:p AND pt.source='self_article' AND pt.is_active"),
                {"p": person_id}).all()
            for person_tag_id, normalized in existing:
                if normalized not in desired:
                    db.execute(text("UPDATE agent.person_tags SET is_active=FALSE"
                                    " WHERE person_tag_id=:i"), {"i": person_tag_id})
            for (tag,) in rows:
                if tag and tag.strip():
                    sync_tag_to_agent(db, person_id=person_id, tag=tag.strip(), active=True,
                                      source="self_article", created_by="content-api")
    except Exception:  # noqa: BLE001
        logger.warning("文章标签回流 Agent 体系失败(已忽略): person=%s", person_id, exc_info=True)


def sync_person_domain_tags(db: Session, *, person_id: str, domains: list[str]) -> None:
    """负责领域全量同步(source='self'):新集合外的自建标签停用,新标签建档并尝试概念映射。

    在 PUT /me/profile 更新 domains 时同事务调用,保证负责领域变更立即进入检索体系。

    与 Agent 体系同步为"尽力而为",失败仅记告警,不阻断业务写入。
    """
    desired = {_normalize(d) for d in (domains or []) if d and d.strip()}
    try:
        with db.begin_nested():
            rows = db.execute(
                text("SELECT pt.person_tag_id, rt.normalized_text FROM agent.person_tags pt"
                     " JOIN agent.raw_tags rt ON rt.tag_id = pt.tag_id"
                     " WHERE pt.person_id=:p AND pt.source='self' AND pt.is_active"),
                {"p": person_id}).all()
            for person_tag_id, normalized in rows:
                if normalized not in desired:
                    db.execute(text("UPDATE agent.person_tags SET is_active=FALSE"
                                    " WHERE person_tag_id=:i"), {"i": person_tag_id})
            for domain in (domains or []):
                if domain and domain.strip():
                    sync_tag_to_agent(db, person_id=person_id, tag=domain, active=True,
                                      source="self", created_by="profile-api")
    except Exception:  # noqa: BLE001
        logger.warning("负责领域同步到 Agent 体系失败(已忽略): person=%s", person_id, exc_info=True)
