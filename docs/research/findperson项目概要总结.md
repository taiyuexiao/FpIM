# findperson 项目概要总结

> 源码：https://github.com/taiyuexiao/findperson
> 阅读方式：全量克隆到临时目录通读（未在本工作目录产生任何中间文件）
> 阅读范围：根目录文档 8 份、`agent-service/` 全部 62 个 Python 模块（约 8,100 行）、`backend/` 全部 API、`src/` 前端结构、DB DDL 6 份、209 个测试用例、144 条评测集
> 整理日期：2026-09-17

---

## 一、一句话定位

**「首问责任平台」**——面向组织内部协作场景的 **AI 找对人 + 责任定位 + 知识沉淀** 平台。

用户用自然语言提问（"报销系统权限申请该找谁？""集群老是报警找谁？"），系统判断意图后做三件事之一：

1. **找人**：从组织、标签、正式责任登记、已发布内容中，找出最合适的责任人/专家，给出**带命中依据**的人员名片（不含糊的"匹配度高"）；
2. **找知识**：检索已沉淀知识给出带引用的回答（架构收敛后并入"找人"，以名片作答）；
3. **写操作**：把"改我的资料""给同事写评价""发一篇文章"等意图转成**可确认的草稿卡**，用户确认后由业务后端落库。

关键取舍：**宁可诚实空答，绝不编造责任人。**

---

## 二、要解决的问题

| 痛点 | 平台对策 |
|---|---|
| 找人难：不知道这事归谁管 | 自然语言提问 → 人员名片推荐（首推 / 可协助 / 相关人员） |
| 责任不清：口口相传无凭据 | 「正式责任登记」作为最高优先级证据，给出责任部门、时限、升级路径 |
| 能力沉淀难：经验散落在个人 | 自画像 / 他画像（同事评价）/ 发布内容三类资产，反向提升推荐质量 |
| 乱贴标签骚扰 | 三层标签体系 + 他人标签「待放行」信任分级，未放行降权 |
| AI 幻觉 | 置信门禁 + 确定性排序 + 全程可解释留痕 |

平台上没有独立的"内容检索门户"——已发布内容只在人员主页、个人中心、内容详情和问答关联结果中出现，定位是**推荐依据**而非内容社区。

---

## 三、整体架构

### 3.1 四层结构

```
┌─ 交互层 ─── Web 前端（Vue3 + Vite + Element Plus）
│             智能问答 / 名片库 / 人员主页 / 个人中心 / 内容 / 后台管理 / Agent 可观测
├─ 业务服务层 ─ backend（FastAPI, :8001）—— 业务事实的【唯一写入方】
│             认证、人员部门、内容审核、评价、会话、统计；JWT + RBAC + 审计日志
├─ 智能服务层 ─ agent-service（FastAPI, :8100）—— 只读、只推理、只产草稿
│             意图 → 结构化 → 概念链接 → 双路检索 → 融合 → 排序 → 置信门 → 回答
└─ 数据与知识资产层
              PostgreSQL（public 业务 / agent 语义 / rag 索引 三 schema 隔离）
              OKF 知识仓库（Git 受控 Markdown 文档库）
```

### 3.2 运行拓扑（3 进程联调）

```
浏览器(前端 Vite :5173)
  ├── 业务 API  VITE_API_BASE_URL  → backend(:8001, /api/v1/*)
  └── 问答 SSE  VITE_AGUI_BASE_URL → agent-service(:8100, /api/agui/*)
                    ▲                        │
                    └── backend 代理 /api/v1/agui/events ─┘（反馈事件转发）
                                     │
              PostgreSQL shouwenzeren_agent(public + agent + rag)
```

### 3.3 六条关键架构原则（最重要的设计决策）

| 决策点 | 选择 | 理由 |
|---|---|---|
| 智能层写业务表 | **禁止**，只产草稿 | 写操作必须经业务层校验与用户确认 |
| 模糊相似直接定论 | **禁止**，只作候选 | 责任人指认必须确定性可解释 |
| 他人标签直接全权重 | **禁止**，需本人放行 | 防乱贴标签导致的推荐骚扰 |
| 找不到时 | 诚实空答 / 反问澄清 | 不编造责任人 |
| 知识访问 | 统一走知识 MCP 接口 | 权限、审计、降级集中治理 |
| 索引更新 | 事件驱动增量 + 原子切换 | 数据新鲜且可回滚 |

另有两条数据侧红线：
- `users` 是写侧事实源（backend 维护），`people` 由**数据库触发器实时同步**，Agent 层只读 `people`；
- PersonProfile 写入 OKF 有**字段白名单**：动态标签、联系方式等敏感/易变数据不写入对外档案。

---

## 四、技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 + Vite + Element Plus + Vue Router（懒加载）+ Pinia；AGUI 事件流接入层 |
| 业务后端 | FastAPI + SQLAlchemy + Alembic + asyncpg；JWT 认证、RBAC、审计中间件 |
| 智能服务 | FastAPI + Pydantic + asyncpg；自研轻量工作流编排器（非 LangChain/LangGraph） |
| 存储 | PostgreSQL 16 + pgvector + pg_trgm |
| 模型 | LLM：DeepSeek（OpenAI 兼容，可 `LLM_USE_MOCK=1` 离线跑通）；RAG 向量：text-embedding-v4 / 1536 维；概念向量：bge-small-zh / 512 维（**两个独立向量空间，不跨空间比较**） |
| 知识仓库 | OKF（Git 受控 Markdown + YAML frontmatter），带 13 个必备字段与六步校验链 |

---

## 五、仓库结构导航

