# FpIM 项目长期记忆

> 跨会话需要长期生效的硬约定与事实。日常流水记在 `YYYY-MM-DD.md`，这里只放"不知道就会犯错"的东西。

## 🔴 项目位置（2026-09-17 起：代码是本目录内的独立副本）

```
~/projects/mine/FpIM/          ← 项目根 = git 仓库根（文档 + 原型 + 代码一起版本化）
├── README.md                  ← 项目入口（怎么跑起来）
├── docs/                      ← 全部文档
│   ├── PROJECT.md             ★ 主文档，接手先读它
│   ├── 01-产品需求文档-PRD.md / 02-技术方案文档.md / 03-前端设计文档.md
│   ├── 重构方案-IM化与问题闭环.md
│   ├── modules/               ← 模块文档
│   └── research/              ← 前期调研与原始方案（归档，不再维护）
├── prototype/                 ← 原型 + 截图
├── findperson/                ← 代码（前端 src/ + backend/ + agent-service/）
└── .workbuddy/memory/         ← 项目记忆（已入库）

~/projects/mine/findperson/    ← 原项目：已不再使用、不再维护
```

- 决策链：原 Q1=A 是"直接在原仓库演进"，用户 2026-09-17 改为"**复制一份**"（两个独立项目不该合到一起）；随后又要求**仓库提到 `FpIM/` 根，文档与代码一起版本化**（首次提交 `e505fd8`，1218 文件）。
- 复制时**排除了 `venv`**（`bin/pip` 的 shebang 硬编码旧路径 → 复制后会静默装回旧项目）与 `.git`；保留源码/配置/`node_modules`/数据脚本。
- 代码内部相对路径以 `findperson/` 为根；`docs/` 里的路径相对 `docs/`。

## 🔴 铁律：仓库内不得出现任何明文凭据

分工明确：**`.env` 存值（不入库），`.env.example` 只放 `CHANGE_ME` 占位符，代码从环境变量读。**

| 变量 | 放哪 | 用途 |
|---|---|---|
| `DATABASE_URL` / `PGPASSWORD` | `findperson/backend/.env` | 数据库（DSN 不带口令，走 `PGPASSWORD`） |
| `JWT_SECRET` | 同上 | 登录令牌签名（`openssl rand -hex 32`） |
| `SEED_PASSWORD` | 同上 | 种子账号口令（conftest 与自测脚本读） |
| `DB_PASSWORD` | `findperson/.env` · `findperson/database/.env` | `docker compose` 建 PG |
| `VITE_DEMO_PASSWORD` | `findperson/.env.fpim.local` | 登录页快捷登录，**仅开发模式** |

- ⚠️ **前端口令藏不住**：`VITE_*` 会被 Vite 在构建期内联进 JS bundle。放 `.env.fpim.local`（Vite 的 `.local` 约定，仅 `--mode fpim` 加载）**并且**用 `import.meta.env.DEV` 兜一层。
- ⚠️ **`ripgrep` 默认跳过隐藏文件**：用它做敏感扫描会漏掉 `.workbuddy/`。扫凭据用 `grep -rnE`（含隐藏）。
- ⚠️ **新增配置项时，绝不把真实值写进 `.env.example`**——原项目就犯过（`.env.example` 里的 `JWT_SECRET` 与真实密钥同值）。

## 🔴 铁律：核对代码事实必须以「本机工作副本」为准

- 历史事实的原始来源在 **`~/projects/mine/findperson`**（**不是** GitHub 公开仓库）。
- GitHub 上的 `taiyuexiao/findperson` **落后一大截**，且大量关键文件从未推送（在原仓库 git 里是未跟踪 `??` 状态）。
- **2026-09-17 已因此犯过一次大错**：只读 GitHub 就断言"问题闭环不存在"，并错误地给 Kimi 的方案写了"勘误"；实际上 `issues` 五表等全已实现。
- 核对任何"仓库里有没有 X"之前，**先看本机工作副本 + `git status`**。现在看 `FpIM/findperson/`（开发基线），追溯看原 `findperson/`。

## 项目是什么

- **FpIM = 把 findperson（首问责任平台）从"找到人"延长到"解决问题并留痕"的 IM 化重构。**
- 重构本质：**把已建成的「邮件闭环」换成「IM 闭环」**，而不是新建问题闭环。
- 用户/领导的核心诉求：制造麻烦倒逼解决 · 过程即数据 · 画像进 HR 链路。

## 已存在、不要重做的资产（findperson 本机副本）

- 五表：`issues` / `issue_events` / `mail_messages` / `knowledge_candidates` / `faqs`（模型 `backend/app/models/issue.py`）
- DDL：`agent-service/scripts/ddl/07_issues_knowledge.sql`
- 接口：`backend/app/api/v1/issues.py`、`backend/app/api/v1/mail.py`
- 设计稿：`docs/问题闭环与知识库设计.md`
- 前端：`src/stores/issues.js`、`src/services/api/{issues,mail}.js`、`src/views/KnowledgeView.vue`
- "前端被隐藏" = `AppSidebar.vue` 里 `knowledge` 那行被注释掉（路由仍在）
- ⚠️ `MailDialog.vue` **已被本重构逻辑废除**（所有引用已解除，但文件与 `mail_messages` 历史保留作证据），不要再把它接回去

