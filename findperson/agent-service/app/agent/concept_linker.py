"""查询侧 ConceptLinker(V1.2 §7.6 / §7.3)。

与员工侧 RawTag ConceptLinker 共用同一套 Concept Registry 和 Candidate Recall 能力,
输入是 Query Structure(QueryStructurer 的 UnderstandingState)。

本模块实现六级映射链的前三级(确定性召回,§7.3):
  1. Canonical Name Exact
  2. Alias Exact
  3. RawTag Historical Mapping(历史上相同 RawTag 已审核映射,直接复用)
第四级 pg_trgm、第五级 Concept Vector 在模块 17,第六级 LLM 消歧在模块 18。

V1 阶段 1 的确认规则:确定性命中即 resolved;命中多个不同 Concept 则 ambiguous,
留给后续级别/人工(阶段 1 不调 LLM)。
"""
from __future__ import annotations

from app.agent.concept_registry import ConceptRegistry, get_concept_registry
from app.agent.orchestrator import AgentNode, ServiceRegistry
from app.contracts.agent_state import AgentState, ConceptState, Intent, StateUpdate
from app.contracts.concept import ConceptCandidate, RawTag
from app.core import db
from app.core.cache import CacheKeys, get_cache

# 确认阈值与可自动确认的确定性级别(§7.3:trgm/vector 只出候选,不自动映射)
RESOLVE_THRESHOLD = 0.9
# 前三级 + prefix/subseq 为确定性级别可自动 resolved;
# prefix = 问句短词对长概念名的前缀/包含匹配;subseq = 字符子序列匹配(缺字说法,唯一命中才生效)
AUTO_RESOLVE_SOURCES = ("exact", "alias", "historical", "prefix", "subseq", "contains")
# 模糊归一(错别字/口语说法):无确定性命中时,向量/trgm 头名 ≥FUZZY_AUTO_MIN 且与
# 次名(不同概念)差距 ≥FUZZY_AUTO_GAP 才允许自动归一——§7.3 候选原则的受控放宽,
# 门限保守防错配(实测:首问必达→首问必答平台 0.547/差距 0.11;asdfgh <0.5 不归一)
FUZZY_AUTO_MIN = 0.5
FUZZY_AUTO_GAP = 0.05
FUZZY_AUTO_SOURCES = ("vector", "pg_trgm")


# 第 2.5 级前缀/包含匹配的词项停用表:通用动作/职能词不做前缀匹配
# (「申请」前缀中「申请受理」这类职能概念会错拉一票人;食堂/出入境等真实领域词不受影响)
_PREFIX_STOP_TERMS = {
    "申请", "办理", "管理", "负责", "维护", "处理", "咨询", "值班", "运维",
    "受理", "负责人", "备岗", "故障", "申请受理", "资源负责人", "运维与故障", "备岗与咨询",
}

# 泛词停用表(B 类治理):词项本身是笼统词时,不做前缀/包含这类「猜测级」匹配——
# 'ai infra' 里的 'ai' 会把 AI产品运营/AI基础研发/AI运营项目 整族猜出来(实测),
# 泛词只允许 exact/alias/historical(精确级),猜测交给 trgm/向量候选
_GENERIC_TERM_STOP = {
    "ai", "bi", "it", "data", "数据", "管理", "平台", "系统", "信息",
    "应用", "开发", "测试", "工作", "业务", "项目", "模型", "智能",
}


def _is_subsequence(needle: str, haystack: str) -> bool:
    """needle 的字符按顺序出现在 haystack 中(允许中间插字),如 会议申请⊂会议室申请。"""
    it = iter(haystack)
    return all(ch in it for ch in needle)