```
findperson/
├── src/                       前端应用（views / components / stores / services）
│   ├── views/                 9 个页面：登录、问答、名片库、个人中心、人员主页、
│   │                          内容发布、内容详情、他人画像、后台管理
│   ├── services/agui/         transport(SSE) / normalizer / reporter / mockStream
│   ├── services/api/          业务接口封装（http/auth/people/content/reviews/sessions/admin）
│   └── stores/                11 个 Pinia store
├── backend/                   业务后端 FastAPI（api/v1/* + api/agui/*）
│   └── app/services/          agent_client / publish_event / tag_sync —— 与智能层解耦的三条接缝
├── agent-service/             智能内核 ★核心★
│   ├── app/agent/             编排主链（orchestrator/intent/structurer/concept_linker/
│   │                          ranker/answer_builder/action_drafts/chain）
│   ├── app/agui/              AGUI 接入层（SSE 事件流 / 会话持久化 / 推荐日志）
│   ├── app/contracts/         公开契约（AgentState / MCP / Evidence / Error / Trace）
│   ├── app/core/              config / db / llm_client / embedding_client / cache / observability
│   ├── app/mcp_knowledge/     知识 MCP Server（8 个只读工具）+ 类型化 Client
│   ├── app/okf/               OKF 生成 / 校验 / 发布 / 仓库
│   ├── app/rag/               切片 / 索引 / 混合检索 / 证据适配 / 事件消费者
│   ├── app/retrieval/         结构化检索（名录 / 标签匹配 / 正式责任）
│   ├── app/feedback/          反馈记录与回流
│   ├── app/eval/              评测
│   ├── docs/modules/          30 份模块级设计文档（01~30，质量很高，强烈建议读）
│   ├── scripts/ddl/           01_public / 02_agent / 03_rag / 04_views / 05_backend_compat / 06_manager
│   └── tests/                 209 个测试用例
├── database/                  独立 database 分支（docker-compose + alembic + seed）
├── alembic/                   迁移（含 agent 兼容视图、后台表、publish_events）
├── docs/                      《首问必答平台-架构设计说明》《数据库切换Runbook》
├── schema.sql                 单文件完整建表脚本（22KB）
├── _snapshots/                旧版静态实现备份（仅回溯用，非入口）
└── *.md                       功能说明 v1~v4、实施方案 v1/v3、核心业务流程设计
```

**这个仓库最值得注意的一点**：文档密度极高。同一套设计同时存在于「业务功能说明 v4」「架构设计说明」「实施方案 v3」「30 份模块设计文档」「代码 docstring 里的 §x.x 引用」五个层级，且互相可追溯。读代码时几乎每个函数都能定位到设计文档章节号。

---

## 六、功能点清单

### 6.1 前端八类业务页面

| 页面 | 核心能力 |
|---|---|
| **智能问答**（登录默认首页） | 三栏布局（历史栏 / 主对话区 / 详情栏）；会话新建·搜索·重命名·删除；SSE 流式回答；推荐卡片 + 确认卡片；右侧详情栏打开人员/内容/待提交字段；空会话复用（不产生连续空记录） |
| **名片库** | 关键词搜索（姓名/部门路径/岗位/领域标签/自画像/部门职责）+ 部门树筛选（任一节点含下级）；人卡片 → 人员主页 |
| **人员主页** | 姓名、完整部门路径、岗位、联系方式、**上级（可点击跳转）**、负责领域、自画像、**他画像气泡图**（按事项聚合，大小反映评价人数）、部门职责、已发布内容 |
| **个人中心** | 资料摘要 + 三个动作（编辑 / 为他人画像 / 发布）；**我的发布**（草稿·待审核·已发布·已驳回 + 审核意见 + 编辑/删除/置顶） |
| **他人画像** | 选同事（排除本人）+ 日期 + 事项（≤20 字，可从目标人负责领域与既有画像中搜索，或选"其他"自定义）；「我添加的事项」支持继续补充 / 删除 |
| **内容发布 / 详情** | 标题、关联领域、摘要、正文；**状态机**：草稿 → 待审核 → 已发布 / 已驳回；保存快照机制（新版本待审期间对外继续展示最近已发布版本，公开内容不会突然消失） |
| **后台管理** | 三页签：数据看板（参与人数 / 已发布内容 / 待审核 / 本周推荐量 + 推荐榜单 + 7 日活跃趋势）、成员管理（含部门负责人、账号状态）、内容审核（驳回必须填原因 + 审核轨迹） |
| **Agent 可观测** | 按时间/用户/问题检索任意一轮问答，逐节点展开：意图判定、概念对齐过程、走了哪条检索路、每个候选人证据构成与得分、最终回答与卡片、用户反馈；另有推荐反馈面板（有帮助率、7 日趋势、点踩原因分布、逐条明细） |

### 6.2 角色与权限

| 角色 | 能力边界 |
|---|---|
| 普通成员 | 问答、看名片库与公开人员主页、维护**本人**联系方式/负责领域/自画像、为他人补画像、管理**本人**内容 |
| 部门负责人 | + 编辑本人负责部门**及其全部下级部门**的部门职责（由部门树负责人关系计算，卸任即失权） |
| 管理员 | + 后台管理：成员、部门、负责人、系统角色、内容审核、全局运营数据与可观测 |

前端入口隐藏只是体验优化；**接口层一律二次校验权限**。个人信息不可维护姓名/部门/岗位/角色（由管理员统一维护）。

### 6.3 后端 API 清单（`/api/v1`）

