# 模块 14:TagMatcher + Directory Search + StructuredRetrievalNode

## 背景

对应 V1.2 §9(路径 A:结构化人员与责任检索):§9.1 Directory Search(contact_lookup 专用)、§9.3 TagMatcher(两级匹配:细分层精确 + 概念层泛化)、§9.4 Formal Responsibility Retriever(正常经 MCP,现阶段按 §18 用显式标记的 Mock/Degraded Adapter)。以及 §8.1 Query Strategy Router 的核心约束:「不同 query_type 不执行无意义工具调用,contact_lookup 中 RAG 调用次数必须为 0」。

## 任务

- 输入:ConceptState.resolved_concepts、UnderstandingState(人名/部门)、query_type
- 输出:retrieval.structured_candidates(PersonEvidence[])、responsibility_evidence(ResponsibilityRecord[])
- 验收:leaf_exact 保留原始 RawTag;泛化降权带 relation_path;contact_lookup 零 RAG;Mock 责任显式 degraded

## 实现方式

- `app/retrieval/directory_search.py` **DirectorySearch**:姓名/部门精确查 public.people,按 completeness 排序,返回 DIRECTORY_MATCH 证据,detail 携带 name/department/role/contact
- `app/retrieval/tag_matcher.py` **TagMatcher.match(resolved_concepts, expand)**:
  - **一级(细分层)**:resolved concept_ids → PCE 直查 → `leaf_exact`,confidence 原值,relation_type=self_declared_scope(§7.9 红线:不是 responsible_for)
  - **二级(概念层)**:concept_relations 白名单关系(broader/narrower/related/component_of)**一跳**泛化(§7.7 默认限制),邻居概念再查 PCE → `concept_generalized`,**confidence×0.8 降权**,relation_path 记录扩展路径(可写 Trace);扩展概念回写 ConceptState.expanded_concepts
- `app/retrieval/responsibility.py` **MockResponsibilityRetriever**:`degraded = True` 类属性显式标记(§18);按概念名 ILIKE 匹配责任标题/描述,Join 部门名,输出 §9.4 全字段(受理/责任部门/责任人/时限/转办/升级/来源/版本)。**模块 26 将替换为 MCP get_responsibility**
- `app/agent/nodes/structured_retrieval.py` **StructuredRetrievalNode**:按 query_type 分流——contact_lookup 只走 DirectorySearch(rag_documents/responsibility_evidence 保持空);explicit_responsibility 走 TagMatcher(不泛化)+ Mock 责任(有结果则 degraded 标记入 degraded_sources);diagnostic/expert_finding 走两级匹配
- 测试 `tests/test_structured_retrieval.py`(5 用例):姓名通讯录、leaf_exact+RawTag 保留、临时关系验证泛化降权+relation_path(测后清理)、contact_lookup 零 RAG、explicit_responsibility 的 Mock 责任+degraded 标记,全部通过(累计 71 passed)

## 遇到的问题报错及解决方法

无。测试数据仓库→数据治理的临时关系验证了泛化路径;存量 61 个概念间尚无真实关系,Concept Relations 的真实数据待模块 17/18 治理填充。

## 上下游接口及依赖

- 上游:模块 13 resolved_concepts/PCE Repository、模块 12 mentioned_people/departments、模块 08 Mock 责任表、模块 04 PersonEvidence/ResponsibilityRecord 契约
- 下游:
  - 模块 15 CandidateMerger 消费 structured_candidates 与 responsibility_evidence 做融合
  - 模块 25/26 MCP 建成后,MockResponsibilityRetriever 被 KnowledgeMcpClient.get_responsibility 替换(同接口)
  - 模块 28 评测:Structured Recall@3 评一级匹配输出
- 对外接口:`DirectorySearch.search()`、`TagMatcher.match()`、`MockResponsibilityRetriever.get_responsibility()`、`StructuredRetrievalNode`
