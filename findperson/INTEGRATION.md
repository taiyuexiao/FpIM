# Integration 分支联调指南

本分支把四个子系统放在同一棵树:**前端(根目录)+ backend/ + agent-service/ + database/**。
前端 UI 零改动,仅通过根目录 `.env` 指向两个后端服务。

## 拓扑

```
浏览器(前端 Vite, :5173)
  ├── 业务 API  VITE_API_BASE_URL  → backend(:8001, /api/v1/*)        人员/部门/内容/评价/会话/登录
  └── 问答 SSE  VITE_AGUI_BASE_URL → agent-service(:8100, /api/agui/*) 意图/检索/排序/推荐卡/确认卡
                    ▲                         │
                    └── backend 代理 /api/v1/agui/events ──────────────┘  (反馈事件转发)
                                      │
                PostgreSQL shouwenzeren_agent(public+agent+rag 三 schema)
```

- 统一库 `shouwenzeren_agent`:V2 数据(252 人/620 文/52 责任/38 概念)+ 1536 维 RAG 索引。
- `users` 为写侧事实源(backend 维护);`people` 由触发器实时同步(Agent 只读)。
- 演示账号:任意工号 `P0001`…`P0252`,初始密码统一 `123456`。

## 启动(三个进程)

```powershell
# 0) 一次性:建库 + 数据 + 索引 + backend 兼容层
cd agent-service
.\venv\Scripts\python scripts\init_db.py
.\venv\Scripts\python scripts\import_v2_data.py
.\venv\Scripts\python scripts\publish_okf.py
.\venv\Scripts\python scripts\build_rag_index.py
.\venv\Scripts\python scripts\backfill_concept_embeddings.py
.\venv\Scripts\python scripts\align_backend_schema.py   # users/sessions/contents 兼容层 + 初始密码

# 1) agent-service(:8100)
cd agent-service; .\venv\Scripts\python -m uvicorn app.main:app --port 8100

# 2) backend(:8001,8000 如空闲亦可)
cd backend; <venv>\python -m uvicorn app.main:app --port 8001

# 3) 前端(:5173)
copy .env.example .env
npm install; npm run dev
```

## 对接说明(前端零 UI 改动)

- AGUI 身份走请求体 `context.userId`(Demo 适配器,服务端按库校验);生产换 JWT 透传。
- 反馈/交互事件:前端 reporter 走业务通道 `POST /api/v1/agui/events`,由 backend 代理转发到
  agent-service(agent-service 不可用时优雅降级,前端仅 console.warn)。
- 推荐卡片含完整 person 对象与命中依据;人 ID 与 backend 名录一致(`p-0001` 系列),
  「查看主页」可直接跳转。
- 确认卡(资料/画像/发布)由 Agent 产草稿,确认后前端调 backend 写 API 执行,
  users 变更经触发器同步到 people,Agent 侧立即可见。

## 验证清单(已通过的项)

- [x] backend 登录 `POST /api/v1/auth/login`(P0001/123456)
- [x] `GET /api/v1/people`、`/people/{id}`、`/departments/tree`(含领域标签)
- [x] AGUI 会话 + SSE 全事件序列:run_started(analysis) → text_delta → text_finished
      → recommendation_cards(首推/可协助/相关人员,带命中依据) → state_delta → run_finished
- [x] 反馈互斥:直连 `POST /api/agui/events` 记录 → 经 backend 代理重复同值自动取消
- [x] 写操作确认卡(profile/review/content 三类,卡片含 draftId/submitTarget)

## 已知边界

1. **Embedding**:本地验证用 `EMBEDDING_PROVIDER=mock`(维度/链路真实,语义为词汇重叠)。
   生产填 `EMBEDDING_BASE_URL/EMBEDDING_API_KEY`(text-embedding-v4,1536 维)后重建索引即可。
2. **LLM**:`.env` 配 DeepSeek key 即真实;`LLM_USE_MOCK=1` 可离线跑通链路。
3. **内容/评价新写入**:backend 写入 contents/peer_reviews 后,需重跑
   `publish_okf.py + build_rag_index.py` 才进入 RAG 知识(增量发布为后续工作)。
4. agent-service 仍有少量 V1 数据集耦合测试在改造中(不影响运行链路)。
