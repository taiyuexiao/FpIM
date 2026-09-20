# 模块：IM 前端（会话页 · 飞书风格）

> 状态：✅ 可用（构建通过、页面可启动）　｜　最近更新：2026-09-17

## 摘要

IM 的前端壳：三栏会话页（列表 / 消息 / 问题详情）+ WS 客户端 + Pinia store + 一套飞书风格设计令牌。
同时改造既有页面的入口——把原来的「发邮件」全部换成「进入会话」。

## 动机

沟通要从邮件搬到 IM，前端需要一个"像飞书但不只是飞书"的工作台：主界面必须能直接看到**问题状态与处理过程**，否则"留痕"就藏进了二级页面，等于没有。

## 范围与非范围

- 范围内：会话列表（未读角标 / 状态标签）、消息区（文本 / 图片 / 文件 / 系统与问题卡）、输入区（附件、截图粘贴、草稿）、问题详情侧栏（状态 / 时间线 / 标记已解决）、实时连接状态、断线重连。
- 明确不做：**深色模式**（token 已变量化，后续覆盖一套变量即可，成本可控）；**语音视频**；**消息引用/转发**；**Electron 桌面壳**（后续独立模块）。

## 上下游依赖

- 上游：[`im-backend.md`](im-backend.md)（REST + WS）、[`issue-loop.md`](issue-loop.md)（问题数据）、`stores/auth.js`（token / userId）、`stores/directory.js`（人员姓名头像）。
- 下游：会话页被 `MainLayout` 的布局层长连接支撑；入口来自 `AskView`/`DetailPanel`（AI 搜人）、`ProfileDetail`（个人主页）、`MineView`（我的问题）。

## 关键接口与运行时信息

### 关键文件

| 文件 | 行数 | 职责 |
|---|---|---|
| `src/views/ChatView.vue` | 270 | 会话页壳：三栏布局、侧栏开关、建群/拉人弹窗 |
| `src/components/im/ConversationList.vue` | 77 | 左栏会话列表 |
| `src/components/im/MessageList.vue` | 148 | 消息区（含 `resolve` / `focus-issue` 事件） |
| `src/components/im/MessageComposer.vue` | 111 | 输入区（附件 / 粘贴 / 草稿） |
| `src/components/im/IssueSidePanel.vue` | 174 | 右栏问题详情 + 时间线 + 标记已解决 |
| `src/stores/im.js` | 341 | Pinia store：全部状态与动作 |
| `src/services/im/socket.js` | 160 | WS 客户端（重连、心跳、帧分发） |
| `src/services/im/format.js` | 125 | 时间 / 文件大小等格式化 |
| `src/services/api/im.js` | 49 | REST 封装 |
| `src/styles/im.css` | 610 | **设计令牌 + IM 组件样式**（飞书四基因落点） |

### 双壳结构（2026-09-18 起）

- **原生 IM 壳 `ImLayout.vue`（产品形态）**：`/im/chat` `/im/todo` `/im/board`。极左 64px 导航栏（头像 + 消息/待办/看板 + 问答回旧壳 + 退出），不复用 OA 侧栏/顶栏；rail 顶部带 `-webkit-app-region: drag`（给将来的 Electron 壳留拖拽区）。
- **旧 web 壳 `MainLayout.vue`（测试对照）**：`/ask` `/directory` `/mine` 等原有页面原样保留；原生壳 rail 的「问答」图标回跳旧壳。
- 登录后默认落 `im-chat`；`/` 重定向到 `/im/chat`。
- 两个壳**各自挂载 `im.init()`**（幂等）：切壳时旧壳 `teardown` 断连、新壳重连，互斥交接无泄漏。

### 接线点（旧 web 壳侧，保留作对照）

| 位置 | 行为 |
|---|---|
| `src/router/index.js` | 新增路由 `{ path: "chat", name: "chat" }` |
| `src/components/layout/AppSidebar.vue` | 新增导航项「消息」（`ChatLineRound`），角标取 `im.totalUnread` |
| `src/layouts/MainLayout.vue` | `onMounted → im.init()` / `onUnmounted → im.teardown()` |
| `src/main.js` | 引入 `./styles/im.css` |
| `DetailPanel.vue`（AI 搜人名片） | 原「✉ 邮件」→「发消息」：`im.openWith(personId, issueId)` → 跳 `chat` |
| `ProfileDetail.vue`（个人主页） | 同上，`im.openWith(person.id)` |
| `MineView.vue`（我的问题） | 「发邮件」→「进入会话」：`im.openWith(item.assigneePersonId, item.id)` |

