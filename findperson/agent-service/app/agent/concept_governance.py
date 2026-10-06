"""RawTag 注册与 Concept 治理(V1.2 §7.4 / §7.5)。

- RawTagConceptLinker(员工侧 §7.4):新 RawTag → 五级候选召回 →
  高置信自动映射 / 第六级 LLM 受约束消歧(LINK_EXISTING / CREATE_CANDIDATE /
  AMBIGUOUS / REJECT)→ tag_concept_map 或 concept_review_queue。
  LLM 不允许创造数据库不存在的正式 Concept ID。
- ConceptGovernance(§7.5):审核队列处理(批准/合并/改名/降级为别名/拒绝),
  审核后自动回填相关 RawTag 映射,概念变更版本化,Registry 缓存失效。
"""
from __future__ import annotations

import time

from app.agent.concept_linker import ConceptCandidateRecall
from app.agent.concept_registry import get_concept_registry
from app.contracts.concept import LinkDecision, MappingType, RawTag, ReviewAction
from app.contracts.errors import AgentError, ErrorCode
from app.core import db
from app.core.llm_client import LLMPort, get_llm

# 高置信自动映射阈值(§7.4:高置信自动链接);低置信进审核队列
AUTO_MAP_THRESHOLD = 0.97
# LLM 消歧 Prompt(业务 Prompt 归本模块)
DISAMBIGUATION_PROMPT = """你是企业概念治理助手。员工填写了一个"负责领域"标签,需要映射到企业标准概念。
严格输出 JSON(不要输出任何其他内容)。

员工填写: {raw_tag}

候选标准概念(只能选择以下候选,不允许创造新概念 ID):
{candidates}

决策规则(严格遵守):
- 仅当标签与某候选【确实指同一件事】(同义/同根,如 HiAgent平台→HiAgent)才选 LINK_EXISTING;
- 只要语义不同——即使相关、即使同领域(如 算力芯片设计≠智芯工程、dns地址管理≠信息管理)——必须选 CREATE_CANDIDATE 建新概念;
- 拿不准一律选 CREATE_CANDIDATE,严禁为了复用而硬挂。

你只能输出以下四种之一:
- {{"decision": "LINK_EXISTING", "concept_id": "<候选中的 concept_id>", "reason": "..."}}
- {{"decision": "CREATE_CANDIDATE", "suggested_name": "<建议标准名>", "reason": "..."}}
- {{"decision": "AMBIGUOUS", "reason": "..."}}
- {{"decision": "REJECT", "reason": "..."}}"""


def _new_id(prefix: str) -> str:
    return f"{prefix}-{int(time.time() * 1000):x}"


