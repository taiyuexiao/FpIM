# FpIM 项目总览

> 项目文档入口：先读这里，再按需读 `modules/` 下的模块文档。更新纪律：每完成一个模块或处理一个变更，当轮更新「变更日志」和受影响的索引条目。**控制在 ~100 行内，细节一律下沉到模块文档。**
> 怎么跑起来、目录结构、凭据约定见仓库根 `README.md`。

## 一句话说明

把 findperson（首问责任平台）从「**找到人**」延长到「**解决问题并留下证据**」——给已有的 AI 搜人 + 问题跟踪链路换上 IM 这个沟通壳，让处理过程全程留痕、可统计、可进人才选拔。

## 技术栈与关键约定

| | |
|---|---|
| 代码 | `findperson/`（自原仓库复制出的独立副本；仓库根即项目根，文档与代码一起版本化） |
| 前端 | Vue 3.5 + Vite 6 + Pinia + Element Plus 2.10 |
| 后端 | FastAPI + SQLAlchemy 2 + psycopg2；`uvicorn[standard]`（自带 websockets） |
| 数据库 | PG（Docker `swzr-pg`）；原库 `shouwenzeren_newdb`，开发库 **`fpim_dev`** |
| 智能内核 | `agent-service`（:8100，**只读只推理只产草稿**，业务写入必经 backend） |

**不可协商的约束**（违反会破坏既定架构）

1. 业务写入必经业务层；`agent-service` 只读只推理。
2. **消息与问题必须同库同事务**——报表/画像全是 SQL 聚合，分库必然出现"报表数字 ≠ 聊天记录"。
3. 分层降级是设计的一部分（WS 不可用走 HTTP 兜底）。
4. `public.sessions`/`public.messages` 已被 AI 问答占用，IM 表独立在 `im` schema。
5. 两个向量空间不合并（Concept 512 维 / RAG 1536 维）。
6. 飞书四基因：白底为主 · 0.5px 极轻分隔 · 四级灰 · 大留白小圆角。禁 `box-shadow`/1px 边框/纯黑正文/20px+ 圆角；**状态徽标必须带文字，不能只用色点**。
7. **仓库内不得出现任何明文凭据**（`.env` 存值不入库，`.env.example` 只放占位符，详见 README「凭据约定」）。

## 已存在、不要重做的资产

问题闭环五表（`issues`/`issue_events`/`mail_messages`/`knowledge_candidates`/`faqs`）、DDL `07_issues_knowledge.sql`、接口 `issues.py`(456 行)/`mail.py`、设计稿 `findperson/docs/问题闭环与知识库设计.md`——**本次重构的本质是把已建成的邮件闭环换成 IM 闭环，不是新建问题闭环**。明细见 [modules/issue-loop.md](modules/issue-loop.md)。

## 模块索引

> 状态：🚧 开发中 / ✅ 稳定 / ⏸ 未开始 / ⚠️ 有已知问题 / 🗑 已废弃

| 模块 | 文档 | 状态 | 一句话摘要 |
|---|---|---|---|
| IM 数据层 | [modules/im-database.md](modules/im-database.md) | ✅ | `im` schema 4 表 + `issues` 扩展 3 列 |
| IM 后端内核 | [modules/im-backend.md](modules/im-backend.md) | ✅ | 12 REST + WS 网关；幂等、离线增量、已读游标 |
| IM 前端 | [modules/im-frontend.md](modules/im-frontend.md) | ✅ | 飞书风三栏会话页 + WS 客户端 + store |
| 问题闭环（渠道替换+立项+待办） | [modules/issue-loop.md](modules/issue-loop.md) | ✅ | 立项 → 自动挂接 → 已读/首响 → 解决确认 → 沉淀候选，全链路已通 |
| 开发环境与验证 | [modules/dev-environment.md](modules/dev-environment.md) | ✅ | `fpim_dev` 库、8002/5175、自测脚本、本机坑 |
| 平台加固（既有代码缺陷修复） | [modules/platform-hardening.md](modules/platform-hardening.md) | ✅ | 改密补全、审计接线、双用户表、pytest 42/42 |
| 通讯录与个人主页 | [modules/directory-profile.md](modules/directory-profile.md) | 🚧 | 数据画像 + 拼音搜索已通；物理合并待做 |
| 附件与本地存储 | — | 🚧 | 内容寻址与上传下载已通；上限/回收策略未定 |
| 小管家 / 通知 | [modules/notify-bot.md](modules/notify-bot.md) | 🚧 | 立项/解决通知已通；报表周报待调度器 |
| 报表与看板 | [modules/stats-board.md](modules/stats-board.md) | 🚧 | 帮助榜 + 知识缺口地图（全员可见，正向口径） |
| 桌面壳 | — | ⏸ | Electron 套现有 Vue3 |

## 变更日志

