# 模块 16:AnswerBuilder + /agent/chat SSE 全链路(阶段 1 收官)

## 背景

对应 V1.2 §13(回答生成与 AG-UI)、§5.1(请求接入)、§3.1(主链基本形式),是阶段 1「Concept 冷启动与结构化人员最小闭环」的收官模块。文档对回答层有三条铁律:① 回答强制分「检索到的事实/建议」;② 人员必须标注身份,且**不得把文章作者描述成正式负责人**;③ Hermes 不得新增 PeopleRanker 未返回人员、不得修改顺序。§19 阶段 1 验收案例:员工A 填 AgentOS、员工B 填 Agent平台,用户问「谁负责智能体平台?」须同时召回 A、B。

## 任务

- 输入:ranked_candidates + gate_decision(及 chat/unclear/edit/knowledge_qa 各意图态)
- 输出:ResponseState(facts/suggestions/cards/clarification)+ /agent/chat SSE 端点 + 主链装配
- 验收:阶段 1 验收案例通过;空结果不编造;SSE 事件序列与四个 ID 完整;未认证 401

## 实现方式

- `app/agent/answer_builder.py`
  - **AnswerBuilder**(确定性模板,离线可测;LLM 润色留作后续可选项,不改变事实与顺序):
    - 按 gate_decision 分流:no_result(诚实空答+建议,**不编造**)→ clarify(歧义澄清,概念歧义时列出歧义词)→ answer/degraded_answer(组织事实+建议)
    - `_identity_of()`:正式责任→正式责任人;leaf_exact→明确负责领域命中者;文章→领域专家;画像→能力候选人;其余→相关参与者(**文章作者永远不可能被标为正式责任人**)
    - contact_lookup 专用事实模板(姓名/部门/岗位/联系方式);explicit_responsibility 无正式责任时自动附「以上基于自填负责领域,建议确认」的建议;事实只呈现 Top5(见问题 2)
  - **AnswerBuilderNode**:chat(简单实现)/unclear(澄清)/edit(识别但不执行,§5.2)/knowledge_qa(显式降级「建设中」,不编造知识)四意图提前终态
- `app/agent/chain.py`:主链装配 Intent→QueryStructurer→ConceptLinker→StructuredRetrieval→Merger→Ranker→Gate→AnswerBuilder,find_person 条件挂载(§3.1 基本形式)
- `app/api_agent.py`(§5.1/§13.2):
  - **[Demo 身份适配器]** X-User-Id → public.people 校验构建可信 UserContext;未认证/不存在 → **HTTP 401 建流前错误**;真实 JWT 在模块 30 替换,接口不变
  - **AG-UI/SSE**:run_started → text_delta×N(24 字分块)→ clarification? → recommendation_cards? → citations? → run_finished;四 ID(sessionId/runId/messageId/traceId)齐全;**SSE 建流后错误走 run_error 事件**(与建流前 4xx 分开,§5.1)
  - QueryNormalizer(空白压缩)在接入层完成
- 测试 `tests/test_full_chain.py`(6 用例):**阶段 1 验收案例**(临时构造 AgentOS/Agent平台→统一 Concept 智能体平台,全链跑出 p-0001/p-0002 双召回+正式/自填区分建议)、事实/建议分块、空结果不编造、身份标签规则、SSE 端到端(401/事件序列/四 ID/查到王丹),全部通过(累计 81 passed)
- **真实端到端冒烟**(uvicorn + 真实 DeepSeek + 真实 PG):「谁负责数据治理?」→ 郑婷婷(正式责任人,score 10.8,带责任部门/时限/升级路径)+ 王丹等 5 人卡片(明确负责领域命中者),degraded=true(Mock 责任适配器),gate=degraded_answer,全程 3.0s

## 遇到的问题报错及解决方法

1. **ConfidenceGate 误杀阶段 1 验收案例**:员工 A、B 同分(同 Concept 并列),旧闸门规则「Top1/Top2 差距过小 → clarify」把并列人选误判为歧义,验收案例走到了澄清分支。
   解决:闸门增加「同 Concept 并列豁免」——Top1/Top2 命中同一 concept_id 属于并列人选而非需要用户澄清的歧义,应并列返回;不同概念才 clarify。已补充单测。
2. **套件级缓存污染(单测孤立通过、套件内失败)**:验收 fixture 临时插入 concept/映射,但 ConceptRegistry 的概念词典与 query→concept 缓存(TTL 300s)已被前面的测试预热,看不到新数据。
   解决:fixture 插入后与清理后都 `get_cache().clear()`。教训:后续模块凡写语义层数据的测试都必须处理缓存。
3. **事实列表刷屏**:真实冒烟发现某领域有 ~50 个 leaf_exact 命中者时,回答把 50 人全部列出。
   解决:AnswerBuilder 事实部分只呈现 Top5(MAX_FACT_CANDIDATES),完整候选在 recommendation_cards。
4. **PowerShell 调 SSE 的坑**:Invoke-WebRequest 对流式响应抛 NullReferenceException;curl.exe 在 PowerShell 里 JSON 内联引号被吞。
   解决:改用 `curl.exe -N --data-binary "@文件"` 方式验证,不做内联 JSON。

## 上下游接口及依赖

- 上游:模块 10-15 全部(编排/意图/结构化/概念链接/检索/融合/排序/闸门)、模块 05 DB 连接池(main.py startup 初始化)
- 下游:
  - 模块 24/25/26:KnowledgeRetrievalNode 将以 `add_parallel` 并联进主链;knowledge_qa 的占位分支将被 MCP search_knowledge 真实实现替换
  - 模块 27:Trace 落库消费 ExecutionState.node_spans;agent_recommendation_logs 落 ranked
  - 模块 29:在接入层加限流/全链超时;模块 30:Demo 身份适配器换 JWT
- 对外接口:`POST /agent/chat`(SSE,X-User-Id 头)、`AnswerBuilder`、`build_orchestrator()`、`build_service_registry()`
