# 模块 08:legacy 迁移 + Mock 责任数据

## 背景

对应开发计划的既定决策「新建数据库 + 导入 300 人」和 V1.2 §17(public 业务事实)。旧库 `shouwenzeren` 有 300 人/30 文/1012 条人员-领域关系,是整个平台最有价值的真实资产;而 `responsibility_assignments`(正式责任唯一事实源,§10.5)旧库没有,需要按文档 Mock(§23 待确认事项:「Responsibility 数据未冻结 → 建 Mock ResponsibilityItem」)。旧库只读,不做任何修改。

## 任务

- 输入:旧库 people(300)/ content(30)/ domains(61)/ person_domains(1012)/ department_paths(20)/ content_tags(90)
- 输出:新库 public 业务事实 + agent.raw_tags/person_tags + Mock responsibility_assignments
- 验收:行数逐项核对;人员-部门全关联;责任人归属正确

## 实现方式

- `scripts/migrate_legacy.py`(可重复执行,幂等 UPSERT):
  - **departments** ← department_paths(20 个,level1/2/3 拼 path);返回 name→id 映射
  - **people** ← people(300,保留 p-XXXX 主键,department_id 按部门名关联)
  - **contents** ← content(30,summary+body 合并为 body,type→content_type,状态「已发布」→published)+ content_tags 聚合成 tags 数组
  - **agent.raw_tags** ← domains(61 个领域名,即员工的"负责领域"原始表达,§7.1 RawTag);**agent.person_tags** ← person_domains(1012,source='self',created_by=本人)——这是 V1.1「负责领域自由填写」模型在存量数据上的落点
  - **Mock 责任数据**:每部门取人员覆盖人数前 3 的领域生成「XX相关事务」责任项,责任人=该部门内覆盖该领域且 completeness 最高者(确定性),带时限/转办条件/升级路径,生成 24 条
- 中途发现并修正一个错误:Mock 责任最初误写成从新库 `public.person_domains` 查数据,但该表只存在于旧库——已改为从迁移后的 `agent.person_tags + raw_tags` 生成
- 测试 `tests/test_migrate_legacy.py`:300 人/20 部门/无孤儿部门引用/30 文带标签/61 tag/1012 pt/责任数量区间/责任人必须属于责任部门,全部通过(累计 41 passed)

## 遇到的问题报错及解决方法

1. **Mock 责任生成写错数据源**:草稿里残留了对新库 `public.person_domains` 的查询(该表在旧库,且迁移设计已改为进 agent.person_tags)。
   解决:定稿前通读脚本发现,改为基于 agent.person_tags 统计生成;并用测试断言「责任人必须属于责任部门」防回归。
2. **旧库 peer_reviews 为空表(0 行)**:勘察后发现无评价数据可迁,新库 peer_reviews 保留空表待真实数据,不造数(评价是敏感数据,不应凭空生成)。

## 上下游接口及依赖

- 上游:旧库 `shouwenzeren`(只读)、模块 05 建好的三 schema
- 下游:
  - 模块 09(Seed Concept 冷启动)从 agent.raw_tags、people.role/department、contents.tags 抽种子概念
  - 模块 13(PersonConceptEvidence)基于 agent.person_tags × tag_concept_map 构建
  - 模块 21(责任发布链)把 responsibility_assignments 发布为 OKF ResponsibilityItem
- 对外接口:`scripts/migrate_legacy.py`(幂等,可重跑)
