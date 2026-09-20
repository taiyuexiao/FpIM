# 模块：问题闭环（邮件渠道 → IM 渠道）

> 状态：✅ 闭环已通（立项 → 留痕 → 解决 → 沉淀候选全链路自测通过；报表与看板未开始）　｜　最近更新：2026-09-17

## 摘要

把 findperson **已经建成的邮件闭环**换成 IM 闭环：问题不再靠邮件往复，而是在会话里沟通；**会话内可直接立项**，立项后该会话的每条消息自动挂接问题；「责任人何时首次看到」「何时首次回复」「解决确认」全部自动留痕。

## 动机

1. **现状断点**：AI 把人找对了，然后 `people.contact` → 线下邮件，过程丢失。链路在"找到人"之后就断了。
2. 领导原话是"邮件往来太低效且无法保存处理过程"——指的就是这套在跑的邮件链路。

> ⚠️ **这不是新建问题闭环**。`issues` / `issue_events` / `knowledge_candidates` / `faqs` 与 `issues.py`（456 行）都已存在并在跑，本模块做的是**换渠道 + 补留痕**。

## 范围与非范围

- 范围内：`issues` 挂 `conversation_id`；责任人首次已读 / 首次回复自动留痕；会话内的问题详情与时间线；三个入口的渠道替换；「我的问题」区块恢复可见。
- 明确不做：**超时提醒与升级（俗称"催办"）**——用户明确决定「先不做，只做已读/未读」；相关字段与事件已从方案移除。**HR 联动**——列为范围外，避免误排期。

## 上下游依赖

- 上游：[`im-database.md`](im-database.md)（`conversation_id` 等 3 列 + read 事件唯一索引）、[`im-backend.md`](im-backend.md)（`record_issue_read` / `_touch_issue_on_message` / `link_issue_conversation`）。
- 下游：`issues.py` 的既有状态机（`not_contacted` / `processing` / `resolved` / `unresolved`）、知识沉淀候选（标记已解决会自动建候选）、后续报表与人才画像。

## 关键接口与运行时信息

### 既有资产（**不要重做**）

| 资产 | 位置 |
|---|---|
| 五表模型 | `backend/app/models/issue.py` |
| DDL | `agent-service/scripts/ddl/07_issues_knowledge.sql` |
| 接口 | `backend/app/api/v1/issues.py`（`/issues/sync` · `/issues` · `/issues/{id}` · `PATCH /issues/{id}` · `/knowledge/candidates*` · `/admin/issues/overview` · `/faqs`） |
| 前端 | `src/stores/issues.js` · `src/services/api/issues.js` · `src/views/KnowledgeView.vue` |
| 设计稿 | `docs/问题闭环与知识库设计.md` |

### 新增的打通点

| 后端函数（`backend/app/services/im.py`） | 作用 |
|---|---|
| `link_issue_conversation(issue_id, conv_id)` | 发会话时把 `issues.conversation_id` 回填，问题可一键跳会话 |
| **`create_issue_in_conversation(conv_id, creator, question, assignee, summary)`** | **会话内立项**：建问题（`source='chat'`、状态即 `processing`）+ 会话锚点 + 插 `issue_card` 消息（幂等键 `issuecard-{id}`） |
| **`insert_resolve_confirm(issue_id, actor, new_status, note)`** | 解决/未解决时往会话插 `resolve_confirm` 系统消息（`sender_id='system'`），并广播给会话成员 |
| `record_issue_read(issue_id, reader_id)` | **只认责任人的已读**，写 `issue_events` 的 `read` 事件（唯一索引兜底，不可覆盖） |
| `_touch_issue_on_message(issue_id, sender_id)` | 消息落到问题时更新 `last_action_at`；发送方即责任人且未响应 → 记 `first_response_at` |
| `conversation_issue_brief(conv_id)` | 会话关联的问题列表（含 `askerId`，前端据此判断能否点"已解决"） |
| `issue_timeline(issue_id)` | 从 `issue_events` 聚合时间线 |

| 接口 | 说明 |
|---|---|
| **`POST /api/v1/im/conversations/{cid}/issues`** | **会话内立项**；单聊责任人默认对方，群聊必须显式指定；广播 issue_card 给会话成员 |
| `GET /api/v1/im/conversations/{cid}/issues` | 会话关联问题 + 时间线（右侧面板数据源） |
| `POST /api/v1/im/issues/{iid}/read` | 问题首次已读留痕（非责任人调用返回 false，不写入） |
| **`GET /api/v1/issues/assigned`** | **待我处理**：我作为责任人的问题（含 counts）。⚠️ 路由必须声明在 `/issues/{issue_id}` 之前，否则 "assigned" 会被路径参数吞成 422 |
| `PATCH /api/v1/issues/{issue_id}` | **既有接口**；标记 `resolved`/`unresolved` 且已挂会话 → 自动插 `resolve_confirm` + 广播；`resolved` 同时自动建知识沉淀候选 |