| 模块 | 端点 |
|---|---|
| auth | `POST /login`、`POST /register`（管理员建号）、`POST /change-password` |
| me | `GET /me`、`PUT /me/profile` |
| people | `GET /people`（分页+搜索）、`POST /people`、`GET /people/{id}`、`PATCH /people/{id}`、`GET /people/{id}/reviews` |
| departments | `GET /departments/tree`（含成员数与领域标签）、`GET/PATCH /departments/{id}`、`PATCH /departments/{id}/responsibility`（仅负责人）、`POST /departments` |
| contents | `GET/POST /contents`、`GET/PUT/PATCH/DELETE /contents/{id}`、`POST /contents/{id}/submit`、`POST /contents/{id}/audit`、`POST /contents/{id}/pin` |
| reviews（信任分级核心） | `POST /reviews`、`GET /reviews/pending`（我收到的待放行）、`POST /reviews/{id}/approve`、`POST /reviews/{id}/ignore`、`GET /reviews/sent`、`GET /reviews/person/{id}`、`GET /reviews/person/{id}/history`、`DELETE /reviews/{id}` |
| sessions | `POST/GET /sessions`、`PATCH/DELETE /sessions/{id}`、`GET /sessions/{id}/messages` |
| admin | dashboard / metrics / rankings/recommend / trends/activity / statistics / feedback/summary / feedback/recent / traces / traces/{trace_id} |
| agui_proxy | `POST /agui/events`（反馈事件代理转发到 agent-service，**agent-service 挂了则优雅降级**）、`GET /agui/feedback/reasons` |
| agui（直连问答） | `POST /agui/sessions`、`GET /agui/sessions/{id}/state`、`POST /agui/sessions/{id}/messages`（SSE）、`POST /agui/events` |

### 6.4 Agent 对外接口

| 端点 | 说明 |
|---|---|
| `POST /api/agui/sessions` | 创建会话 |
| `GET /api/agui/sessions/{id}/state` | 会话状态（历史消息与卡片） |
| `POST /api/agui/sessions/{id}/messages` | **问答主入口，SSE 事件流** |
| `POST /api/agui/events` | 交互/反馈上报（`value=up/down` 为互斥反馈，重复同值自动取消） |
| `POST /agent/chat` | 文档兼容端点（SSE，`X-User-Id` 头） |
| `POST /agent/feedback` | 带 `trace_id` 的推荐反馈 |
| `GET /agent/feedback/reasons` | 点踩原因配置 |
| `GET /health` / `GET /metrics` | 健康检查 / Prometheus 指标 |

**SSE 事件序列**（单行 JSON，`type` 在 data 内）：

```
run_started(result.analysis)  →  text_delta × N  →  text_finished
   →  recommendation_cards  或  confirmation_card
   →  state_delta  →  run_finished        （异常时 run_error）
```

每个事件都携带 `sessionId / runId / messageId / traceId`，保证切会话或刷新后事件不会串号。

---

## 七、智能内核主链路（全项目最核心的部分）

### 7.1 编排模型

自研的 `AgentOrchestrator`——一个**轻量有状态工作流编排器**，不依赖 LangChain/LangGraph：

- **Node 统一约定**：`class AgentNode: async def execute(state, services) -> StateUpdate`，即"读 State + 调 Service + 写回 State"；
- **编排器只管**：执行顺序、条件分流、并行调度（`asyncio.gather`）、超时、异常收敛、状态传递、降级、终态；
- **编排器不管**：概念算法、SQL、RAG、排序、Prompt 等一切业务逻辑；
- `ServiceRegistry` 用宽松 dict 而非强类型字段，「新增 Node 不需要修改已有结构」；
- 有明确的 **Node 读写字段矩阵**（`NODE_FIELD_MATRIX`），Node 不得越权读写其他子状态。

### 7.2 链路九节点（`app/agent/chain.py`）

```
IntentNode                      意图识别（LLM + 规则降级）
  ↓ (仅 find_person)
QueryStructurerNode             问题结构化
  ↓
ConceptLinkerNode               概念链接（六级召回）
  ↓
RetrievalCoordinator            ★并行★ StructuredRetrievalNode ∥ KnowledgeRetrievalNode
  ↓
CandidateMergerNode             候选融合（按 person_id 去重，保留全部证据）
  ↓
PeopleRankerNode                确定性排序（按 query_type 选 policy）
  ↓
RelatedPeopleFallbackNode       主召回无结果时，LLM 从真实人员库选 1~3 位"可能相关"
  ↓
ConfidenceGateNode              置信门禁
  ↓
AnswerBuilderNode               回答组织（确定性模板）
```

**逐节点要点：**

