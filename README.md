# FpIM —— 首问责任平台的 IM 化重构

> 把「找到人」延长到「**解决问题并留下证据**」。
> 现有平台在"AI 找到责任人"之后就断了——沟通靠邮件往来，过程丢失。本项目把这段换成 IM，让处理全程留痕、可统计、可进人才选拔。

## 这是什么

原平台（`findperson`/首问责任平台）已经能做：自然语言提问 → AI 找人 / 找知识 → 指派责任人 → 跟进问题。
**本项目的重构点只有一个：把沟通渠道从邮件换成 IM，并让沟通行为自动沉淀成证据。**

- 不是新建问题闭环——`issues` / `issue_events` / 知识沉淀这套**本来就在跑**，本项目是**换渠道 + 补留痕**。
- 差异化不在聊天本身，而在聊天之外：**状态机、留痕、统计、画像**。所以没有直接采用开源 IM，而是自研内核（消息必须与问题同库同事务，否则报表数字和聊天记录必然对不上）。

## 当前进度

| 模块 | 状态 |
|---|---|
| IM 数据层（`im` schema） | ✅ 已完成 |
| IM 后端内核（13 REST + WebSocket） | ✅ 已完成，自测 HTTP 37 项 + WS 13 项 |
| IM 前端（飞书风三栏会话页） | ✅ 已完成 |
| 问题闭环（会话内立项 + 自动留痕） | ✅ 已通（立项 → 挂接 → 已读/首响 → 解决确认 → 沉淀候选）；报表未做 |
| 「待办」视图（待我处理 / 我提出的） | ✅ 已完成（侧栏红点 + 进入会话跳转） |
| 通讯录 / 个人主页（数据画像） | 🚧 画像已通，物理合并未做 |
| 小管家 / 报表看板 / 桌面壳 | ⏸ 未开始 |

完整索引与变更日志见 **[docs/PROJECT.md](docs/PROJECT.md)**。

## 怎么跑起来

```bash
./start-dev.sh        # 拉起后端(8002)+前端(5175)，已起则跳过
./start-dev.sh stop   # 停掉
```

然后打开 **http://127.0.0.1:5175**（账号 P0004~P0007，密码见 `findperson/backend/.env` 的 `SEED_PASSWORD`）。
日志在 `.workbuddy/logs/`；前提：PostgreSQL 容器（swzr-pg:5432）在跑。

## 目录结构

```
FpIM/
├── README.md               ← 本文件
├── docs/                   ← 全部文档
│   ├── PROJECT.md          ★ 主文档，接手先读这个
│   ├── 01-产品需求文档-PRD.md
│   ├── 02-技术方案文档.md
│   ├── 03-前端设计文档.md
│   ├── 重构方案-IM化与问题闭环.md
│   ├── modules/            ← 模块文档（数据库/后端/前端/问题闭环/开发环境）
│   └── research/           ← 前期调研与原始方案（归档）
├── prototype/              ← 高保真原型（fpim-mockup.html）+ 界面截图
├── findperson/             ← 代码
└── .workbuddy/memory/      ← 项目记忆（决策、踩坑）
```

## 技术栈

| | |
|---|---|
| 前端 | Vue 3.5 + Vite 6 + Pinia + Element Plus 2.10 |
| 后端 | FastAPI + SQLAlchemy 2 + psycopg2；`uvicorn[standard]`（自带 websockets） |
| 数据库 | PostgreSQL + pgvector（Docker 容器 `swzr-pg`） |
| 智能内核 | 独立 `agent-service`（:8100，**只读、只推理、只产草稿**，不写业务表） |

## 本地跑起来

开发环境**独立于**原有的 8001 实例，用单独的库和端口，互不干扰。

```bash
# 1) 后端（8002，指向独立开发库 fpim_dev）
#    口令不入库：从 backend/.env 读取（.env.example 是模板）
cd findperson/backend
DATABASE_URL="postgresql://swzr_admin@localhost:5432/fpim_dev" \
  PGPASSWORD="<数据库口令，见 backend/.env>" \
  FPIM_FILE_ROOT=/tmp/fpim-files \
  CORS_ORIGINS="http://localhost:5173,http://localhost:5174,http://localhost:5175" \
  venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8002

# 2) 前端（5175，--mode fpim 读 .env.fpim 把 API 指向 8002）
cd findperson
node node_modules/vite/bin/vite.js --mode fpim --port 5175 --host 127.0.0.1 --strictPort
```

浏览器打开 <http://127.0.0.1:5175>，用 `P0004` + 种子账号口令（见 `backend/.env` 的 `SEED_PASSWORD`）登录，左侧「消息」即是会话页。

### 自测

```bash
cd findperson/backend
venv/bin/python scripts/fpim_smoke_http.py --reset   # 19 项，--reset 会清空 im 数据
venv/bin/python scripts/fpim_smoke_ws.py             # 13 项
```

完整环境说明（端口分配、依赖重建、已知坑）见 **[docs/modules/dev-environment.md](docs/modules/dev-environment.md)**。

## 两条必须遵守的约定

1. **业务写入只能走 backend**。`agent-service` 只读只推理，IM 这种高频写路径也不许绕过。
2. **消息与问题必须同库同事务**。这是自研 IM 的唯一决定性理由——报表、闭环、人才画像全是 SQL 聚合。

## 凭据约定（重要）

**仓库内不含任何明文凭据。** 所有口令、密钥、API Key 都从 `.env` 注入，而 `.env` 已被 `.gitignore` 排除。

| 变量 | 用途 | 模板位置 |
|---|---|---|
| `DATABASE_URL` / `PGPASSWORD` | 数据库连接与口令 | `findperson/backend/.env.example` |
| `JWT_SECRET` | 登录令牌签名密钥（生成：`openssl rand -hex 32`） | 同上 |
| `SEED_PASSWORD` | 种子账号统一登录口令（测试与自测脚本用） | 同上 |
| `DB_PASSWORD` | `docker compose` 建 PG 容器 | `findperson/.env.example` |
| `VITE_DEMO_PASSWORD` | 登录页「快捷登录」演示口令（不设置则不显示） | 同上 |

首次搭建：把各处的 `.env.example` 复制为 `.env` 并填入真实值。若某个变量缺失，相关组件会**明确报错提示**（而不是静默用默认口令连库）。

> 说明：`.env.example` 里只放 `CHANGE_ME` 之类的占位符。**新增配置项时请不要把真实值写进 `.example`。**

## 其他说明

- `docs/` 与本文档中的路径均相对 `docs/`；代码内部相对路径以 `findperson/` 为根。
- `findperson/` 内的 `README.md`（根与 `backend/`）是原项目遗留文档，部分内容已过时，以 `docs/` 为准。