### store 契约（`useImStore`）

- state：`conversations` / `activeId` / `messages{cid}` / `hasMore` / `connection` / `online` / `typing` / `issues` / `draft`
- getters：`active` / `activeMessages` / `totalUnread` / `titleOf` / `peerOf`
- actions：`init` `loadConversations` `connect` `teardown` `resyncAll` `openWith` `newGroup` `invite` `selectConversation` `loadMessages` `loadMore` `loadIssues` `sendText` `sendFile` `markRead` `revoke` `notifyTyping`
- **`init()` 幂等**（`initialized` 标记），因为布局层可能因登录态变化重复挂载。

### WS 客户端

- `createImSocket({ getToken, handlers })` → 返回 `{ close, sendMessage, sendRead, sendTyping }`
- `resolveWsUrl()` 由 API base 推导：`http(s) → ws(s)`，路径 `/api/v1/ws/im?token=...`
- 帧分发到 handlers：`ready` / `ack` / `message` / `read` / `typing` / `presence` / `error` / `status`
- 断线指数退避重连；重连成功后调 `resyncAll()` 补齐离线消息。

### 如何运行与验证

```bash
# 需要后端先起在 8002（见 im-backend.md）
cd /Users/shipeilin/projects/mine/FpIM/findperson
node node_modules/vite/bin/vite.js --mode fpim --port 5175 --host 127.0.0.1 --strictPort
# 打开 http://127.0.0.1:5175  → 用 P0004 + 种子口令（见 backend/.env 的 SEED_PASSWORD）登录 → 左侧「消息」
```

> `--mode fpim` 读取 `.env.fpim`，把 API 指向独立的 8002 实例；**不影响默认 `.env` 指向的 8001**。

## 设计决策与假设

- **设计令牌集中在 `im.css`**，不引新组件库（`D4`）。飞书像不像八成不在组件库，而在四个视觉基因：
  1. **白底为主**——只有左栏浅灰，内容区全白（上一版做成了"灰底 + 白卡片浮起"，方向就错了）
  2. **0.5px 极轻分隔**，几乎不用阴影
  3. **四级灰严格分层**，正文用 `#1F2329` 而非纯黑
  4. **大留白 + 小圆角**（6~10px，行高 1.6）
  - 自检口诀：新页面出现 `box-shadow` / `1px` 边框 / 纯黑文字 / 20px+ 圆角，基本判定跑偏。
- **状态徽标必须带文字，不能只用色点**。只靠颜色，员工会读成"系统在给我亮红牌"；写成「已读，未回复」就是一个中性事实陈述。这个小差别直接决定机制会不会招人抵触，因此是硬约束。
- **长连接挂在布局层而非会话页**：这样在任何页面未读角标都能实时更新。
- **「待办」是独立导航项**（飞书没有）——被问方每天要打开的不是"会话"，而是"我欠着谁的问题"。
- **右侧面板放"问题详情 + 处理过程时间线"**（飞书放群成员）——留痕是本产品的核心资产，必须在主界面可查。
- **`fpim:start-conversation` 自定义事件监听从设计上保留**：当前所有入口都直接调 `im.openWith` 后 `router.push`，事件通道是给将来的跨组件/非 Vue 调用方留的兜底。⚠️ 目前**没有任何地方 dispatch 它**。

## Bug 与问题记录

### BUG-001 发送消息后出现重复气泡（2026-09-17，已解决）