| 节点 | 关键机制 |
|---|---|
| **IntentNode** | LLM 输出严格限为 Intent Schema（**不允许直接产生人员 ID、概念 ID 或 SQL**）；一级意图只有 `find_person` / `edit` / `unclear`（`knowledge_qa` 与 `chat` 已废弃收敛）；`find_person` 下二级分 4 类：`contact_lookup` / `explicit_responsibility` / `diagnostic` / `expert_finding`；**LLM 失败 → `RuleFallbackRouter` 兜底**（只覆盖"查电话""谁负责X"等高确定性模式，不猜复杂责任关系，全部显式标 `degraded=true`）；意图结果带 300s 短缓存 |
| **QueryStructurerNode** | 双通道抽取：**词典显式匹配**（人名/部门/概念名/别名）+ **LLM 抽取**，并标注每个字段来源是 `explicit`（原文出现）还是 `inferred`（模型推断），后续环节区别对待；书中书名号内容原样保留为对象（文章标题是最强检索线索）；高频问句确定性兜底正则（"谁负责X/谁懂X/X找谁"）；原文中的连续英文技术词强制补入（防 LLM 把 `Agent Tracing` 截成 `Agent`）；**LLM 失败不产生虚假概念**，仅保留词典结果 |
| **ConceptLinkerNode** | 见 §八 |
| **StructuredRetrievalNode** | `contact_lookup` → 名录精确匹配单路（不走概念与语义，保证确定性）；其余三类 → `TagMatcher` 两级匹配（叶子概念精确 `leaf_exact` / 概念关系泛化 `concept_generalized`，泛化降权 ×0.8）；`explicit_responsibility` 附加正式责任检索（走 MCP，MCP 失败降级 Mock 直读并标 `mock_responsibility_adapter`） |
| **KnowledgeRetrievalNode** | 经 MCP `search_knowledge` 取知识证据，再由 `RagEvidenceAdapter` **折算为人员证据**（"谁写过相关文章"）；检索式不是原问句而是**结构化关键词拼接**，并剥离"找谁/谁负责/请问"等问法套话；词项全空时按"英文词 + 中文二字组"生成兜底检索式 |
| **CandidateMergerNode** | **明确禁止** `structured_score + rag_score` 直接相加——证据语义不同，融合只合并证据清单，打分是 Ranker 的事；正式责任责任人即使不在候选池也要带入 |
| **PeopleRankerNode** | 见 §九 |
| **RelatedPeopleFallbackNode** | 仅在主召回 Top1 分数 < 0.05 时触发；由 LLM 从**真实人员库**选 1~3 位并给理由，分数上限锁死在 0.45 以下（**永不覆盖精确证据**） |
| **AnswerBuilderNode** | 确定性模板（离线可测，天然满足"不新增/不重排"）；**不得**新增 Ranker 未返回人员、修改顺序、把文章作者描述成正式负责人；回答强制分「检索到的事实」/「建议」；人员标注身份标签（正式责任人 / 明确负责领域命中者 / 相关参与者 / 领域专家 / 能力候选人）；`edit` 意图在此提前终态产确认卡 |

**架构收敛的一个有意思的演进**：`KnowledgeQANode` 已被删除，知识类问题由意图层映射为 `find_person/expert_finding` 走双路检索、以名片作答。也就是说**全平台对外只表达一件事——"帮你找到对的人"**。

### 7.3 统一状态模型

`AgentState` 是主链唯一运行状态，可 JSON 序列化用于 Trace 回放与评测。七个子状态：

`RequestState`（含 `user_context` 可信上下文 + 多轮 `history`）→ `IntentState` → `UnderstandingState`（含 `field_sources` 显式/推断标记）→ `ConceptState` → `RetrievalState` → `RankingState` → `ResponseState`，外层 `ExecutionState` + `AgentTrace`。

并行检索的合并是难点：`RetrievalState` 的列表字段采用**去重追加语义**而非整体替换，保证双路证据互不覆盖。

---

## 八、标签三层模型与概念治理

### 8.1 三层结构

```
用户问句  ──►  中间概念层（标准概念 + 别名）  ──►  原始标签层（员工自由填写）
                                                      │
人员  ◄──  人员-标签关系（含信任分档）  ◄──────────────┘
```

- **原始标签层（RawTag）**：员工填写的原文，**原样保存、永不改写**（事实可追溯）；
- **中间概念层（Concept）**：企业级标准概念 + 登记的**标准别名**（`llm` / `hadoop` → 对应概念）；
- **人员-标签关系层**：`source` 分三类（`self` 本人自填 / `admin` 管理员维护 / `peer_review` 同事评价）。

目的：解决"用户问句是自由说法、名片标签也是自由文本"之间的语义对齐鸿沟，且避免"一个写法一个概念"的碎片化。

### 8.2 六级候选召回（确定性从高到低）

| 级别 | 匹配方式 | 分数 | 可否自动确认 |
|---|---|---|---|
| 1 | 概念标准名精确 | 1.00 | ✅ |
| 2 | 已登记别名精确 | 0.98 | ✅ |
| 3 | 历史标签映射复用 | ≤0.97 | ✅ |
| 2.5 | 前缀 / 包含匹配 | 0.96 / 0.95（多命中 0.85） | ✅ 唯一命中时 |
| 2.6 | 字符子序列匹配（会议申请 ⊂ 会议室申请） | 0.94 | ✅ 唯一命中时 |
| 4 | pg_trgm 模糊相似 | ≤0.89 | ❌ 仅候选 |
| 5 | 概念向量相似（512 维） | ≤0.85 | ❌ 仅候选 |
| 6 | LLM 受约束消歧 | — | 人工/受约束决策 |

**只有确定性命中才自动 resolved**；后两级只出候选。代码里还埋了几道防错配的闸：

- **停用表**：`申请 / 办理 / 管理 / 运维` 等通用职能词不做前缀匹配，防"申请"错拉"申请受理"一票人；
- **泛词停用表**：`ai / bi / it / data / 数据 / 平台 / 系统` 等只允许精确级匹配，防 `ai infra` 里的 `ai` 猜出整族 AI 概念；
- **短概念名保护**：<3 字符的概念名（如 `AI`）不允许被"长词包含短名"命中；
- **模糊归一双重保险**：无确定性命中时，向量/trgm 头名需同时满足「分数 ≥0.5」+「与次名差距 ≥0.05」+「pg_trgm 有字符重叠」才自动归一——纯语义近邻会把 `HarnessEval` 错配到 `AI基础研发`，加字符重叠校验后错别字（首问必达 → 首问必答平台）仍能救回；
- **多概念歧义 → 并列归一**（至多 3 个）而非一刀切追问：`MLOps` 同时命中"MLOPS产品设计"和"MLOPS开发建设"时，给并列名片比追问更有用。