| 日期 | 类型 | 摘要 | 涉及模块 |
|---|---|---|---|
| 2026-09-17 | 新增 | 文档骨架；三份正式文档（PRD/技术/前端）；高保真原型 + 截图 | — |
| 2026-09-17 | 修正 | **撤回错误勘误**：问题闭环五表已实现（此前只读 GitHub 得出反向结论） | 问题闭环 |
| 2026-09-17 | 决策 | Q1~Q5 + D1~D7 全部拍板（详见 `重构方案-IM化与问题闭环.md` 决策链） | — |
| 2026-09-17 | 新增 | `im` schema DDL 落库并验证幂等 | IM 数据层 |
| 2026-09-17 | 新增 | IM 后端内核 + 前端会话页；自测 HTTP 19/19、WS 13/13 | IM 后端/前端 |
| 2026-09-17 | 重构 | 三处入口「发邮件」→「进入会话」；`MailDialog` 引用解除；「我的问题」恢复显示 | 问题闭环 |
| 2026-09-17 | 重构 | 代码独立化（排除 venv 复制）；开发环境独立（`fpim_dev`/8002/5175）；自测脚本固化进仓库 | 开发环境 |
| 2026-09-17 | 重构 | 目录规范化（文档归 `docs/`）；仓库提到根，**历史重建为单次提交**（旧提交含明文凭据，备份在 `/tmp`） | — |
| 2026-09-17 | 修复 | **凭据脱敏**（全仓改环境变量注入，轮换 JWT 密钥）+ **统一文本编码**（修混合编码 `.gitignore` 等）；删重复 seed（16M） | 开发环境 |
| 2026-09-17 | 新增 | **会话内立项**：`POST /im/conversations/{cid}/issues` + 消息自动挂接活跃问题 + resolve_confirm 系统消息与广播；前端立项对话框；自测增至 HTTP 37 项 | 问题闭环 |
| 2026-09-17 | 新增 | **「待办」视图**：`/issues/assigned` + TodoView（待我处理/我提出的）+ 侧栏红点；自测增至 42 项 | 问题闭环 |
| 2026-09-17 | 修复 | **平台加固**：跑通既有测试套件（42/42）；修注册即登录失败、审计中间件未接线、审计外键指老表；改密从 stub 补全 | 平台加固 |
| 2026-09-18 | 新增 | **数据画像**：`GET /people/{id}/profile-stats` + `ProfileStats.vue` 两页共用 | 通讯录与主页 |
| 2026-09-18 | 新增 | **看板**：`/issues/leaderboard` + `/issues/gap-map` + BoardView（/board，侧栏「看板」）；拼音搜索（全拼/首字母）；自测增至 50 项 | 报表与看板 / 通讯录与主页 |
| 2026-09-18 | 新增 | **小管家**：bot 用户行 + `notify_user` + 立项/解决通知责任人（一人一栏 + 实时广播）；自测增至 57 项 | 小管家 |
| 2026-09-18 | 重构 | **原生 IM 壳**：`ImLayout.vue`（极左 rail + /im/chat|todo|board），登录默认进 IM 壳；旧 web 壳保留作测试对照 | IM 前端 |

## 关键问题与解决

### ⚠️ 基于公开远端仓库做事实判断（已纠正）

只读 GitHub 就断言"issues 表不存在"并给他人方案写"勘误"；实际本机副本全已实现。**核对代码事实必须以本机工作副本为准**；原 `~/projects/mine/findperson` 仅作追溯，已不再维护。全链条记录在 `.workbuddy/memory/`。

> 环境坑（Docker VM 死掉 / 端口被占 / 代理拦回环 / venv 不可搬迁）与安全坑（JWT 泄露 / VITE 构建内联 / ripgrep 漏隐藏目录）全部按三段式记在 [modules/dev-environment.md](modules/dev-environment.md)。

## 已锁定决策（勿改回）

IM 内核**自研 FastAPI WebSocket** ｜ 责任留痕**只做已读/未读**（可逆，`first_read_at` 已在积累）｜ 统计全员公开但**只公开正向榜 + 知识缺口地图** ｜ PC 端 **Electron 桌面壳**（后置）｜ 文件存**本地磁盘内容寻址** ｜ 推送走 **「小管家」系统号** ｜ 群聊**首期做、上限 100 人** ｜ UI 照飞书 7.x、沿用 Element Plus 主题层 ｜ 邮件渠道**逻辑废除**（历史保留作证据）｜ HR 联动、中文分词装 DB **范围外**。完整决策链与理由见 `重构方案-IM化与问题闭环.md`。

## 待处理 / 后期处理

- [ ] **`findperson/backend/README.md` 正文乱码**（UTF-16 + GBK 双重损坏，不可还原）——建议删除，`docs/` 已覆盖。
- [ ] **要资源（非技术）**：1TB 文件存储 + 水位告警；备份责任人（**数据库比文件更关键**）。
- [x] ~~`backend/venv` 未装 `pytest`/`httpx`，既有 `backend/tests/` 未执行。~~（已装，42/42 通过）
- [x] ~~「在会话里立项」交互~~（本轮已完成）。
- [x] ~~「我的待办」视图~~（本轮已完成）。
- [ ] 通讯录与个人主页物理合并（数据画像与拼音搜索已先行）。
- [ ] `contents.owner_id` / `peer_reviews.reviewer_id` 外键从老表 users 迁到 user2（platform-hardening 待办）。
- [ ] 群聊增强、小管家、报表看板、桌面壳。

## 可参考的类似项目

- **飞书 7.x 桌面端** —— UI 唯一参照（四基因见约束 6）
- **Zammad / Chatwoot** —— 问题闭环 + SLA 的成熟模型
- `findperson/agent-service/docs/modules/`（30 份模块设计文档，最佳深入入口）

## 后续优化方向

- 消息全文检索：首期 `pg_trgm` → P3 应用层 jieba + tsvector（不依赖 DB 扩展）
- 深色模式：token 已变量化 ｜ 单实例 → 多实例：WS 加 Redis pub/sub、存储换对象存储
