# 模块 09:Seed Concept 冷启动 + ConceptRegistry

## 背景

对应 V1.2 §7.2(Canonical Concept 模型与 Seed Concept 冷启动)和 §19 阶段 1 的第一步。文档明确两条红线:① 冷启动不能等全员填完负责领域再建 Concept,否则陷入「没人填→没标签→没概念→查人不好用」死循环;② Seed Concept 不由 LLM 凭空生成,必须从企业已有真实资产抽取。同时 §7.6 要求员工侧与查询侧共用同一套 Concept Registry,因此同步建设 Registry 服务。§0.1 规模前提(概念库数百级)允许词典全量内存缓存。

## 任务

- 输入:agent.raw_tags(61)、public.contents.tags、public.responsibility_assignments
- 输出:agent.concepts 首批 Seed Concept + 第一级精确映射 + ConceptRegistry 服务
- 验收:概念有稳定 ID、可增量;存量 RawTag 全部挂上 Concept;Registry 缓存生效、不含 candidate

## 实现方式

- `scripts/seed_concepts.py`(幂等可重跑):
  1. **种子汇集**(三来源,对应 §7.2「正式系统/平台/项目/部门职责/正式责任事项/技术目录」):raw_tags 61 个负责领域表达、contents.tags 文章主题、responsibility 责任事项领域(剥掉「相关事务」后缀);按规范化文本去重得 69 个候选
  2. **类型启发式**:含「平台」→platform、「系统」→system、含开发/治理/分析等 →capability、其余 domain
  3. 写入 `agent.concepts`(concept-seed-NNNN 稳定 ID,status='seed',description 记录来源)——69 个
  4. **第一级自动映射 Canonical Name Exact**(§7.3):raw_tag.normalized_text == concept.canonical_name(lower) → `tag_concept_map`(exact_alias, confidence=1.0, generated_by='rule', auto_approved)——61 条,存量 RawTag 100% 覆盖
- `app/agent/concept_registry.py` **ConceptRegistry**:
  - `load_concepts(include_candidate=False)`:正式概念词典(seed/active),LocalCache TTL 300s 全量缓存(§14.4 concept dictionary);治理侧可 include_candidate=True
  - `load_aliases()` / `load_tag_mappings()`(只取 auto_approved/approved 生效映射)/ `get_raw_tag_by_text()`
  - `invalidate()`:供阶段 2 治理动作后主动失效缓存
  - 单例 `get_concept_registry()`
- 测试 `tests/test_seed_concepts.py`:种子数量与完整字段、RawTag 零未映射、exact_alias 数量、Registry 加载+缓存+不含 candidate、按文本查 RawTag,全部通过(累计 45 passed)

## 遇到的问题报错及解决方法

无阻塞问题。设计取舍:责任事项标题的领域提取用了「去掉『相关事务』后缀」的确定性规则(因为 Mock 责任数据是该脚本可预期的格式);8 个仅来自 contents/responsibility 的概念没有对应 RawTag,属于正常——它们将在查询侧召回和后续治理中发挥作用。

## 上下游接口及依赖

- 上游:模块 08 迁移数据(raw_tags/contents/responsibility_assignments)、模块 07 LocalCache、模块 04 Concept/TagConceptMap 契约
- 下游:
  - 模块 13 ConceptLinker 前三级召回(Exact/Alias/Historical)直接消费 Registry 的词典与映射
  - 模块 13 PersonConceptEvidence Builder = person_tags × tag_concept_map
  - 模块 17 的 pg_trgm/向量召回在 Registry 词典上做候选召回
  - 模块 18 治理动作(转正/合并/改名)写 concepts 后调 `invalidate()`
- 对外接口:`ConceptRegistry`(load_concepts/load_aliases/load_tag_mappings/get_raw_tag_by_text/invalidate)、`get_concept_registry()`、`scripts/seed_concepts.py`