- 错误行为：WHEN 通过 WS 发送消息 THEN 乐观插入的气泡收到 `ack` 后**不被替换**，屏幕上出现一条"发送中"和一条正式消息。
- 期望行为：WHEN `ack` 到达 THEN 系统 SHALL 用服务端消息替换同 `clientMsgId` 的乐观消息，全程只有一条气泡。
- 不可破坏的行为：WHEN WS 不可用 THEN 系统 SHALL CONTINUE TO 走 HTTP 兜底发送，且**同样具备幂等**（同 `clientMsgId` 不产生两条）。
- 根因：`socket.js` 内部的 `sendMessage()` **自己生成了 `clientMsgId`**，而 store 的乐观消息用的是另一个 id，两者对不上，`ack` 无法定位待替换的那条。
- 解决方式：把 `clientMsgId` 改为**由调用方传入**（`sendMessage({ ..., clientMsgId })`），store 先造好 id 再同时用于乐观插入与发送。
- 验证方式：`scripts/fpim_smoke_ws.py` 第 3 组断言 ack 的 `clientMsgId` 与发出的一致；HTTP 侧 `fpim_smoke_http.py` 第 5 组断言重复提交返回同一条。

### BUG-002 构建失败：ChatView 导入路径多一层（2026-09-17，已解决）

- 错误行为：WHEN 执行 `npm run build` THEN 报模块解析失败，找不到 `../../services/...`。
- 期望行为：WHEN 同一构建 THEN 系统 SHALL 成功产出 `ChatView` chunk。
- 不可破坏的行为：WHEN 该文件被移动到其他目录 THEN 构建 SHALL 报错而非静默解析到错误模块。
- 根因：`ChatView.vue` 位于 `src/views/`，其相对导入写成了按 `src/views/im/` 的层级（多一层 `../`）。
- 解决方式：批量修正为 `../services/` `../stores/` `../components/`。
- 验证方式：`npm run build` 通过，产出 `ChatView` chunk 约 24KB。

### BUG-003 问题面板永远显示空态（2026-09-17，已解决）

- 错误行为：WHEN 会话有立项问题 THEN `IssueSidePanel` 仍渲染"这个会话还没有关联问题"。
- 期望行为：WHEN `store.issues` 有数据 THEN 面板 SHALL 渲染问题卡片与时间线。
- 不可破坏的行为：WHEN 切换会话 THEN 面板 SHALL CONTINUE TO 跟随 `store.issues` 实时刷新。
- 根因：`const issues = () => store.issues` 写成了箭头函数，模板里 `issues.length` 读到的是**函数的参数个数（恒为 0）**；Vue 模板不会自动调用函数。
- 解决方式：改为 `computed(() => store.issues)`。
- 验证方式：构建通过 + 立项后端到端自测（面板数据接口断言正常）。

## 已知限制与待办

- [ ] `fpim:start-conversation` 事件无 dispatch 方（见「设计决策」）——要么补调用方，要么删除该监听以免误导。
- [ ] typing 未节流，长文本输入会高频发帧。
- [ ] 图片消息点击放大预览未做；拖拽上传未做（粘贴与选择文件已支持）。
- [ ] 群聊的 @提及 未实现；群成员管理只有「拉人」，无移出群。
- [ ] 深色模式未做（token 已变量化）。
- [ ] `im.css` 尚未与既有 `element-theme.css` 做冲突排查（两者都覆盖 Element Plus 变量）。
- [ ] 立项对话框不能引用某条消息作为问题来源（"长按消息 → 转问题"未做）。
- [ ] 立项后**只有新消息**自动挂接；想给历史消息补挂问题，暂无 UI。

## 变更历史

| 日期 | 变更 | 关联需求 / bug |
|---|---|---|
| 2026-09-17 | 新建会话页与 IM 组件、store、WS 客户端、设计令牌；侧栏加「消息」入口；路由加 `/chat` | FpIM P0-a |
| 2026-09-17 | 三个入口的「发邮件」改为「进入会话」（名片 / 个人主页 / 我的问题） | FpIM：渠道替换 |
| 2026-09-17 | 修 BUG-001（重复气泡）、BUG-002（导入路径） | BUG-001 / BUG-002 |
| 2026-09-17 | **会话内立项 UI**：头部「＋ 立项」按钮（`fpim:create-issue` 事件 → IssueSidePanel 对话框）+ 责任人选择（单聊默认对方/群聊必选）+ `store.createIssue`；收到 `issue_card`/`resolve_confirm` 消息时自动刷新问题面板；已读推进带上 issueId；`isSystem` 识别 `senderId==='system'` | FpIM P0-b |
| 2026-09-17 | 修 BUG-003（面板空态：函数 vs computed 笔误） | BUG-003 |