## 环境事实

- 本机跑着：PG(Docker:5432) / backend:8001 / agent-service:8100
- PG：容器 `pgvector/pgvector:pg17`，库 `shouwenzeren_newdb`；`database/seed.sql` 是 208 人真实名片库 + 2250 RAG 向量块
- **本机没有 `psql`**；`docker` CLI 有 API 版本不兼容报错 → 连库走 `docker exec swzr-pg psql` 或 Python 驱动
- 工作区长期脏（1700+ 未提交项），动手前先确认基线

### FpIM 独立开发环境（已建好，直接用，勿碰 8001 环境）

- **代码根**：`~/projects/mine/FpIM/findperson/`（下文所有相对路径都相对它）
- 开发库 **`fpim_dev`**（从 `shouwenzeren_newdb` 1:1 复制，208 人 + 8487 RAG 块齐全）
  DSN：`postgresql://swzr_admin@localhost:5432/fpim_dev`（**口令不入库**，由 `PGPASSWORD` 提供，见 `findperson/backend/.env`）
- 端口：**8002** = FpIM backend ｜ **5175** = FpIM 前端（`vite --mode fpim` 读 `.env.fpim`）
- 测试账号：`P0004`~`P0007`，口令统一（**不入库**，见 `findperson/backend/.env` 的 `SEED_PASSWORD`）
- **backend venv 已重建**：`backend/venv`（uv + CPython **3.12.14**，与原环境同版本）
- 验证：`cd /Users/shipeilin/projects/mine/FpIM/findperson/backend && venv/bin/python scripts/fpim_smoke_http.py --reset`（19 项）+ `scripts/fpim_smoke_ws.py`（13 项）
- ⚠️ `backend/venv` **没装 pytest/httpx**，既有 `backend/tests/` 跑不了
- ⚠️ 起开发服务必须用**后台常驻**方式；同一条命令 `nohup ... &` 后返回，进程会被回收
- ⚠️ 换前端端口必须同步加进后端的 `CORS_ORIGINS`，否则跨域失败
- ⚠️ 沙箱注入 `HTTP_PROXY`：本地回环请求要绕过（脚本用 `ProxyHandler({})`，curl 用 `--noproxy '*'`）
- ⚠️ **不要把 `venv` 目录复制/移动**：`bin/pip` 的 shebang 硬编码绝对路径，复制后会静默装回旧项目。`node_modules` 可以复制（只需清 `node_modules/.vite`）

## 用户偏好（沟通）

- 对 OA/政务行话不熟（"催办"就不认识）→ 用大白话；涉及"要别人配合/要资源"的事项，连问题本身一起解释清楚，最好给可直接照抄的提问清单。
- 决策风格偏**轻量、偏快**：倾向先砍掉复杂机制上线跑，而不是一次做全。给"最小可用版 + 可低成本恢复的退路"命中率最高。
- 对 UI 的判断靠**直接对比参照物**；给视觉方案前先拿真实截图拆解特征。
- 阅读外部代码时不要在项目目录留中间产物（临时克隆放 `/tmp`）。

## 已锁定的关键决策（勿改回）

- IM 内核：**自研 FastAPI WebSocket**（理由：报表/闭环全是 SQL 聚合，消息必须与 issue 同库同事务）
- 责任留痕：**只做已读/未读**，不做超时/延期/升级（可逆——`first_read_at` 从上线起就在积累）
- 统计：全员公开，但只公开**正向榜 + 知识缺口地图**，不公开个人拖延明细
- PC 端：**Electron 独立桌面壳**；文件存**本地磁盘**（内容寻址）；推送走 IM 内的**「小管家」**系统号
- 群聊：首期做，单群上限 **100 人**
- HR 联动、中文分词扩展装 DB：**本次范围外 / 不阻塞开工**
- UI：**照飞书 7.x 抄**，主色 `#3370FF`；四个视觉基因 = 白底为主 / 0.5px 极轻分隔 / 四级灰分层 / 大留白小圆角。禁 `box-shadow`、1px 边框、纯黑正文、20px+ 圆角
- **代码基线：`~/projects/mine/FpIM/findperson/`（独立副本，已 git init）**；原 `~/projects/mine/findperson` 保持独立不再改动
- **UI 路线：沿用 Element Plus + 主题层飞书化**（不引 Arco、不纯自建）；IM 专属组件自研

## 代码事实（已落地，勿重复实现）

> 以下路径均相对 `FpIM/findperson/`。

