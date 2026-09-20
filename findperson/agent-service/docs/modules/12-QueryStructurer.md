# 模块 12:QueryStructurer

## 背景

对应 V1.2 §6.1(找人查询的问题理解)。文档给它划了两条硬边界:①「只表达用户问题,不完成最终概念链接」——概念对齐是 ConceptLinker(模块 13)的事,不能越界;②「解析失败不产生虚假概念」,并要求「明确文本中显式出现与模型推断得到的字段来源」。它输出的 UnderstandingState 是查询侧 ConceptLinker 的输入(§7.6)。

## 任务

- 输入:normalized_query + IntentState(仅 find_person 执行)
- 输出:UnderstandingState(systems/objects/symptoms/duty_clues/people/departments/field_sources/explicit_terms)
- 验收:字段来源 explicit/inferred 标注正确;LLM 失败无虚假概念、保留词典匹配、degraded

## 实现方式

- `app/agent/query_structurer.py`
  - **QueryStructurerService**:
    1. **词典显式匹配**:people/departments 全表名在 query 中直接命中 → mentioned_people/departments,field_sources 标 `explicit`
    2. **LLM 要素抽取**(Prompt 含 JSON 示例,花括号已按模块 11 教训转义):systems/objects/symptoms/duty_clues;每个值按「是否出现在原文」再标 `explicit`/`inferred`——例如「Dify」在原文出现 → explicit,「性能优化」是模型归纳 → inferred
    3. `explicit_terms` 汇总显式词项(供 ConceptLinker 优先精确对齐,§7.6)
  - **QueryStructurerNode**:非 find_person 直接跳过(双保险,正常由编排条件控制);LLM 失败时**只保留词典匹配结果**(人名),LLM 推断字段全空——宁缺毋假,degraded 继续
- 测试 `tests/test_query_structurer.py`(4 用例):诊断句要素抽取+来源标注(「Dify」explicit/「性能优化」inferred)、人名显式匹配、非 find_person 跳过、LLM 失败无虚假概念+保留人名+degraded,全部通过(累计 60 passed)

## 遇到的问题报错及解决方法

无。直接沿用了模块 11 的教训(Prompt JSON 示例花括号转义),一次通过。

## 上下游接口及依赖

- 上游:模块 11 IntentState、模块 06 LLM Client、public.people/departments 词典、模块 03 UnderstandingState
- 下游:
  - 模块 13 查询侧 ConceptLinker 消费 systems/objects/duty_clues/symptoms/explicit_terms 做概念对齐
  - 模块 28 评测:QueryType/概念错误的归因分界点(结构化错 ≠ 概念链接错)
- 对外接口:`QueryStructurerService.structure(query)`、`QueryStructurerNode`、`STRUCTURER_PROMPT`