### 「待办」视图（被问方的日常入口）

- 前端 `TodoView.vue`（路由 `/todo`），侧栏「待办」带红点（`issues.assignedOpen` = 未联系+处理中），红点数据在 `MainLayout` 每 30s 轮询（问题变更频次低，不值得长连接）。
- 两个 tab：「待我处理」（`/issues/assigned`）与「我提出的」（`/issues`）；每行显示状态徽标、对方、最近动作、**已读/未读 + 已回复/未回复**两个留痕态（未读/未回复标蓝，给被问方压力）。
- 点击行/「进入会话」：已挂 `conversationId` 的直接 `im.selectConversation`；未挂的用 `im.openWith(peerId, issueId)` 取或建单聊（peer = 提问方或责任人，取决于 tab）。
- `_issue_dict` 本轮补齐了 `conversationId` / `firstReadAt` / `firstResponseAt` / `askerId` / `askerName`——这是待办视图与"进会话"跳转的数据基础。

### 消息自动挂接（"过程即数据"的关键）

`send_message` 未显式带 `issue_id` 时，若会话锚点指向一个**处理中**的问题，则自动挂接：

- 立项后锚点即指向它 → 双方普通聊天逐条落到问题上，`_touch_issue_on_message` 全程留痕
- 问题解决/关闭后锚点仍在但不再挂接 → 闲谈不污染已结问题
- 一个会话可以有多个问题（`conversation_issue_brief` 按 `conversation_id` 或锚点列出全部），锚点只指"当前活跃"的那个

### 三个渠道替换入口

| 页面 | 变化 |
|---|---|
| `DetailPanel.vue`（AI 搜人名片） | 「✉ 邮件」→「发消息」，`im.openWith(personId, issueId)` |
| `ProfileDetail.vue`（个人主页） | 「✉ 发邮件」→「发消息」 |
| `MineView.vue`（我的问题） | 「发邮件」→「进入会话」；区块从 `v-if="false"` **恢复显示** |

## 设计决策与假设

- **止于"逻辑废除"，不做物理销毁**（用户选 `Q5=C 废除`，执行时收窄了范围）：
  `MailDialog.vue` 不再被任何页面引用，但**文件与 `mail_messages` 历史保留**。理由：历史邮件就是现成的"处理证据"，直接物理删除会造成证据断档；且渠道替换若需回退，引用关系比表结构更容易恢复。
- **已读有两处，语义不同，不能混用**（本模块最关键的约束）：
  - 会话侧 `conversation_members.last_read_seq` —— 供红点，**会被覆盖**；
  - 问题侧 `issue_events.read` + `issues.first_read_at` —— 作为证据，**永不覆盖**。
  - 拿会话侧当证据 = 证据会被后续已读冲掉。
- **只认责任人的已读**：群里 20 个人都看了不算，否则会掩盖"责任人根本没看"。这是把"已读"当证据的前提。
- **`resolved` 只能由提问方确认**：后端 `update_issue` 硬校验 `issue.user_id != user.id → 403`，被问方无法自己点"已解决"。这是去掉时限机制后最容易被钻的空子，必须堵住。
- **立项即 `processing`，不走 `not_contacted`**：立项卡消息本身就是"联系"动作（与邮件链路"发出即处理中"同语义）。责任人首次响应由 `_touch_issue_on_message` 自动判定。
- **群聊立项强制唯一责任人**：`assignee_id` 不传时群聊直接 400——"集体负责 = 无人负责"是考核口径的底线，不能让步。
- **系统消息用 `sender_id='system'`**：`messages.sender_id` 是 NOT NULL，系统消息不能真空；约定字面值 `system`，`send_message` 对它放行成员校验且只允许系统类消息类型。前端按 `senderId === "system"` 判定居中灰条渲染。
- **不做超时/催办，但保留可逆性**：`first_read_at` / `first_response_at` 从上线第一天就在积累，日后若要加自动提醒，只需加调度器，**表结构不用重构**。
- **报表口径随之调整**：没有约定时限就不该有"达标率"，改用**分位数分布**；核心风险指标改为**已读未回复率**。

## Bug 与问题记录

### BUG-001 ORM 模型缺列导致 `update_issue` 500（2026-09-17，已解决）