概念召回还经过 **`tag_link_sweep`** 后台轮询任务：未映射的标签自动走概念链接。

### 8.3 概念治理

- 新标签进入系统走「五级召回 → 高置信自动映射（≥0.97）→ 第六级 LLM 受约束消歧」，LLM 只能在**候选集合内**选择，输出候选外的 concept_id 会被判为 anomaly 入队；
- 四选一决策：`LINK_EXISTING` / `CREATE_CANDIDATE` / `AMBIGUOUS` / `REJECT`；Prompt 明确写着"只要语义不同——即使相关、即使同领域——必须建新概念；拿不准一律 `CREATE_CANDIDATE`，严禁为了复用而硬挂"；
- **ConceptGovernance** 支持五种审核动作：批准 / 改名批准 / 合并 / 降级为别名 / 拒绝，审核后自动回填相关 RawTag 映射，概念变更版本化（`version` + `valid_from` / `valid_to`）；
- `concept_review_queue` 承接四类待办：低置信映射 / 歧义映射 / 候选概念 / 异常。

---

## 九、双路检索 + 确定性排序 + 置信门禁

### 9.1 统一双路检索

默认开启 `RETRIEVAL_ALWAYS_DUAL=1`：**所有查人问题一律「结构化 ∥ RAG」并联召回**，不再按 query_type 分单路双路。

理由很实在：规则单路会漏掉"没打标签但发过相关文章"的人。设 `=0` 可回退旧路由，作为应急回滚开关。

配一道**无信号熔断**：理解层什么有效词都没提出（寒暄/乱码）时不进检索，防止给非找人问题随意配出名片。

### 9.2 知识检索（RAG）管线

```
权限预过滤
  → FTS/pg_trgm Top20  ‖  pgvector Top20      （两路并行）
  → RRF 融合（FTS 腿权重 2.0，向量腿 1.0）
  → 可选 Reranker（V1 默认关闭）
  → 二次权限校验
  → 按文档/章节去重
  → Top5
```

几个工程细节值得记：

- **向量噪声下限 `RAG_VECTOR_MIN_SIM = 0.55`**：实测 bge-small-zh 噪声底（`asdfgh`/`你好`）≈0.51，真实词命中 ≥0.57，低于下限的命中只是"最近邻总存在"的假象，直接丢弃；
- **多词检索式按词 OR 匹配**：整串 ILIKE 对拼接式必败（没有文档包含整串）；
- **标题参与匹配且权重 ×2**：标题短、信号集中，长 chunk 上 trgm 被稀释时标题 ILIKE 仍能命中；
- **权限过滤用 `permission_clause`**：匿名只看 `public`；已认证看 `public/internal` + 本部门 owner 或 `allowed_departments` 放行的 `restricted`；**客户端自报部门不作数**，`department_id` 必须来自可信 `user_context`。

### 9.3 确定性排序

**证据语义基础权重：**

| 证据类型 | 权重 |
|---|---|
| 正式责任登记 `formal_assignment` | 1.00 |
| 名录精确匹配 `directory_match` | 0.90 |
| 明确自填负责领域 `explicit_self_tag` | 0.80 |
| 画像推断 `inferred_from_profile` | 0.60 |
| 评价推断 `inferred_from_review` | 0.50 |
| 文章推断 `inferred_from_article` | 0.45 |

匹配层级修正：`leaf_exact` ×1.0 > `concept_generalized` ×0.7。

**按 query_type 选 RankPolicy：**

| 查询类型 | Policy | 组合公式要点 |
|---|---|---|
| `explicit_responsibility` | `responsibility_policy` | **有正式责任者直接 10.0 + 自填分**，碾压一切；否则 自填×1.0 + 画像×0.5 + 评价×0.4 + 文章×0.3 |
| `diagnostic` | `diagnostic_policy` | 正式责任×1.0 + 自填×0.9 + 文章×0.5 + 画像×0.5 + 评价×0.4 |
| `expert_finding` | `expert_policy` | 自填×1.0 + 画像×0.8 + 文章×0.7 + 评价×0.6 + 正式×0.3 |
| `contact_lookup` | `directory_policy` | 仅身份唯一性与范围校验，得分无意义 |

外加 **query-aware 关键词奖励**（≤0.3）：证据来源文本与查询词的 2/3-gram 重叠度，以及**独立的 ASCII 技术词通道**——纯英文术语不含 CJK 字符，会被中文 n-gram 生成器完全跳过，导致"文章标题精确含查询术语"这一最强信号零贡献，必须单开一条。

排序是**确定性、可解释**的：每个人由哪几类证据、各多少分构成，全部落库可查。设计上明确规定 **LLM 不能重排 PeopleRanker 的输出**。

### 9.4 置信门禁

`ConfidenceGate` 输出四种判定：`answer` / `clarify` / `no_result` / `degraded_answer`。

判定逻辑（门槛设计得很讲究）：
- 无候选 → `no_result`；
- 降级状态 → `degraded_answer`；
- 概念歧义 → `clarify`；
- Top1 分数 < 0.05 且无正式责任证据 → `no_result`；
- **兜底候选（LLM 相关推荐）直接放行**——它们本来就是"无完全匹配时的可能相关人选"，不该再被歧义规则打回；
- Top1-Top2 差距 < 0.05 且双方均无正式证据 → `clarify`；**但**若双方命中同一 Concept（同领域并列人选）则不算歧义，并列返回；且仅在 Top1 本身够强（≥0.3）时才谈歧义澄清——全是弱行为证据时，给"领域专家/相关参与者"名片比追问"能否补充条件"更有用。