class RawTagConceptLinker:
    """员工侧:新 RawTag 注册与概念链接(§7.4 完整六级链)。"""

    def __init__(self, recall: ConceptCandidateRecall | None = None,
                 llm: LLMPort | None = None) -> None:
        self._recall = recall or ConceptCandidateRecall()
        self._llm = llm

    async def register_raw_tag(self, person_id: str, text: str, *,
                               source: str = "self", created_by: str = "") -> dict:
        """员工填写负责领域入口:原样保存 RawTag + 建立 person_tag + 概念链接。

        返回处理结果(链接方式/映射/是否进审核)。原始文本永远先落库(§7.1)。
        """
        normalized = RawTag.normalize(text)
        if not normalized:
            raise AgentError(ErrorCode.INPUT_ERROR, "负责领域不能为空")

        # 1) RawTag 原样保存(已存在则复用,§7.3:同一规范化文本为统一实体)
        tag = await get_concept_registry().get_raw_tag_by_text(normalized)
        if tag is None:
            tag_id = _new_id("tag")
            await db.execute(
                "INSERT INTO agent.raw_tags(tag_id, text, normalized_text) VALUES($1,$2,$3)",
                tag_id, text.strip(), normalized,
            )
            tag = RawTag(tag_id=tag_id, text=text.strip(), normalized_text=normalized)

        # 2) person_tags 关系(幂等)
        pt_id = f"pt-{person_id}-{tag.tag_id}"
        await db.execute(
            "INSERT INTO agent.person_tags(person_tag_id, person_id, tag_id, source, created_by)"
            " VALUES($1,$2,$3,$4,$5) ON CONFLICT (person_tag_id) DO NOTHING",
            pt_id, person_id, tag.tag_id, source, created_by or person_id,
        )

        # 3) 概念链接:已有生效映射直接复用(第三级);否则五级召回
        result = {"tag_id": tag.tag_id, "person_tag_id": pt_id, "action": ""}
        mappings = await get_concept_registry().load_tag_mappings()
        if tag.tag_id in mappings:
            m = mappings[tag.tag_id][0]
            result.update(action="reused", concept_id=m.concept_id, confidence=m.confidence)
            return result

        candidates = await self._recall.recall(text)
        result["candidates"] = [c.model_dump() for c in candidates]

        # 4) 高置信确定性命中 → 自动映射(§7.4)
        if candidates and candidates[0].candidate_score >= AUTO_MAP_THRESHOLD:
            top = candidates[0]
            await self._write_mapping(tag.tag_id, top.concept_id,
                                      confidence=top.candidate_score,
                                      generated_by="rule",
                                      reason=f"{top.candidate_source} 高置信自动映射")
            result.update(action="auto_mapped", concept_id=top.concept_id,
                          confidence=top.candidate_score)
            return result

        # 5) 第六级:LLM 受约束消歧(§7.4)
        decision = await self._llm_disambiguate(text, candidates)
        result["llm_decision"] = decision
        if decision["decision"] == LinkDecision.LINK_EXISTING.value:
            # LLM 只能选候选中的 concept_id(防线:不得输出候选集合之外的 ID)
            valid_ids = {c.concept_id for c in candidates}
            if decision["concept_id"] not in valid_ids:
                await self._enqueue("anomaly", {"tag_id": tag.tag_id, "text": text,
                                                "llm_output": decision,
                                                "reason": "LLM 输出候选集合外的 concept_id"})
                result.update(action="review_enqueued", reason="llm_output_out_of_candidates")
                return result
            await self._write_mapping(tag.tag_id, decision["concept_id"],
                                      confidence=0.9, generated_by="llm",
                                      review_status="pending",
                                      reason=decision.get("reason", "LLM 受约束链接"))
            await self._enqueue("low_confidence_mapping",
                                {"tag_id": tag.tag_id, "concept_id": decision["concept_id"],
                                 "reason": "LLM 链接待人工确认"})
            result.update(action="linked_pending_review", concept_id=decision["concept_id"])
        elif decision["decision"] == LinkDecision.CREATE_CANDIDATE.value:
            candidate_id = _new_id("candidate")
            await db.execute(
                "INSERT INTO agent.concepts(concept_id, canonical_name, concept_type, status,"
                " suggested_name, source_tags, description)"
                " VALUES($1,'',  'domain','candidate',$2,$3,$4)",
                candidate_id, decision.get("suggested_name") or text.strip(),
                [text.strip()], "LLM 建议的候选概念,待人工审核(§7.5)",
            )
            await self._enqueue("candidate_concept",
                                {"candidate_concept_id": candidate_id,
                                 "suggested_name": decision.get("suggested_name") or text.strip(),
                                 "source_tags": [text.strip()], "tag_id": tag.tag_id})
            await get_concept_registry().invalidate()
            result.update(action="candidate_created", candidate_concept_id=candidate_id)
        else:  # AMBIGUOUS / REJECT
            await self._enqueue("ambiguous_mapping",
                                {"tag_id": tag.tag_id, "text": text,
                                 "candidates": [c.model_dump() for c in candidates],
                                 "llm_decision": decision})
            result.update(action="review_enqueued", reason=decision["decision"])
        return result

    async def link_tag(self, text: str) -> dict:
        """标签→概念链接(不含人员关系,供 backend 写侧/事件消费者调用)。

        §7.4 完整链路:五级召回 → 高置信自动映射 → 第六级 LLM 受约束消歧。
        演示环境策略(审核队列仅作备查,结果立即可检索):
        - LINK_EXISTING(候选内)→ auto_approved 挂接已有概念
        - CREATE_CANDIDATE → 按 LLM 建议名建 seed 概念并挂接
        - AMBIGUOUS/REJECT → 按原文建 seed 兜底(保持可检索,记入队列)
        """
        normalized = RawTag.normalize(text)
        if not normalized:
            raise AgentError(ErrorCode.INPUT_ERROR, "标签不能为空")

        # RawTag 原样保存(已存在则复用,§7.1/§7.3)
        tag = await get_concept_registry().get_raw_tag_by_text(normalized)
        if tag is None:
            tag_id = _new_id("tag")
            await db.execute(
                "INSERT INTO agent.raw_tags(tag_id, text, normalized_text) VALUES($1,$2,$3)",
                tag_id, text.strip(), normalized,
            )
            tag = RawTag(tag_id=tag_id, text=text.strip(), normalized_text=normalized)

        # 已有生效映射直接复用(第三级历史映射)
        mappings = await get_concept_registry().load_tag_mappings()
        if tag.tag_id in mappings:
            return {"action": "reused", "concept_id": mappings[tag.tag_id][0].concept_id,
                    "tag_id": tag.tag_id}

        candidates = await self._recall.recall(text)

        # 高置信确定性命中 → 自动映射(§7.4)
        if candidates and candidates[0].candidate_score >= AUTO_MAP_THRESHOLD:
            top = candidates[0]
            await self._write_mapping(tag.tag_id, top.concept_id,
                                      confidence=top.candidate_score,
                                      generated_by="rule",
                                      reason=f"{top.candidate_source} 高置信自动映射")
            return {"action": "auto_mapped", "concept_id": top.concept_id, "tag_id": tag.tag_id}

        # 第六级:LLM 受约束消歧
        decision = await self._llm_disambiguate(text, candidates)
        valid_ids = {c.concept_id for c in candidates}
        if decision["decision"] == LinkDecision.LINK_EXISTING.value \
                and decision.get("concept_id") in valid_ids:
            await self._write_mapping(
                tag.tag_id, decision["concept_id"], confidence=0.9, generated_by="llm",
                review_status="auto_approved",
                reason=decision.get("reason", "") or "LLM 受约束链接(演示环境自动生效)")
            await self._enqueue("llm_link_audit",
                                {"tag_id": tag.tag_id, "text": text,
                                 "concept_id": decision["concept_id"],
                                 "reason": decision.get("reason", "")})
            return {"action": "linked", "concept_id": decision["concept_id"],
                    "tag_id": tag.tag_id}
        if decision["decision"] == LinkDecision.CREATE_CANDIDATE.value:
            name = (decision.get("suggested_name") or text.strip())[:64]
            cid = _new_id("concept")
            await db.execute(
                "INSERT INTO agent.concepts(concept_id, canonical_name, concept_type, status,"
                " source_tags, description) VALUES($1,$2,'domain','seed',$3,$4)",
                cid, name, [text.strip()],
                "LLM 消歧建议建档(演示环境自动生效,审核队列备查)")
            await self._write_mapping(tag.tag_id, cid, confidence=0.9, generated_by="llm",
                                      review_status="auto_approved", reason="LLM 建议新概念建档")
            await self._enqueue("llm_candidate_audit",
                                {"tag_id": tag.tag_id, "text": text,
                                 "concept_id": cid, "suggested_name": name})
            return {"action": "created", "concept_id": cid, "tag_id": tag.tag_id}
        # AMBIGUOUS/REJECT/非法输出:按原文建 seed 兜底(保持可检索),记审核队列
        cid = _new_id("concept")
        await db.execute(
            "INSERT INTO agent.concepts(concept_id, canonical_name, concept_type, status,"
            " source_tags, description) VALUES($1,$2,'domain','seed',$3,$4)",
            cid, text.strip(), [text.strip()],
            "消歧不明,按原文兜底建档(审核队列备查)")
        await self._write_mapping(tag.tag_id, cid, confidence=0.5, generated_by="rule",
                                  review_status="auto_approved", reason="消歧不明兜底建档")
        await self._enqueue("ambiguous_mapping",
                            {"tag_id": tag.tag_id, "text": text,
                             "candidates": [c.model_dump() for c in candidates],
                             "llm_decision": decision})
        return {"action": "fallback_created", "concept_id": cid, "tag_id": tag.tag_id}

    async def _llm_disambiguate(self, text: str, candidates) -> dict:
        """LLM 受约束消歧:输入候选,输出四选一(§7.4)。"""
        llm = self._llm or get_llm()
        cand_text = "\n".join(
            f"{i+1}. {c.concept_id}({c.canonical_name})" for i, c in enumerate(candidates)
        ) or "(无候选)"
        data, _ = await llm.structured_chat(
            [{"role": "user", "content": DISAMBIGUATION_PROMPT.format(
                raw_tag=text, candidates=cand_text)}],
            required_keys=["decision", "reason"],
        )
        decision = str(data.get("decision", "")).upper()
        if decision not in {d.value for d in LinkDecision}:
            return {"decision": LinkDecision.AMBIGUOUS.value,
                    "reason": f"LLM 输出非法 decision: {decision}"}
        return {"decision": decision,
                "concept_id": data.get("concept_id"),
                "suggested_name": data.get("suggested_name"),
                "reason": str(data.get("reason", ""))}

    async def _write_mapping(self, tag_id: str, concept_id: str, *,
                             confidence: float, generated_by: str,
                             review_status: str = "auto_approved",
                             reason: str = "") -> None:
        await db.execute(
            "INSERT INTO agent.tag_concept_map(map_id, tag_id, concept_id, mapping_type,"
            " confidence, generated_by, review_status, reason)"
            " VALUES($1,$2,$3,$4,$5,$6,$7,$8) ON CONFLICT (tag_id, concept_id) DO NOTHING",
            _new_id("map"), tag_id, concept_id,
            MappingType.NEAR_ALIAS.value if generated_by == "llm" else MappingType.EXACT_ALIAS.value,
            confidence, generated_by, review_status, reason,
        )
        await get_concept_registry().invalidate()

    async def _enqueue(self, item_type: str, payload: dict) -> None:
        await db.execute(
            "INSERT INTO agent.concept_review_queue(review_id, item_type, payload)"
            " VALUES($1,$2,$3)",
            _new_id("review"), item_type,
            __import__("json").dumps(payload, ensure_ascii=False, default=str),
        )