- `im` schema：`agent-service/scripts/ddl/08_im.sql` —— `conversations` / `conversation_members` / `messages` / `attachments` + 4 个唯一索引；`issues` 扩展 `conversation_id` / `first_read_at` / `first_response_at`
- 后端：`backend/app/models/im.py` · `services/im.py`（REST 与 WS **共用同一服务层**）· `api/v1/im.py`（12 REST）· `ws/im_gateway.py`（端点 `/api/v1/ws/im?token=`）
- 前端：`src/views/ChatView.vue` · `src/components/im/*` · `src/stores/im.js` · `src/services/im/{socket,format}.js` · `src/styles/im.css`（设计令牌）
- 入口：侧栏「消息」· 路由 `/chat` · 长连接挂 `MainLayout`（不在会话页）
- **关键实现约束**：消息幂等靠唯一索引 `uq_msg_client_idem`（`sender_id + client_msg_id`）；`clientMsgId` **必须由调用方生成**，socket 内部不许自己造；查消息的 SQL **列清单必须与 `_msg_dict_from_row` 对齐**
- **已读有两处，语义不同不能混用**：会话侧 `last_read_seq`（可覆盖，供红点）vs 问题侧 `issue_events.read` + `issues.first_read_at`（永不覆盖，作证据）
- `resolved` **只能提问方确认**（后端 `update_issue` 硬校验 `issue.user_id`）
- **会话内立项**（2026-09-17 已落地）：`POST /im/conversations/{cid}/issues`（单聊默认对方、群聊必须指定）；立项后 `send_message` 自动挂接活跃问题（status=processing，解决后不再挂）；解决/未解决 → `resolve_confirm` 系统消息（`sender_id='system'`）+ 广播
- **「待办」视图**：`GET /issues/assigned` + `TodoView.vue`（/todo）+ 侧栏红点（30s 轮询）
- **系统消息约定**：`sender_id='system'`，只允许 system/resolve_confirm/report_card 类型
- ⚠️ **DDL 加列必须同步 ORM 模型**（08_im.sql 加的 3 列没进 `models/issue.py`，update_issue 曾因此 500）

## 🔴 平台既有事实（双用户表）

- **`public.user2` 是当前用户主表**（登录/注册/ORM 都走它）；**`public.users` 是老表**，但 `contents.owner_id` / `peer_reviews.reviewer_id` 的外键仍指向它。种子用户两表都有（208 人）；`/auth/register` 新建的只在 user2。
- `audit_logs.user_id` 的 FK 已对齐到 user2（`09_fix_audit_fk.sql`）；`contents` / `peer_reviews` 的 FK 迁移是待办。
- 测试基建：`backend/venv` 已装 pytest+httpx；`pytest tests/` 42/42 全过（须指向 fpim_dev）。跑法见 docs/modules/platform-hardening.md。
- 改密链路本轮从 stub 补全（后端真校验旧密码 + 前端真调接口）。

## 文档地图（本项目目录）

- **`README.md`** —— 项目入口（是什么 / 进度 / 怎么跑 / 约定）
- **`docs/PROJECT.md`** —— 项目主文档（模块索引 / 变更日志 / 已锁定决策 / 待处理），**接手先读它**
- `docs/modules/` —— 模块文档：`im-database` / `im-backend` / `im-frontend` / `issue-loop` / `dev-environment` / `platform-hardening`（平台既有缺陷修复记录）
- `docs/01-产品需求文档-PRD.md` / `docs/02-技术方案文档.md` / `docs/03-前端设计文档.md`（§12 是飞书还原规格）
- `docs/重构方案-IM化与问题闭环.md`（**开头有「🛑 重大修订」块，先读它**）
- `docs/research/` —— 归档：`findperson项目概要总结.md` / `proposal.md`（§六 是勘误与撤回）/ `research-*.md` / `调研总论与选型结论.md`
- `prototype/fpim-mockup.html` + `prototype/screens/*.png`

> 目录已于 2026-09-17 规范化：所有文档归入 `docs/`，前期调研归档到 `docs/research/`，根目录只留 `README.md`。

## 环境坑（会重复踩，记牢）

- **开发服务不保证长期存活**：中间跑了重活（git 大批量操作、大目录复制）后进程可能被回收，表现为端口空出、curl 返回 `000`。**开工前先探活，别假设还在。**
- **`venv` 不可复制/搬迁**：`bin/pip` 的 shebang 硬编码绝对路径，复制后会静默装回旧项目 → 换位置必须重建 venv。`node_modules` 可以复制（清 `.vite` 即可）。
- 仓库里**有两个完全重复的 16M `seed.sql`**（`findperson/scripts/` 与 `findperson/database/scripts/`，md5 相同、无代码引用），占体积 71%。

## 当前最大缺口（下一步优先）

**「在会话里立项」交互缺失**：目前只有「从问题进入会话」才带上 `issue_id`，普通聊天不会自动关联问题 → `_touch_issue_on_message` 不被触发，"过程即数据"落不了地。这是最该补的一环。