**推荐卡片：宁缺毋滥。** 只出分数 ≥0.05 的达标者，最多 3 张，依次标 `首推 / 可协助 / 相关人员`，每张必须给出**具体命中依据**（正式责任 / 负责领域命中 / 自画像相关 / 发布过相关内容 / 同事评价提及 / 名录精确匹配），禁止只显示"匹配度高"。

---

## 十、写操作的人机确认闭环

用户的写操作意图**不直接执行**，走五步闭环：

1. **意图识别**为 `edit` → 按对象驱动规则快速分类写操作类型（`profile` / `review` / `content`）；规则未覆盖的长尾说法由 LLM 受约束分类兜底；
2. 系统按提问的明确程度**预填草稿卡片**：能提取多少填多少，**不编造缺失字段**（字段不足转为澄清追问）；
3. 用户点卡片 → 右侧展开详情侧栏，可**直接修改**草稿；也可一键跳转对应业务页（个人中心/画像页/发布页）继续编辑（通过 `draftId` 回填，页面地址不携带完整草稿正文）；
4. 用户点「确认」→ **由前端调用业务服务层的正式接口**完成写入，`submitTarget` 分别是 `/api/v1/me`、`/api/v1/reviews`、`/api/v1/contents`；
5. 写入后业务层发变更事件，驱动知识资产与索引增量更新。

**三类卡片：**

| 类型 | 提取字段 | 关键约束 |
|---|---|---|
| `profile` 资料维护 | `contact` / `addDomains` / `removeDomains` / `selfPortrait` | 只更新用户可维护字段；`role`/`name` 等非可维护项被丢弃；追加语义（"再加一句"）会与现有内容合并而非覆盖 |
| `review` 他人画像 | `personName` / `tag`（≤20 字） | **不能评价本人**；对象必须在名录中；同名重复提交按更新处理 |
| `content` 内容发布 | `title` / `tags` / `summary` / `body` | 摘要与关联领域**默认留空**，仅用户明确要求时生成（防 LLM 自行概括）；长正文按标题位置从原文截取、不走 LLM（保真且瞬时）；成功后提示**不得**表述为"已公开发布" |

另有一条很实用的**多轮续接通道**（`is_continuation` + `merge_draft`）：存在待确认草稿时，"再加一句 X""换成 X"这类省略式追问**直接合并草稿出新卡，零 LLM 调用，毫秒级**。代码注释记录了一次 A/B 实验：多轮续接准确率 72.7% → 100%。

---

## 十一、知识资产链路（OKF → RAG → MCP）

### 11.1 OKF 知识仓库

OKF（Organizational Knowledge Format）= Git 受控的 Markdown 文档库 + YAML frontmatter。支持 8 种文档类型：`responsibility` / `person` / `department` / `process` / `policy` / `faq` / `content` / `relationship`。

**六步发布校验链**（全部通过才写仓库，校验失败不污染当前可查询版本）：

```
YAML Schema（13 必备字段）  →  Stable ID（类型前缀 + 格式）
  →  Source（可反查业务来源）  →  Visibility / Sensitivity（0~3）
  →  链接完整性（related_okf_ids 必须存在）  →  content_hash
  →  Published OKF（写仓库）  →  触发 RAG 增量索引
```

增量判断靠 `content_hash`：与仓库旧版相同则跳过；不同则 `version + 1`。

### 11.2 索引版本化

- 全量重建 = **新 `index_version` → 完整 Smoke Test（文档数/chunk 覆盖/向量完整/样例可查）→ 原子切换 `rag_index_pointer`**，旧版本可随时回滚；
- 增量更新区分四种情况：新增 / 正文修改（替换 chunks）/ 仅元数据变化 / 删除或废止（`status='invalidated'`）；
- `embedding_model` 写入每个 chunk，**不跨模型混写**。

### 11.3 知识 MCP（8 个只读工具）

Agent **不直连** rag schema 与 OKF 仓库，一切知识访问经此服务：

`search_knowledge` · `get_document` · `get_responsibility` · `get_person_profile` · `get_process` · `find_related_knowledge` · `list_sources` · `knowledge_health`

- 调用**强制携带可信 `user_context`**，无则直接拒绝；
- 每次调用写 `mcp_call_logs`，同一 `trace_id` 串联；
- V1 传输形态是进程内直连（同接口，后续可换 stdio/HTTP）；
- `get_responsibility` 走"**责任文档确定性标题匹配优先 → 混合检索语义兜底**"两级；语义兜底带一道**防误伤闸** `_shared_token`：标题与查询名必须有实质词元重叠（CJK 2-gram 或拉丁词），否则不当作正式责任返回（如「堡垒机」不会关联到「大模型网关与API Key」）。

### 11.4 人员画像字段白名单（重要红线）

进 OKF/RAG：正式职责描述、负责领域叙述性正文、自我介绍正文、项目经历正文、他人评价聚合正文（低权重）。
**不进**：`raw_tags`、`person_tags`、动态 `concept_ids`、动态推断标签、Agent 内部权重。

---

## 十二、反馈回流与数据新鲜度

### 12.1 反馈回流

- **记录**：`POST /api/agui/events`（`value=up/down` 互斥可取消，DB 侧用**部分唯一索引**保证同用户同对象同消息只有一种反馈），落 `agent.feedback_events`；推荐结果落 `agent.agent_recommendation_logs`（问题摘要/候选/排序证据/运行标识）；
- **在线回流**：`PeopleRanker` 聚合人员反馈，`weight × (up-down)/(up+down+1)` 微调得分（`FEEDBACK_RANK_WEIGHT` 默认 0.1）。**只调整、不产生或消除候选**；
- **离线回流**：`scripts/export_feedback.py` 导出"推荐 × 反馈"JSONL，点踩案例自动入 `concept_review_queue` 供概念/别名治理复核。