class ConceptCandidateRecall:
    """候选概念召回(五级确定性召回)。

    前三级(exact/alias/historical)为可自动确认的确定性级别;
    第四级 pg_trgm、第五级 Concept Vector 只产出候选(§7.3:向量用于候选召回,
    不直接形成最终映射),是否链接由第六级 LLM 消歧(模块 18)或治理决定。
    """

    def __init__(self, registry: ConceptRegistry | None = None) -> None:
        self._registry = registry or get_concept_registry()

    async def recall(self, text: str, *, max_level: int = 5) -> list[ConceptCandidate]:
        """对单个表达做候选召回,按分数降序。

        max_level: 最多走到第几级(阶段 1 链路传 3,阶段 2 起传 5)。
        命中前三级即返回(确定性短路);否则继续第四/五级补充候选。
        """
        normalized = RawTag.normalize(text)
        concepts = await self._registry.load_concepts()
        candidates: list[ConceptCandidate] = []

        # 第一级:Canonical Name Exact
        for c in concepts.values():
            if c.canonical_name.lower() == normalized:
                candidates.append(ConceptCandidate(
                    concept_id=c.concept_id, candidate_source="exact",
                    candidate_score=1.0, matched_text=text,
                    canonical_name=c.canonical_name,
                ))

        # 第二级:Alias Exact
        if not candidates:
            aliases = await self._registry.load_aliases()
            cid = aliases.get(normalized)
            if cid and cid in concepts:
                candidates.append(ConceptCandidate(
                    concept_id=cid, candidate_source="alias",
                    candidate_score=0.98, matched_text=text,
                    canonical_name=concepts[cid].canonical_name,
                ))

        # 第三级:RawTag Historical Mapping(已审核的相同 RawTag 映射,直接复用)
        # 提前于前缀/包含/子序列:有审核过的精确映射就不用启发式猜测——
        # 否则 'ai infra' 会被前缀规则截胡到泛概念 'AI'(实测),精确映射反被短路
        if not candidates:
            tag = await self._registry.get_raw_tag_by_text(normalized)
            if tag:
                mappings = await self._registry.load_tag_mappings()
                for m in mappings.get(tag.tag_id, []):
                    if m.concept_id in concepts:
                        candidates.append(ConceptCandidate(
                            concept_id=m.concept_id, candidate_source="historical",
                            # 保留 4 位小数:float4 的 0.9 实为 0.8999999761581421,
                            # 不截尾会以 1e-8 之差跌破 RESOLVE_THRESHOLD=0.9 导致归一失败(实测)
                            candidate_score=min(0.97, round(m.confidence, 4)), matched_text=text,
                            canonical_name=concepts[m.concept_id].canonical_name,
                        ))

        # 第 2.5 级:前缀/包含匹配(验收:短问句对长概念名,如 食堂→食堂评价、出入境→出入境管理)
        # 多概念歧义时不自动 resolved(由 resolve 侧 distinct>1 拦下),只出候选;
        # 通用动作/职能词(申请/办理/运维…)不参与前缀匹配,防错拉职能类概念;
        # 泛名保护:<3 字符的短概念名(如 AI)不允许「长词包含短名」命中,防泛概念截胡多字词项
        if not candidates and normalized not in _PREFIX_STOP_TERMS \
                and normalized not in _GENERIC_TERM_STOP:
            for c in concepts.values():
                name = c.canonical_name.lower()
                if name.startswith(normalized):
                    hit = True
                elif len(normalized) > len(name) and len(name) >= 3 and name in normalized:
                    hit = True
                else:
                    hit = False
                if hit:
                    candidates.append(ConceptCandidate(
                        concept_id=c.concept_id, candidate_source="prefix",
                        candidate_score=0.96, matched_text=text,
                        canonical_name=c.canonical_name,
                    ))
            if not candidates:
                aliases = await self._registry.load_aliases()
                for alias, cid in aliases.items():
                    if cid not in concepts:
                        continue
                    if alias.startswith(normalized) or (len(normalized) > len(alias) and alias in normalized):
                        candidates.append(ConceptCandidate(
                            concept_id=cid, candidate_source="prefix",
                            candidate_score=0.96, matched_text=text,
                            canonical_name=concepts[cid].canonical_name,
                        ))

        # 第 2.55 级:包含匹配(验收:词根/后缀型口语词,如 报销→财务报销管理)
        # 概念名包含查询词即可;词长≥2;唯一命中→0.95 进自动确认区;
        # 多命中→0.85 仅候选(不进自动确认,防 数据/管理 类泛词错拉);通用词与前缀同表停用
        if not candidates and len(normalized) >= 2 and normalized not in _PREFIX_STOP_TERMS \
                and normalized not in _GENERIC_TERM_STOP:
            hits = [c for c in concepts.values()
                    if len(c.canonical_name) > len(normalized)
                    and normalized in c.canonical_name.lower()]
            unique = len(hits) == 1
            for c in hits:
                candidates.append(ConceptCandidate(
                    concept_id=c.concept_id, candidate_source="contains",
                    candidate_score=0.95 if unique else 0.85, matched_text=text,
                    canonical_name=c.canonical_name,
                ))

        # 第 2.6 级:子序列匹配(验收:会议申请→会议室申请;用户漏字/插字说法)
        # 仅短词对长名(防长问句误配);词长≥3;多概念歧义时不自动 resolved,只出候选
        if not candidates and len(normalized) >= 3 and normalized not in _PREFIX_STOP_TERMS:
            for c in concepts.values():
                name = c.canonical_name.lower()
                if len(normalized) < len(name) and _is_subsequence(normalized, name):
                    candidates.append(ConceptCandidate(
                        concept_id=c.concept_id, candidate_source="subseq",
                        candidate_score=0.94, matched_text=text,
                        canonical_name=c.canonical_name,
                    ))
            if not candidates:
                aliases = await self._registry.load_aliases()
                for alias, cid in aliases.items():
                    if cid not in concepts:
                        continue
                    if len(normalized) < len(alias) and _is_subsequence(normalized, alias):
                        candidates.append(ConceptCandidate(
                            concept_id=cid, candidate_source="subseq",
                            candidate_score=0.94, matched_text=text,
                            canonical_name=concepts[cid].canonical_name,
                        ))

        if candidates or max_level < 4:
            candidates.sort(key=lambda c: c.candidate_score, reverse=True)
            return candidates

        # 第四级:pg_trgm Fuzzy Recall(§7.3)——分数上限 0.89,不进入自动确认区
        rows = await db.fetch(
            "SELECT concept_id, canonical_name,"
            "       greatest(similarity(canonical_name, $1), 0) AS sim"
            " FROM agent.concepts"
            " WHERE status IN ('seed','active') AND canonical_name % $1"
            " ORDER BY sim DESC LIMIT 5",
            text,
        )
        for r in rows:
            candidates.append(ConceptCandidate(
                concept_id=r["concept_id"], candidate_source="pg_trgm",
                candidate_score=round(min(0.89, float(r["sim"]) * 0.95), 4),
                matched_text=text, canonical_name=r["canonical_name"],
            ))

        # 第五级:Concept Vector Recall(§7.3)——只召回候选,不直接形成映射
        if max_level >= 5:
            vector_hits = await self._vector_recall(text, concepts)
            candidates.extend(vector_hits)

        candidates.sort(key=lambda c: c.candidate_score, reverse=True)
        return candidates

    async def _vector_recall(self, text: str, concepts: dict,
                             top_n: int = 5, min_score: float = 0.25) -> list[ConceptCandidate]:
        """用 Concept 独立向量空间(1024 维)做候选召回。分数上限 0.85。"""
        from app.core.embedding_client import cosine_similarity, get_concept_embedding
        emb = get_concept_embedding()
        query_vec = await emb.embed_query(text)
        # 概念向量全量结果短缓存:避免每查询全表拉取+逐行解析(验收:响应慢)
        from app.core.cache import get_cache
        cache = get_cache()
        rows = await cache.get("concept:embeddings")
        if rows is None:
            rows = await db.fetch(
                "SELECT concept_id, embedding FROM agent.concepts"
                " WHERE status IN ('seed','active') AND embedding IS NOT NULL",
            )
            await cache.set("concept:embeddings", rows, ttl_seconds=30)
        hits: list[ConceptCandidate] = []
        for r in rows:
            cid = r["concept_id"]
            if cid not in concepts:
                continue
            vec = r["embedding"]
            if isinstance(vec, str):  # asyncpg 默认把 vector 读成字符串字面量
                vec = [float(x) for x in vec.strip("[]").split(",")]
            score = cosine_similarity(query_vec, list(vec))
            if score >= min_score:
                hits.append(ConceptCandidate(
                    concept_id=cid, candidate_source="vector",
                    candidate_score=round(min(0.85, score * 0.9), 4),
                    matched_text=text, canonical_name=concepts[cid].canonical_name,
                ))
        hits.sort(key=lambda c: c.candidate_score, reverse=True)
        return hits[:top_n]


