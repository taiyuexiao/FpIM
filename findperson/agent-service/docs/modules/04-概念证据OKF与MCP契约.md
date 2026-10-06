# 模块 04:概念/证据/OKF/MCP 契约

## 背景

对应 V1.2 阶段 0 冻结清单中的 RawTag Schema、PersonTag Schema、Concept Schema、TagConceptMap Schema、Concept Review Schema、OKF Schema、Document Metadata、MCP Schema,以及 §12.1 PersonEvidence 统一证据模型。这些契约横跨两条数据建设链(人员语义链 §7、企业知识链 §10),是阶段 1~6 所有模块的共用语言。文档反复强调的边界(短标签不进 RAG、Candidate≠正式 Concept、自填≠正式责任、证据不能只剩一个浮点数、MCP 强制 user_context)都要在契约层面就锁死。

## 任务

- 输出:concept.py / evidence.py / okf.py / mcp.py 四份契约
- 验收:字段与文档逐条对齐;关键边界有测试断言守护

## 实现方式

- `app/contracts/concept.py`(§7)
  - 枚举:ConceptType(12 类)、ConceptStatus(seed/candidate/active/deprecated,Candidate 与正式隔离)、MappingType(7 种,禁止一律 alias)、LinkDecision(LLM 只能四选一)、RelationType(9 种关系白名单,含 routes_to)、ReviewAction(5 种审核动作)、TagSource(自填/评价/管理员)
  - 模型:RawTag(text 原文 + normalized_text 判重,`normalize()` 静态方法)、PersonTag、Concept(含 Candidate 专有字段 suggested_name/source_tags)、ConceptAlias、TagConceptMap(必带 mapping_type/confidence/generated_by/review_status/reason)、ConceptRelation、ConceptReviewItem、PersonConceptEvidence(relation_type 默认 self_declared_scope)、ConceptCandidate(§7.3 统一候选输出:concept_id/candidate_source/candidate_score/matched_text)
- `app/contracts/evidence.py`(§12.1):EvidenceType 6 类;PersonEvidence 全字段(含 relation_path 写 Trace、detail 保留原始证据)
- `app/contracts/okf.py`(§10.1/§10.7):OkfType 8 类目录、OkfStatus、Visibility;OkfMetadata 13 必备字段 + `compute_hash()`(sha256,发布校验与增量索引判断用);OkfDocument = metadata + Markdown body + extra;RagChunk 输出契约
- `app/contracts/mcp.py`(§12.1):McpTool 8 个只读工具枚举;McpRequest 强制 user_context + trace_id;RagHit(§10.9 产出)、ResponsibilityRecord(§9.4 输出:受理/责任部门/责任人/时限/转办/升级/来源/版本);McpResponse 统一响应(含 degraded)
- 测试 `tests/test_contracts_domain.py`:11 个用例,把文档红线变成断言(原文不被覆盖、Candidate 隔离、relation_type≠responsible_for、关系白名单、审核动作齐全、证据语义分层、13 字段+hash 稳定、MCP 强制 user_context、8 工具枚举),全部通过(累计 19 passed)

## 遇到的问题报错及解决方法

无。一次通过。

## 上下游接口及依赖

- 上游:模块 03 的 `UserContext`(McpRequest 引用)
- 下游:
  - 模块 05 的 DDL 表结构按这些模型建表(agent.raw_tags/person_tags/concepts/...、rag.rag_documents/rag_chunks)
  - ConceptLinker(模块 13/17/18)消费 ConceptCandidate/TagConceptMap/LinkDecision;治理(模块 18)消费 ConceptReviewItem/ReviewAction
  - PersonConceptEvidence Builder(模块 13)、TagMatcher(模块 14)、CandidateMerger/Ranker(模块 15)消费 evidence.py
  - OKF Publisher(模块 19-21)消费 okf.py;RAG(模块 22-24)消费 RagChunk;MCP(模块 25)消费 mcp.py 全部
- 对外接口:四个文件的全部公开模型与枚举
