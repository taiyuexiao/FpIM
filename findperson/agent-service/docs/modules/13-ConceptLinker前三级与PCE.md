# 模块 13:ConceptLinker(前三级)+ PersonConceptEvidence Builder

## 背景

对应 V1.2 §7.6(查询侧 ConceptLinker:与员工侧共用同一套 Concept Registry 和 Candidate Recall)、§7.3(六级映射链——本模块实现前三级确定性召回)、§9.2(PersonConceptEvidence:低成本确定性人员召回索引,保留原始 RawTag 用于解释,relation_type 不得为 responsible_for)。这是「员工语言 ↔ 用户语言在统一 Concept 上对齐」的运行时核心。

## 任务

- 输入:UnderstandingState 的 explicit_terms/systems/objects/duty_clues/symptoms
- 输出:ConceptState(candidate/resolved/ambiguous/link_trace)+ PCE 视图与 Repository
- 验收:唯一高分命中即 resolved;多概念歧义标记;未登录表达不产生虚假 resolved(非法 concept_id=0);PCE 按 concept_id 召回人员且保留 source_raw_tag、增量刷新

## 实现方式

- `app/agent/concept_linker.py`
  - **ConceptCandidateRecall**(前三级,§7.3):
    1. Canonical Name Exact(normalized 比较,score=1.0)
    2. Alias Exact(alias 词典,0.98)
    3. RawTag Historical Mapping(规范化文本命中已审核 RawTag 的生效映射,0.97×confidence 封顶)
    全部走模块 09 的 ConceptRegistry(员工侧/查询侧共用,§7.6);第四/五级(pg_trgm/向量)预留到模块 17 在同一类上追加
  - **QueryConceptLinker.link(terms)**:逐表达召回 → 确认规则「唯一 ≥0.9 命中 → resolved;多个不同 Concept → ambiguous」;每步写 concept_link_trace;**query→concept 结果 LocalCache 300s**(§14.4)
  - **ConceptLinkerNode**:仅 find_person 执行;链接顺序 = explicit_terms 优先,再系统/对象/职责线索/症状;写 agent.query_concept_logs(失败不阻断主链)
- `scripts/ddl/04_agent_views.sql` + `app/retrieval/person_concept_evidence.py`:
  - **SQL 视图** `agent.person_concept_evidence` = person_tags × tag_concept_map(生效映射)× raw_tags。刻意用实时视图而非物化表——RawTag/Concept 更新后证据**天然增量刷新**,免去刷新任务(§9.2 验收)
  - **PersonConceptEvidenceRepository**:`find_by_concepts()`(默认只返回 active)、`find_by_person()`
  - init_db.py 已纳入 04_agent_views.sql,全新环境一键含视图
- 测试 `tests/test_concept_linker.py`(6 用例):精确召回、大小写/空白不敏感、唯一命中 resolved+缓存一致、未登录词零虚假 resolved、PCE 召回+relation_type=self_declared_scope+source_raw_tag 保留、**视图增量刷新实测**(临时插 tag+映射立即可查,测试后清理),全部通过(累计 66 passed)

## 遇到的问题报错及解决方法

无。一处设计决策:阶段 1 的 ambiguous 只做标记不做 LLM 消歧(第六级在模块 18),符合「先纯结构化闭环」的阶段划分;alias 表当前为空,第二级通路已由代码与单测覆盖,等治理(模块 18)产出真实别名。

## 上下游接口及依赖

- 上游:模块 09 ConceptRegistry(词典/别名/映射缓存)、模块 12 UnderstandingState、模块 07 CachePort、模块 05 DB
- 下游:
  - 模块 14 TagMatcher 消费 resolved_concepts + PCE Repository 做结构化召回
  - 模块 17 在 ConceptCandidateRecall 上追加 pg_trgm/向量召回;模块 18 追加 LLM 消歧与 ambiguous 处理
  - 模块 26 diagnostic 的 ConceptRelationExpand 消费 resolved_concepts
  - 模块 28 评测:Query→Concept Accuracy/Recall 评的就是 link() 输出;query_concept_logs 是归因数据源
- 对外接口:`ConceptCandidateRecall.recall(text)`、`QueryConceptLinker.link(terms)`、`ConceptLinkerNode`、`PersonConceptEvidenceRepository`