class QueryConceptLinker:
    """查询侧概念链接器:把 UnderstandingState 的各类表达对齐到 Canonical Concept。"""

    def __init__(self, recall: ConceptCandidateRecall | None = None) -> None:
        self._recall = recall or ConceptCandidateRecall()

    async def link(self, terms: list[str], *, query: str = "") -> ConceptState:
        """对一组表达做概念对齐,输出 ConceptState(§7.6 输出结构)。"""
        state = ConceptState()
        seen: set[str] = set()
        for term in terms:
            term = term.strip()
            if not term or RawTag.normalize(term) in seen:
                continue
            seen.add(RawTag.normalize(term))

            # query→concept 短缓存(§14.4)
            cache_key = CacheKeys.QUERY_CONCEPT.format(query=f"{term}")
            cached = await get_cache().get(cache_key)
            if cached is not None:
                candidates = cached
            else:
                candidates = await self._recall.recall(term)
                await get_cache().set(cache_key, candidates, ttl_seconds=30)  # 新标签建档后 30s 内可检索

            for c in candidates:
                state.candidate_concepts.append(c.model_dump())
            state.concept_link_trace.append({
                "term": term,
                "candidates": [c.model_dump() for c in candidates],
                "levels_tried": ["exact", "alias", "prefix", "subseq", "historical"],
            })

            # 确认规则:只有确定性级别(exact/alias/historical)可自动 resolved;
            # pg_trgm/vector 候选保留待第六级消歧(模块 18);多概念歧义标记
            top = [c for c in candidates if c.candidate_score >= RESOLVE_THRESHOLD
                   and c.candidate_source in AUTO_RESOLVE_SOURCES]
            distinct = {c.concept_id for c in top}
            if len(distinct) == 1:
                c = top[0]
                if c.concept_id not in {r["concept_id"] for r in state.resolved_concepts}:
                    state.resolved_concepts.append({
                        "concept_id": c.concept_id,
                        "canonical_name": c.canonical_name,
                        "matched_text": term,
                        "source": c.candidate_source,
                        "confidence": c.candidate_score,
                    })
            elif len(distinct) > 1:
                # 多概念歧义改为并列归一(至多 3 个):如 MLOps→MLOPS产品设计+MLOPS开发建设,
                # 候选人是同领域兄弟姐妹时给并列名片,比纯追问更有用;真正无法理解的
                # 输入由置信门/意图层澄清,不靠 ambiguous 一刀切
                for c in top:
                    if len({r["concept_id"] for r in state.resolved_concepts}) >= 3:
                        break
                    if c.concept_id not in {r["concept_id"] for r in state.resolved_concepts}:
                        state.resolved_concepts.append({
                            "concept_id": c.concept_id,
                            "canonical_name": c.canonical_name,
                            "matched_text": term,
                            "source": c.candidate_source,
                            "confidence": c.candidate_score,
                        })
            elif not distinct and len({c.concept_id for c in candidates
                                       if c.candidate_source == "contains"}) > 1:
                # contains 多命中(0.85 档)并列归一:泛词已被 _GENERIC_TERM_STOP 拦截,
                # 剩余多命中多为同族领域(如「集群」命中三个集群类概念),
                # 并列后让多证据持有者(标签+文章)自然浮顶(实测史朋飞案例)
                for c in [c for c in candidates if c.candidate_source == "contains"][:3]:
                    if c.concept_id not in {r["concept_id"] for r in state.resolved_concepts}:
                        state.resolved_concepts.append({
                            "concept_id": c.concept_id,
                            "canonical_name": c.canonical_name,
                            "matched_text": term,
                            "source": c.candidate_source,
                            "confidence": c.candidate_score,
                        })
            elif not distinct:
                # 模糊归一:无确定性命中时,高置信模糊头名且差距足够才自动归一。
                # 必须同时满足「语义近」(向量/trgm 分数)与「字符重叠」(pg_trgm 有候选):
                # 纯语义近邻会把 HarnessEval 错配到 AI基础研发(实测),
                # 而错别字(首问必达→首问必答平台)兼有字符重叠——双保险防错配
                fuzzy = [c for c in candidates
                         if c.candidate_source in FUZZY_AUTO_SOURCES
                         and c.candidate_score >= FUZZY_AUTO_MIN]
                if fuzzy:
                    best = fuzzy[0]
                    runner_up = next((c for c in fuzzy[1:] if c.concept_id != best.concept_id), None)
                    char_overlap = any(c.concept_id == best.concept_id
                                       and c.candidate_source == "pg_trgm" for c in candidates)
                    if (char_overlap and (runner_up is None
                            or best.candidate_score - runner_up.candidate_score >= FUZZY_AUTO_GAP)):
                        if best.concept_id not in {r["concept_id"] for r in state.resolved_concepts}:
                            state.resolved_concepts.append({
                                "concept_id": best.concept_id,
                                "canonical_name": best.canonical_name,
                                "matched_text": term,
                                "source": f"{best.candidate_source}_fuzzy",
                                "confidence": best.candidate_score,
                            })
        return state