### 12.2 数据新鲜度链路

```
业务变更（内容发布/修改/删除、人员资料或画像变更）
   │  backend 同事务写 rag.publish_events
   ▼
agent-service 事件消费者（10s 轮询，启动时把 failed 事件重入队一次防死循环）
   │  按事件类型增量重建对应 OKF 文档（每次发布一个版本）
   ▼
RagIndexer 按「文档 ID + 版本 + 内容哈希」幂等增量更新向量索引
   │  全量重建时：新版本 → 冒烟验证 → 原子切换指针（旧版本可回滚）
   ▼
检索立即可见（标签类变更经实时 SQL 视图天然即时生效，无需重建索引）
```

---

## 十三、可靠性与可观测性

### 13.1 分层降级（任何单点故障都有明确退化路径）

| 故障点 | 退化路径 |
|---|---|
| 意图 LLM 失败 | `RuleFallbackRouter` 规则路由，显式标 `degraded` |
| 要素抽取失败 | 保留词典显式匹配结果，不产生虚假概念 |
| 向量模型失败 | 关键词（FTS/pg_trgm）单路检索继续 |
| 知识 MCP 失败 | 结构化路径照常，标记 `mcp_search_knowledge` 降级源 |
| 正式责任 MCP 失败 | 降级 Mock 直读 Adapter，标记 `mock_responsibility_adapter` |
| 反馈服务故障 | 排序无调整，不阻断主链 |
| 缓存故障 | 直穿，不影响主链 |
| 索引未构建 | 抛 `RAG_ERROR(degraded=True)` |

降级状态**对用户可见**（回答尾部标注）、**对管理员可查**。

### 13.2 可观测性

每一轮问答**全链路留痕并持久化**：

- `agent_traces`（问句、用户、总耗时、是否降级）
- `agent_node_spans`（各节点耗时/状态/输入输出摘要/LLM tokens/工具调用）
- `query_concept_logs`（概念链接轨迹：词项 → 候选 → 确认）
- `mcp_call_logs`（知识服务调用日志）
- `agent_recommendation_logs`（推荐候选及排序证据）
- `rag_query_logs`（知识检索命中记录）
- `feedback_events`（用户反馈含点踩原因，与推荐运行记录关联）

管理员在「Agent 可观测」界面按时间/用户/问题检索任意一轮，逐节点展开。同时 `/metrics` 暴露 Prometheus 文本格式指标。

### 13.3 评测

- `run_v2_eval.py --split dev`（64 题）/ `--split test`（256 题）
- 数据集：`data/v2_eval_batch1~8.jsonl` + `v2_eval_test_batch01~05.jsonl`（144 行）+ `golden.json`
- **209 个测试用例**，覆盖：契约 / 编排 / 意图 / 结构化 / 概念链接 / 双路检索 / RAG 索引与检索 / MCP / 排序与闸门 / 权限过滤（匿名·认证·restricted）/ 动作卡片 / 反馈互斥与回流 / AGUI 事件形状 / 稳定性
- 前端另有浏览器冒烟测试（`npm run smoke`）：覆盖登录、问答推荐、会话空白复用、名片库、个人中心、草稿回填、跨用户非公开内容拦截、待审核新版继续展示旧公开快照

---

## 十四、数据模型速览

### 14.1 public schema（业务事实）

`departments` · `people` · `contents` · `peer_reviews` · `responsibility_assignments` · `users`（写侧事实源，触发器同步到 `people`）· `sessions` · `messages` · `query_logs`

### 14.2 agent schema（动态语义层 + 运行态）

| 分组 | 表 |
|---|---|
| 标签概念 | `raw_tags`、`person_tags`、`concepts`（含 `vector(512)`）、`concept_aliases`、`tag_concept_map`、`concept_relations`、`concept_review_queue` |
| 运行日志 | `query_concept_logs`、`agent_traces`、`agent_node_spans`、`agent_sessions`、`agent_recommendation_logs`、`mcp_call_logs`、`feedback_events`、`agui_messages` |

### 14.3 rag schema

`rag_documents` · `rag_chunks`（含 `vector(1536)` + embedding_model）· `rag_index_jobs` · `rag_index_pointer`（active_version 原子指针）· `rag_query_logs` · `publish_events`

**两个向量空间严格隔离**：Concept 512 维（bge-small-zh，Agent 内部空间）、RAG 1536 维（text-embedding-v4），**不跨空间比较**。

### 14.4 演示数据与账号

- V2 数据：**252 人 / 620 文 / 52 责任 / 38 概念** + 1536 维 RAG 索引（FpIM 现有 README 记录的线上口径为约 208 人 / 32 部门）
- 演示账号：任意工号 `P0001` … `P0252`，初始密码统一 `123456`

---

## 十五、当前完成度与已知边界

### 已完成（integration 分支四条子系统已合一棵树）

- ✅ 前端全部 8 类业务页面 + Agent 可观测界面，路由懒加载、Element Plus 按需注册
- ✅ 业务后端全部 API + JWT + RBAC + 审计日志 + 内容审核流 + 快照回退
- ✅ 智能服务全主链 + 双路检索 + 概念治理 + OKF 发布 + RAG 索引 + MCP + 反馈回流 + 评测
- ✅ 209 个测试通过；生产构建与浏览器冒烟通过

### 已知边界

