# 模块 11:意图识别 + RuleFallbackRouter

## 背景

对应 V1.2 §5.2(一级意图与查询类型识别:5 个一级意图 + find_person 的 4 种 query_type;「LLM 输出必须限制为 Schema」「LLM 不允许直接产生人员 ID、最终概念 ID 或数据库查询语句」)和 §5.3(RuleFallbackRouter:LLM 不可用时应急,只覆盖高确定性情况,不猜测复杂责任关系,降级输出显式 degraded=true)。意图是主链第一个 Node,它决定 QueryStructurer、策略路由和 RankPolicy 的全部走向。

## 任务

- 输入:normalized_query
- 输出:IntentState(intent/query_type/confidence/needs_clarification/clarify_question)
- 验收(本模块达成情况):LLM 正常时枚举严格合法;LLM 故障降级规则;规则不覆盖时显式 unclear 不猜测。文档基线(意图 Accuracy≥97% 等)留待模块 28 评测集验证

## 实现方式

- `app/agent/intent.py`
  - **IntentService**:业务 Prompt 归本模块(§14.1:LLM Client 不维护业务 Prompt);`structured_chat` JSON 模式 + required_keys;枚举严格校验——非法 intent/query_type 抛 `INTENT_ERROR`(把「输出必须限制为 Schema」做成运行时校验);unclear 自动 needs_clarification
  - **RuleFallbackRouter**(§5.3):加载 people 姓名词典,三条高确定性规则——「姓名+电话/联系方式」→contact_lookup(0.95)、「谁负责X」→explicit_responsibility(0.9)、「某部门找人」→contact_lookup(0.85);其余一律返回 None(不尝试复杂诊断)
  - **IntentNode**(AgentNode,on_error=degrade 双保险):正常走 IntentService;捕获 LLM_ERROR/TIMEOUT/INTENT_ERROR → 降级规则路由(命中则 degraded=true 继续);规则也不覆盖 → 显式 unclear + 澄清话术 + degraded,**不猜测**(§5.3 红线)
- 测试 `tests/test_intent.py`(5 用例):LLM 正常解析、非法枚举值→INTENT_ERROR、LLM 故障降级规则(真实库姓名「王丹」命中查电话)、双不可用→unclear、规则只覆盖高确定性(复杂诊断句不命中),全部通过(累计 56 passed)
- **真实 DeepSeek 冒烟** `scripts/smoke_intent.py`:5 个典型问题全部分类正确——「谁负责智能体平台」→explicit_responsibility、「Dify并发超时找谁」→diagnostic、「GPU算力申请流程」→knowledge_qa、「王丹电话」→contact_lookup、「今天天气不错」→chat

## 遇到的问题报错及解决方法

1. **`KeyError: '"intent"'`(4 个测试失败)**:INTENT_PROMPT 里给 LLM 的 JSON 示例含字面花括号 `{"intent": ...}`,而代码用 `INTENT_PROMPT.format(query=query)` 插值,Python 把 `{"intent"}` 当成格式字段。
   解决:示例 JSON 的花括号全部转义为 `{{ }}`,56 全过。教训:含 JSON 示例的 Prompt 模板禁用 `.format`,或必须双花括号转义——后续模块的 Prompt 统一用转义或 `str.replace`。

## 上下游接口及依赖

- 上游:模块 06 LLM Client(structured_chat)、模块 10 AgentNode/ServiceRegistry、模块 03 IntentState/枚举、public.people(规则词典)
- 下游:
  - 模块 12 QueryStructurer 读 intent(find_person 才执行)
  - 模块 16 策略路由按 query_type 分流;chat/unclear 走提前终态
  - 模块 15 PeopleRanker 按 query_type 选 RankPolicy
  - 模块 28 评测:Intent Accuracy、query_type Accuracy 即本模块输出
- 对外接口:`IntentService.classify(query)`、`RuleFallbackRouter.route(query)`、`IntentNode`、`INTENT_PROMPT`