class ConceptGovernance:
    """Candidate Concept 与映射的人工治理(§7.5)。"""

    async def review(self, review_id: str, action: ReviewAction, *,
                     operator: str, **kwargs) -> dict:
        """处理审核队列条目。审核后自动回填相关 RawTag 映射(§7.5 验收)。"""
        row = await db.fetchrow(
            "SELECT review_id, item_type, payload, status FROM agent.concept_review_queue"
            " WHERE review_id=$1", review_id,
        )
        if not row:
            raise AgentError(ErrorCode.INPUT_ERROR, f"审核条目不存在: {review_id}")
        if row["status"] != "pending":
            raise AgentError(ErrorCode.INPUT_ERROR, f"审核条目已处理: {review_id}")
        import json
        payload = json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"]
        resolution: dict = {"action": action.value, "operator": operator}

        if row["item_type"] == "candidate_concept":
            resolution.update(await self._review_candidate(payload, action, operator, **kwargs))
        elif row["item_type"] == "low_confidence_mapping":
            if action == ReviewAction.APPROVE:
                await db.execute(
                    "UPDATE agent.tag_concept_map SET review_status='approved'"
                    " WHERE tag_id=$1 AND concept_id=$2",
                    payload["tag_id"], payload["concept_id"],
                )
                resolution["approved_mapping"] = payload
            else:
                await db.execute(
                    "UPDATE agent.tag_concept_map SET review_status='rejected'"
                    " WHERE tag_id=$1 AND concept_id=$2",
                    payload["tag_id"], payload["concept_id"],
                )
                resolution["rejected_mapping"] = payload
        else:
            resolution["note"] = "该类型仅记录,无需动作"

        await db.execute(
            "UPDATE agent.concept_review_queue SET status='resolved', resolution=$1,"
            " resolved_at=now() WHERE review_id=$2",
            json.dumps(resolution, ensure_ascii=False, default=str), review_id,
        )
        await get_concept_registry().invalidate()
        return resolution

    async def _review_candidate(self, payload: dict, action: ReviewAction,
                                operator: str, **kwargs) -> dict:
        """Candidate Concept 的五种审核动作(§7.5)。"""
        cid = payload["candidate_concept_id"]
        tag_id = payload.get("tag_id")
        if action == ReviewAction.APPROVE:
            name = payload["suggested_name"]
            await db.execute(
                "UPDATE agent.concepts SET status='active', canonical_name=$1, version=version+1"
                " WHERE concept_id=$2", name, cid)
            formal_id = cid
        elif action == ReviewAction.RENAME_APPROVE:
            name = kwargs["new_name"]
            await db.execute(
                "UPDATE agent.concepts SET status='active', canonical_name=$1, version=version+1"
                " WHERE concept_id=$2", name, cid)
            formal_id = cid
        elif action == ReviewAction.MERGE:
            target = kwargs["target_concept_id"]
            await db.execute(
                "UPDATE agent.concepts SET status='deprecated', valid_to=now(), version=version+1"
                " WHERE concept_id=$1", cid)
            formal_id = target
        elif action == ReviewAction.AS_ALIAS:
            target = kwargs["target_concept_id"]
            await db.execute(
                "UPDATE agent.concepts SET status='deprecated', valid_to=now(), version=version+1"
                " WHERE concept_id=$1", cid)
            alias = RawTag.normalize(payload["suggested_name"])
            await db.execute(
                "INSERT INTO agent.concept_aliases(alias_id, concept_id, alias)"
                " VALUES($1,$2,$3) ON CONFLICT DO NOTHING",
                _new_id("alias"), target, alias)
            formal_id = target
        else:  # REJECT
            await db.execute(
                "UPDATE agent.concepts SET status='deprecated', valid_to=now(), version=version+1"
                " WHERE concept_id=$1", cid)
            return {"rejected_candidate": cid}

        # 回填:来源 RawTag 自动映射到转正后的正式概念(§7.5 验收)
        backfilled = []
        if tag_id:
            await db.execute(
                "INSERT INTO agent.tag_concept_map(map_id, tag_id, concept_id, mapping_type,"
                " confidence, generated_by, review_status, reason)"
                " VALUES($1,$2,$3,'near_alias',0.95,'human','auto_approved',$4)"
                " ON CONFLICT (tag_id, concept_id) DO NOTHING",
                _new_id("map"), tag_id, formal_id,
                f"审核转正后回填(operator={operator})",
            )
            backfilled.append({"tag_id": tag_id, "concept_id": formal_id})
        return {"formal_concept_id": formal_id, "backfilled_mappings": backfilled}
