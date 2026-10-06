# 模块 18:LLM 受约束消歧 + Candidate Concept 治理

## 背景

对应 V1.2 §7.4(员工侧 RawTag → Concept 受约束链接:LLM 只能输出 LINK_EXISTING/CREATE_CANDIDATE/AMBIGUOUS/REJECT,且只能选候选中的 concept_id,**不允许创造数据库不存在的正式 Concept**)、§7.5(Candidate Concept 治理:候选≠正式,五种审核动作,**审核后自动回填相关 RawTag 映射**,概念变更版本化)。这是「Concept 随真实使用持续演化」的动态治理闭环,也是阶段 2 的验收核心:「新 RawTag → 自动映射 → 低置信审核 → Candidate Concept → 人工转正」全流程可运行。

## 任务

- 输入:员工新填写的负责领域(person_id + text);审核队列条目
- 输出:RawTag 注册链接全链路结果;治理审核动作与回填
- 验收:高置信自动映射不进审核;候选隔离;转正回填;非法 concept_id 零落库;原文不被覆盖

## 实现方式

- `app/agent/concept_governance.py`
  - **RawTagConceptLinker.register_raw_tag(person_id, text)**(员工侧完整六级链):
    1. RawTag 原样落库(已存在复用;§7.1 原文红线)+ person_tags 幂等关系
    2. 已有生效映射直接复用(第三级)
    3. 五级候选召回(模块 17);≥0.97 确定性命中 → rule 自动映射(auto_approved)
    4. 否则第六级 LLM 受约束消歧(候选注入 Prompt,四选一):
       - LINK_EXISTING:**校验 concept_id 必须在候选集合内**,不在则拒绝落库并进 anomaly 队列;合法则建 pending 映射 + 入审核队列
       - CREATE_CANDIDATE:建 candidate 概念(status 隔离,suggested_name/source_tags)+ 入审核队列
       - AMBIGUOUS/REJECT:入审核队列,不建映射
  - **ConceptGovernance.review(review_id, action, operator)**:pending 状态守卫;
    - candidate_concept 五动作:APPROVE/RENAME_APPROVE(转正 active,version+1)、MERGE/AS_ALIAS(旧 candidate deprecated + 指向目标概念/建别名)、REJECT(deprecated)
    - low_confidence_mapping:批准 → approved 生效;拒绝 → rejected
    - **回填**:转正/合并/别名化后,来源 RawTag 自动建 near_alias 映射到正式概念(human,auto_approved)
    - 全程 `registry.invalidate()` 失效缓存
- 测试 `tests/test_concept_governance.py`(5 用例):生效映射复用、**全流程**(CREATE_CANDIDATE→隔离→批准→回填→状态核对)、LLM 幻觉 ID 防线(零落库+anomaly 队列)、AMBIGUOUS 入队、原文保留,全部通过(累计 91 passed)

## 遇到的问题报错及解决方法

1. **StubLLM 位置参数错传**:`RawTagConceptLinker(StubLLM(...))` 把 stub 传给了第一参数 recall,报 `'StubLLM' object has no attribute 'recall'`,并连锁导致测试数据未清理(后续迁移/种子测试因残留数据失败)。
   解决:改为关键字传参 `llm=StubLLM(...)`;级联失败在根因修复后自动消失。
2. **PowerShell 批量改文件导致编码损坏**:试图用 `Get-Content -replace | Set-Content` 改测试文件,GBK 读 + UTF8 写导致全文乱码(SyntaxError U+FF04)。
   解决:用 WriteFile 重写文件。教训:**绝不用 PowerShell 管道改写含中文的源文件**,一律用 WriteFile/StrReplaceFile。

## 上下游接口及依赖

- 上游:模块 17 五级召回、模块 06 LLM Client、模块 09 Registry(invalidate)、agent.* 语义层各表
- 下游:
  - 模块 26:查询侧 ambiguous 时的消歧复用本模块 LLM 受约束机制
  - 模块 28 评测:RawTag→Concept Accuracy/Review Rate 评 register_raw_tag 链路
  - 未来员工端 API(写操作阶段)调 register_raw_tag 作为「负责领域填写」入口
  - 治理产出(新正式概念/别名/映射)即时反映到模块 13 查询侧链路
- 对外接口:`RawTagConceptLinker.register_raw_tag()`、`ConceptGovernance.review()`、`DISAMBIGUATION_PROMPT`
