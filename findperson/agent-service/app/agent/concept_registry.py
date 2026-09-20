"""Concept 注册表服务:Concept/Alias/TagConceptMap 的查询入口。

ConceptLinker(模块 13/17/18)、TagMatcher(模块 14)、PCE Builder(模块 13)
共用这一个 Registry(V1.2 §7.6:员工侧与查询侧共用同一套 Concept Registry)。

词典全量缓存(V1.2 §0.1 规模前提:概念库数百级可全量内存缓存;§14.4 缓存 concept dictionary)。
"""
from __future__ import annotations

from app.contracts.concept import Concept, ConceptStatus, RawTag, TagConceptMap
from app.core import db
from app.core.cache import CacheKeys, get_cache

# 概念词典缓存 TTL(秒);阶段 2 治理动作会主动失效
# 验收:后台/画像新标签自动建档 seed 概念后需尽快可检索,全量词典重载成本低(数百级),TTL 30s
CONCEPT_DICT_TTL = 30


class ConceptRegistry:
    """Concept 词典与映射的只读注册表(带全量缓存)。"""

    async def load_concepts(self, *, include_candidate: bool = False, force: bool = False) -> dict[str, Concept]:
        """加载概念词典(concept_id → Concept),带缓存。

        include_candidate=False 时只返回 seed/active 正式概念(检索侧使用);
        True 时包含 candidate(治理侧使用)。
        """
        cache = get_cache()
        key = CacheKeys.CONCEPT_DICT + (":all" if include_candidate else ":formal")
        if not force:
            cached = await cache.get(key)
            if cached is not None:
                return cached
        statuses = ("seed", "active", "candidate") if include_candidate else ("seed", "active")
        rows = await db.fetch(
            "SELECT concept_id, canonical_name, concept_type, description, scope_department_id,"
            "       status, embedding_model, suggested_name, source_tags, version"
            " FROM agent.concepts WHERE status = ANY($1)",
            statuses,
        )
        concepts = {
            r["concept_id"]: Concept(
                concept_id=r["concept_id"],
                canonical_name=r["canonical_name"],
                concept_type=r["concept_type"],
                description=r["description"],
                scope_department_id=r["scope_department_id"],
                status=ConceptStatus(r["status"]),
                embedding_model=r["embedding_model"],
                suggested_name=r["suggested_name"],
                source_tags=list(r["source_tags"] or []),
                version=r["version"],
            )
            for r in rows
        }
        await cache.set(key, concepts, ttl_seconds=CONCEPT_DICT_TTL)
        return concepts

    async def load_aliases(self) -> dict[str, str]:
        """规范化别名 → concept_id(第二级召回用)。"""
        rows = await db.fetch("SELECT alias, concept_id FROM agent.concept_aliases")
        return {r["alias"]: r["concept_id"] for r in rows}

    async def load_tag_mappings(self) -> dict[str, list[TagConceptMap]]:
        """tag_id → 已生效映射列表(第三级历史映射 + PCE Builder 用)。"""
        rows = await db.fetch(
            "SELECT map_id, tag_id, concept_id, mapping_type, confidence, generated_by,"
            "       review_status, reason"
            " FROM agent.tag_concept_map WHERE review_status IN ('auto_approved','approved')"
        )
        result: dict[str, list[TagConceptMap]] = {}
        for r in rows:
            result.setdefault(r["tag_id"], []).append(
                TagConceptMap(
                    map_id=r["map_id"], tag_id=r["tag_id"], concept_id=r["concept_id"],
                    mapping_type=r["mapping_type"], confidence=r["confidence"],
                    generated_by=r["generated_by"], review_status=r["review_status"],
                    reason=r["reason"],
                )
            )
        return result

    async def get_raw_tag_by_text(self, normalized_text: str) -> RawTag | None:
        """按规范化文本查 RawTag 实体。"""
        r = await db.fetchrow(
            "SELECT tag_id, text, normalized_text FROM agent.raw_tags WHERE normalized_text=$1",
            normalized_text,
        )
        if not r:
            return None
        return RawTag(tag_id=r["tag_id"], text=r["text"], normalized_text=r["normalized_text"])

    async def invalidate(self) -> None:
        """治理动作后失效缓存(模块 18 调用)。"""
        cache = get_cache()
        await cache.delete(CacheKeys.CONCEPT_DICT + ":all")
        await cache.delete(CacheKeys.CONCEPT_DICT + ":formal")
        await cache.delete(CacheKeys.TAG_CONCEPT_MAP)


_registry: ConceptRegistry | None = None


def get_concept_registry() -> ConceptRegistry:
    """Registry 单例。"""
    global _registry
    if _registry is None:
        _registry = ConceptRegistry()
    return _registry