class ConceptLinkerNode(AgentNode):
    """概念链接节点。仅 find_person 执行;结果落 ConceptState 并写 query_concept_logs。"""

    name = "ConceptLinkerNode"
    timeout_ms = 10000
    on_error = "degrade"

    async def execute(self, state: AgentState, services: ServiceRegistry) -> StateUpdate:
        if state.intent.intent != Intent.FIND_PERSON:
            return StateUpdate()
        u = state.understanding
        # 链接对象:显式词项优先,然后系统/对象/职责线索/症状(§7.6)
        terms = list(u.explicit_terms) + [
            t for t in (u.mentioned_systems + u.objects + u.duty_clues + u.symptoms)
            if t not in u.explicit_terms
        ]
        linker = services.get("concept_linker") if "concept_linker" in services.services else QueryConceptLinker()
        query = state.request.normalized_query or state.request.original_query
        concept_state = await linker.link(terms, query=query)

        # 查询概念日志(§7.6 评测与 trace 串联);失败不阻断主链
        try:
            await db.execute(
                "INSERT INTO agent.query_concept_logs(trace_id, query, link_trace, resolved_concepts)"
                " VALUES($1,$2,$3,$4)",
                state.trace.trace_id, query,
                _json([t for t in concept_state.concept_link_trace]),
                _json(concept_state.resolved_concepts),
            )
        except Exception:  # noqa: BLE001
            pass
        return StateUpdate(concept=concept_state)


def _json(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False, default=str)