- 错误行为：WHEN 立项后提问方标记已解决 THEN `PATCH /issues/{id}` 返回 500（`AttributeError: 'Issue' object has no attribute 'conversation_id'`）。
- 期望行为：WHEN 标记已解决 THEN 系统 SHALL 更新状态并往会话插 resolve_confirm 消息。
- 不可破坏的行为：WHEN ORM 读 `issues` 行 THEN 系统 SHALL CONTINUE TO 能访问 `conversation_id` / `first_read_at` / `first_response_at`。
- 根因：`08_im.sql` 用 raw SQL `ALTER TABLE` 给 `issues` 加了 3 列，但 ORM 模型 `models/issue.py` 没同步声明；读留痕字段的服务层全走 raw `text()` SQL（正常），而既有 `update_issue` 用 ORM 对象访问 → 属性不存在。**教训：DDL 加列时 ORM 模型必须同步，不管现有代码走不走 ORM。**
- 解决方式：`models/issue.py` 补 `conversation_id` / `first_read_at` / `first_response_at` 三列声明。
- 验证方式：立项全链路自测 18 项全过（`fpim_smoke_http.py` §14~21）。

### BUG-002 侧栏问题面板永远显示"暂无问题"（2026-09-17，已解决）

- 错误行为：WHEN 会话有立项问题 THEN 右侧问题面板仍显示空态文案。
- 期望行为：WHEN `store.issues` 有数据 THEN 面板 SHALL 渲染问题列表。
- 不可破坏的行为：WHEN 切换会话 THEN 面板 SHALL CONTINUE TO 随 `store.issues` 实时更新。
- 根因：`IssueSidePanel.vue` 里 `const issues = () => store.issues` 写成了函数，模板里 `issues.length` 拿到的是**函数的参数个数（恒为 0）**；应使用 `computed(() => store.issues)`。Vue 模板不会自动调用箭头函数。
- 解决方式：改为 `computed`。
- 验证方式：前端构建通过；立项后端到端自测确认面板接口返回正常。

## 已知限制与待办

- [x] ~~「在会话里立项」交互~~ → **已完成**：头部「＋ 立项」+ 侧栏按钮 + 对话框；立项 → 自动挂接 → 留痕 → 解决确认全链路 18 项自测通过。
- [x] ~~沉淀候选自动创建未验证~~ → 已在自测里断言（标记解决后 `knowledge_candidates` 落 1 条）。
- [ ] 「我的问题」列表页的**待办视角**（我作为责任人的问题）：已加列 `first_read_at` / `first_response_at`，前端还没有独立入口——**下一步做「待办」视图**。
- [ ] 立项对话框的问题描述**不支持引用某条消息**（比如长按消息"转问题"）；当前只能手填。
- [ ] 一个会话只能有一个"活跃锚点"：同一会话立第二个问题时，普通消息会挂到最新的那个；旧问题的继续讨论需重新立项或显式带 issueId（当前 UI 不提供显式选择）。
- [ ] `mail.py` / `mail_messages` 保留但已无 UI 入口与写入方，**需明确是否正式下线写入路径**。
- [ ] `resolve_confirm` 的广播只推给在线成员；离线成员重连后经增量补齐能看到（seq 拉取），无问题。

## 变更历史

| 日期 | 变更 | 关联需求 / bug |
|---|---|---|
| 2026-09-17 | `issues` 扩展 `conversation_id` / `first_read_at` / `first_response_at` + read 事件唯一索引 | FpIM P0-b |
| 2026-09-17 | 消息与服务层打通：`link_issue_conversation` / `record_issue_read` / `_touch_issue_on_message` | FpIM P0-b |
| 2026-09-17 | 三处入口由「发邮件」改为「进入会话」；「我的问题」区块恢复显示；`MailDialog` 引用全部解除（Q5=C 逻辑废除） | FpIM：渠道替换 |
| 2026-09-17 | **会话内立项**：`create_issue_in_conversation` + `POST /im/conversations/{cid}/issues` + 消息自动挂接活跃问题 + `resolve_confirm` 系统消息 + 广播；前端立项对话框 | FpIM P0-b |
| 2026-09-17 | 修 BUG-001（ORM 模型缺 3 列 → update_issue 500）、BUG-002（面板 computed 笔误）；立项全链路 18 项自测固化进 `fpim_smoke_http.py` | BUG-001/002 |
| 2026-09-17 | **「待办」视图**：`GET /issues/assigned`（路由顺序必须先于 `/issues/{id}`）+ `TodoView.vue`（待我处理/我提出的）+ 侧栏红点（30s 轮询）；`_issue_dict` 补闭环字段；自测增至 42 项 | FpIM：待办 |
