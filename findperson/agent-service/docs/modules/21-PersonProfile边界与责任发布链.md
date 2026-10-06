# 模块 21:PersonProfile 边界 + 责任发布链(端到端)

## 背景

对应 V1.2 §10.4(PersonProfile 的 OKF 边界:叙述性正文可进,raw_tags/person_tags/concept_ids/动态推断标签/内部权重**绝不进**)、§10.5(正式责任知识发布链:responsibility_assignments 是唯一事实源 → ResponsibilityPublisher → OKF ResponsibilityItem → RAG 索引;Agent 主路径不直读业务表)。§19 阶段 3 验收:「能够从 Mock 业务数据稳定生成可发布、可版本化、可追溯的 OKF」。

## 任务

- 输入:public 业务事实(24 责任/300 人/30 文/20 部门)
- 输出:四类 OKF 构建器 + 全量发布脚本 + 真实 Git 仓库 374 份 Published
- 验收:白名单零泄漏;全部可反查业务来源;幂等重跑零变更

## 实现方式

- `app/okf/builders.py`:
  - **build_responsibility_doc()**(§10.5):正文含受理部门/责任部门/责任人/时限/转办条件/升级路径,extra 结构化保留同名字段,source_uri 指回业务表
  - **build_person_profile_doc()**(§10.4):`PERSON_PROFILE_ALLOWED = (name, department, role, self_portrait)` **白名单过滤**,自我介绍正文进、他人评价聚合正文进(标记低权重);raw_tags/concept_ids 等动态数据留在 agent schema
  - **build_content_doc()**:标题+正文+主题标签+作者;owner_department 取作者部门(13 必备字段)
  - **build_department_doc()**:部门名+组织路径+在编人数
- `scripts/publish_okf.py`:全量发布,幂等(Publisher content_hash 增量判断)
- **真实运行结果**:首跑 374/374 发布成功(24 责任 + 300 人 + 30 文 + 20 部门,344 首次 + 30 修复后补发),**幂等复跑 changed=0**;Git 仓库每份一个版本
- 测试 `tests/test_okf_builders.py`(5 用例):白名单零泄漏(正文与 extra 都不含 raw_tags/concept_ids)、PersonProfile 可过校验链、责任文档全字段、真实仓库 374 份四类计数 + 逐份来源/哈希/版本核对、真实 PersonProfile 无动态标签,全部通过(累计 101 passed)

## 遇到的问题报错及解决方法

1. **30 份 Content 发布失败**:`build_content_doc` 把 `owner_department_id` 置 None,被校验链 schema 步拦截(必备字段)——校验链真实发挥了守门作用。
   解决:Content 的归属部门取作者所属部门(查询 join people.department_id 传入),修复后 374/374 全过。

## 上下游接口及依赖

- 上游:模块 19 Publisher/Validator、模块 20 Repository、public 业务事实(模块 08)
- 下游:
  - 模块 22 Chunker 消费这 374 份 Published OKF;模块 23 RAG Indexer 以此为唯一输入
  - 模块 25 MCP get_responsibility/get_person_profile/get_document 的数据源
  - 模块 26:RAG 证据的知识本体
- 对外接口:四个 `build_*_doc()` 构建器、`PERSON_PROFILE_ALLOWED`、`scripts/publish_okf.py`、`knowledge-okf/` Git 仓库