1. **Embedding**：本地验证用 `EMBEDDING_PROVIDER=mock`（维度/链路真实，语义为词汇重叠）；生产填 `EMBEDDING_BASE_URL/KEY`（text-embedding-v4）后重建索引即可，**业务代码零改动**
2. **LLM**：配 DeepSeek key 即真实；`LLM_USE_MOCK=1` 可离线跑通链路
3. **内容/评价新写入**：backend 写入后需重跑 `publish_okf.py + build_rag_index.py` 才进入 RAG 知识（**增量发布为后续工作**，虽有 `publish_events` 消费者但存在此限制说明）
4. **身份**：Demo 用 `X-User-Id` 头适配器，生产需换 JWT 透传（接口不变）
5. 前端 `transport.js` 的 fetch 目前不带 `Authorization`，联调需补一行
6. agent-service 仍有少量 V1 数据集耦合测试在改造中（不影响运行链路）
7. 遗留实现边界：工单办理、责任事项台账、跨部门转办、催办升级、内容分级可见、数据导出等均**不在当前范围**

---

## 十六、对本项目（FpIM IM 化重构）的意义

结合本工作目录已有的调研（`README.md` / `proposal.md` / 四份 IM 选型报告），findperson 作为"核心内核"的可复用度可以这样切分：

### 16.1 可直接复用（几乎不用改）

| 资产 | 说明 |
|---|---|
| **智能问答主链**（agent-service 全量） | 意图 → 结构化 → 概念链接 → 双路检索 → 排序 → 置信门 → 回答，8,100 行 + 209 测试，是最大的一块资产 |
| **标签三层模型 + 概念治理** | 组织级语义中枢，与业务无关，换任何上层 UI 都成立 |
| **AGUI 接入层 + SSE 事件契约** | 前端已对齐；IM 化后「搜人入口」可继续用它 |
| **组织树 / 人员名录 / 部门职责 / 上级关系** | 通讯录与个人主页的直接数据源 |
| **推荐卡片 + 推荐理由机制** | 已有"命中依据"可解释性，IM 中"AI 名片上发消息"只需加一个跳转 |
| **可观测性与 Trace** | 全链路留痕已落库，IM 化后做"提问价值/部门被问排行"统计时是现成数据源 |
| **双 schema 隔离 + publish_events 事件链路** | 消息与问题状态若也落在 PG，可复用同一套增量索引机制 |

### 16.2 需要改造

| 现有形态 | IM 化改造方向 |
|---|---|
| `sessions` / `messages`（问答会话，public schema） | 与 IM 单聊会话体系合并或映射；问答会话可作为 IM 中"与 AI 的会话" |
| 个人中心 `/mine` + 人员主页 `/profile/:id` | 合并为「个人主页」（对标飞书个人名片页），支持主页间互跳 + 上级标注 |
| 内容发布/审核/详情 | 是否需要保留内容社区形态取决于产品取舍；若保留，可作为"经验沉淀"入口 |
| 反馈（`up/down` 互斥） | 扩展为"问题解决状态"（待响应/处理中/已解决/未解决）的证据来源 |
| `me` 的可维护字段（仅联系方式/负责领域/自画像） | IM 化后可能需要头像、签名档等，属于同一白名单机制的扩展 |

### 16.3 需要新增（findperson 里没有的）

- **IM 核心**：WebSocket 长连接、消息可靠性（ACK / 重发 / 幂等 / 断线重连 / 离线消息）、已读回执、历史漫游、文件与图片
- **问题闭环状态机**：会话关联问题、催办、超时曝光（`proposal.md` 提到现有 issues 五表后端已就绪、前端被隐藏，正好启用）
- **统计报表**：提问量排行、提问价值（反馈 + 解决率）、部门被问排行、解决成果，生成报告
- **HR 联动**：画像/排名数据对接人力资源系统

### 16.4 三条需要特别留意的既有约定

1. **写入边界不能破**：findperson 严格规定「智能层只读、只推理、只产草稿，一切业务写入必经业务层」。IM 化后消息写入是高频写路径，如果 AI 侧也要产出结构化结果（如自动生成问题卡），仍应遵守"AI 产草稿 → 确认落库"的模式，不要开直写口子。
2. **降级是设计的一部分**：新链路（WebSocket / 报表 / 催办）也应补上对应的降级路径，与现有分层降级风格一致。
3. **两个向量空间不要合并**：Concept 512 维与 RAG 1536 维是刻意分离的（概念对齐用内部空间、知识检索用外部空间），合并会引入跨空间比较的语义噪声。

---

## 附：建议的后续阅读路径

如果要把这个仓库吃透，建议按此顺序（它的 30 份模块文档是最好的入口）：

1. `docs/首问必答平台-架构设计说明.md` — 全局设计意图（8 节 + 关键决策摘要表）
2. `agent-service/docs/modules/10-AgentOrchestrator.md` → `11-意图识别与RuleFallbackRouter.md` → `12-QueryStructurer.md` → `13-ConceptLinker前三级与PCE.md` → `15-Merger Ranker与ConfidenceGate.md` → `16-AnswerBuilder与SSE全链路.md` — 主链一条线
3. `agent-service/docs/modules/17-六级召回补齐.md` → `18-LLM受约束消歧与Concept治理.md` — 概念层
4. `agent-service/docs/modules/19-OKF Publisher.md` → `23-RAG Indexer.md` → `24-Hybrid Retriever与Knowledge QA.md` → `25-Knowledge MCP.md` → `26-双路召回全链路.md` — 知识链路
5. `agent-service/docs/modules/27-Trace落库与指标监控.md` → `28-自动评测体系.md` → `29-稳定性.md` — 质量保障
6. `首问责任平台功能详细说明v4.md` — 产品口径与验收场景（14 节）
7. `INTEGRATION.md` — 三进程启动与联调验证清单
