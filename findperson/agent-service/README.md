# 首问责任平台 Agent 服务(agent-service)

本目录是首问责任平台的 **Agent 服务**:编排主链(意图 → 问题结构化 → 概念链接 →
双路检索 → 候选融合 → 排序 → 置信度门 → 回答)+ AGUI 前端接入层 + 知识 MCP +
RAG 索引/检索 + 用户反馈回流。与仓库其他分支的关系:

```text
前端 (main 分支 Vue3+AGUI) ──► 本服务 /api/agui/*(SSE 事件流)
业务后端 (backend 分支)    ──► 业务 CRUD/鉴权(本服务不替代;确认卡片动作由前端调后端执行)
知识规范 (okf-rag-mcp 分支) ──► OKF frontmatter 校验/切片/权限模型,本服务对齐其实现
数据库 (database 分支)      ──► public 业务表 + 本服务增量 agent.*/rag.*(scripts/ddl)
```

## 关键决策(已拍板)

| 决策点 | 结论 |
|---|---|
| RAG 向量维度 | **1536**,生产用 text-embedding-v4(OpenAI 兼容),与 knowledge-service 对齐 |
| Concept 向量 | 512(bge-small-zh),Agent 内部空间,不与 RAG 跨空间比较 |
| confirmation 动作 | 资料维护 / 他人画像 / 内容发布三类全做,Agent 只产草稿,确认写执行走业务后端 |
| MCP | 真实化:进程内 `KnowledgeMcpServer`(8 个只读工具契约),Agent 经 `KnowledgeMcpClient` 调用 |
| 反馈回流 | 互斥反馈落库 + 排序在线微调(±0.1)+ 离线导出治理队列 |

## 快速开始

```powershell
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt fastembed
copy .env.example .env   # 填入 LLM_API_KEY / PGPASSWORD;生产再填 EMBEDDING_BASE_URL/KEY
.\venv\Scripts\python scripts\init_db.py            # 建库 shouwenzeren_agent + DDL
.\venv\Scripts\python scripts\import_v2_data.py     # 导入 V2 数据(252 人/620 文/38 概念)
.\venv\Scripts\python scripts\publish_okf.py        # 业务事实 → OKF
.\venv\Scripts\python scripts\build_rag_index.py    # OKF → 1536 维 RAG 索引
.\venv\Scripts\python scripts\backfill_concept_embeddings.py
.\venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8100
```

本地离线链路验证(EMBEDDING_PROVIDER=mock、LLM_USE_MOCK=1)无需任何外部密钥;
生产把 `EMBEDDING_PROVIDER=openai_compatible` 并注入 `EMBEDDING_BASE_URL/EMBEDDING_API_KEY`
后重建索引即可,业务代码零改动。

## 对外接口

### AGUI(前端对接面,与 src/services/agui/* 对齐)

| 端点 | 说明 |
|---|---|
| `POST /api/agui/sessions` | 创建会话 |
| `GET /api/agui/sessions/{id}/state` | 会话状态(历史消息与卡片) |
| `POST /api/agui/sessions/{id}/messages` | 发送消息,SSE 事件流 |
| `POST /api/agui/events` | 交互/反馈上报(value=up/down 为互斥反馈) |

SSE 事件(单行 JSON,`type` 在 data 内):`run_started`(带 result.analysis)→
`text_delta`×N → `text_finished` → `recommendation_cards` 或 `confirmation_card` →
`state_delta` → `run_finished`;异常时 `run_error`。

### 文档兼容端点(实施方案v3 §3.2)

| 端点 | 说明 |
|---|---|
| `POST /agent/chat` | Agent 对话(SSE,X-User-Id 头) |
| `POST /agent/feedback` | 提交带 trace_id 的推荐反馈 |
| `GET /agent/feedback/reasons` | 点踩原因配置 |
| `GET /health` / `GET /metrics` | 健康检查 / Prometheus 指标 |

### 身份

Demo 适配器:`X-User-Id` 头(或 AGUI 请求体 `context.userId`)→ `public.people` 校验,
客户端自报角色/部门不作数。正式环境由网关/JWT 替换,接口不变。

**前端接入注意**:`src/services/agui/transport.js` 的 `fetch` 目前不带 Authorization,
联调时需补一行从 localStorage 取 token 放入 header(前端侧改动);
`VITE_AGUI_MODE=server`、`VITE_AGUI_BASE_URL` 指向本服务。

## 反馈回流

- **记录**:`POST /api/agui/events`(value=up/down 互斥可取消;其余为交互事件),
  落 `agent.feedback_events`(带 session/message/trace);推荐结果落
  `agent.agent_recommendation_logs`(问题摘要/候选/排序证据/运行标识)。
- **在线回流**:PeopleRanker 聚合人员反馈,`weight × (up-down)/(up+down+1)`
  微调得分(`FEEDBACK_RANK_WEIGHT`,默认 0.1;只调整不产生/消除候选)。
- **离线回流**:`scripts/export_feedback.py` 导出推荐×反馈 JSONL,点踩案例
  自动入 `agent.concept_review_queue` 供概念/别名治理复核。

## 测试

```powershell
.\venv\Scripts\python -m pytest tests -q
```

覆盖:契约/编排/意图/结构化/概念链接/双路检索/RAG 索引与检索/MCP/排序与闸门/
权限过滤(匿名/认证/restricted)/动作卡片/反馈互斥与回流/AGUI 事件形状。

## 评测

```powershell
.\venv\Scripts\python scripts\run_v2_eval.py --split dev        # 64 题
.\venv\Scripts\python scripts\run_v2_eval.py --split test       # 256 题
```

## 目录

```text
app/
├── agent/          # 编排主链(orchestrator/intent/structurer/concept_linker/ranker/answer_builder/action_drafts)
├── agui/           # AGUI 接入层(SSE 事件流/会话/消息持久化/推荐日志)
├── contracts/      # 公开契约(AgentState/MCP/证据/错误/trace)
├── core/           # config/db/llm/embedding/cache/observability
├── feedback/       # 反馈记录与回流
├── mcp_knowledge/  # 知识 MCP Server(8 工具)与类型化 Client
├── okf/            # OKF 生成/校验/发布
├── rag/            # 切片/索引/混合检索(FTS+pgvector+RRF,权限过滤)
├── retrieval/      # 结构化检索(名录/标签匹配/正式责任)
└── eval/           # 评测
scripts/            # 建库/导入/发布/索引/评测/反馈导出
scripts/ddl/        # 01_public / 02_agent / 03_rag / 04_agent_views
tests/              # 单元与链路测试
```
