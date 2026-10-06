# 静态 Demo 迁移 Vue 与 AGUI 前端工程化实施方案

## 一、当前项目现状

当前仓库本质上是一个单页静态 Demo，核心文件只有三类：

- `index.html`
- `assets/main.css`
- `assets/main.js`

当前能力已经覆盖：

- 登录页
- 智能问答页
- 历史会话
- 右侧详情栏
- 名片库
- 人员主页
- 个人中心
- 操作手册
- 为他人画像
- 内容发布
- 内容检索与内容详情
- 后台看板
- 点赞点踩反馈

当前问题也很清楚：

- 所有逻辑都堆在 `assets/main.js`
- 页面没有模块化拆分
- 数据主要来自前端模拟数据和 `localStorage`
- 问答逻辑是前端本地匹配，不是真实 Agent
- 没有 API 层
- 没有统一状态管理
- 没有工程化构建、环境区分和联调约束

所以本次迁移不是“改个语法”，而是要把当前 Demo 从“静态演示型单文件应用”升级为“可接后端、可接 Agent、可多人协作开发”的前端工程。

## 二、迁移后目标架构

建议迁移后的技术栈为：

- 框架：`Vue 3`
- 构建工具：`Vite`
- 路由：`Vue Router`
- 状态管理：`Pinia`
- HTTP：`Axios`
- AGUI 流式接入：`fetch + ReadableStream` 或 `SSE`
- 样式：沿用当前 CSS，逐步拆成模块样式或全局主题文件

TypeScript 策略建议如下：

- 初期启用 `strict: false`，允许迁移期存在少量 `any` 过渡。
- `types/` 目录下的领域模型、接口类型、AGUI 事件类型先行定义。
- 页面和 Store 迁移时逐步补齐类型标注，优先补 service 入参出参、Store state、组件 props。
- 当静态页面迁移完成、AGUI 接入稳定后，再切换到 `strict: true` 做第二轮类型收敛。

目标目录建议如下：

```text
src/
  main.ts
  App.vue
  router/
    index.ts
  stores/
    auth.ts
    app.ts
    sessions.ts
    directory.ts
    content.ts
    admin.ts
    agui.ts
  views/
    LoginView.vue
    AskView.vue
    DirectoryView.vue
    MineView.vue
    ManualView.vue
    ProfileView.vue
    ReviewView.vue
    PublishView.vue
    ContentSearchView.vue
    ContentDetailView.vue
    AdminView.vue
  components/
    layout/
    ask/
    directory/
    profile/
    content/
    admin/
    common/
  services/
    api/
    agui/
    mock/
  types/
    api.ts
    agui.ts
    domain.ts
  utils/
    format.ts
    normalize.ts
    storage.ts
  styles/
    base.css
    tokens.css
    pages.css
```

## 三、现有功能保留清单

迁移方案的前提是“现有 Demo 所有功能都要保留”。建议先把现有功能固定成迁移验收清单。

### 3.1 登录与用户入口

需保留：

- 登录页展示
- 演示账号登录
- 顶部头像入口
- 个人中心入口
- 修改密码入口
- 操作手册入口
- 退出登录

迁移后位置：

- `LoginView.vue`
- `components/layout/MainTopbar.vue`
- `stores/auth.ts`

### 3.2 智能问答页

需保留：

- 输入问题并发送
- 示例问题
- 历史对话展示
- 搜索历史会话
- 新建对话
- 重命名会话
- 删除会话
- 问答消息气泡
- 推荐人员卡片
- 内容卡片
- 确认卡片
- 右侧详情栏
- 点赞点踩反馈

迁移后位置：

- `AskView.vue`
- `components/ask/*`
- `stores/sessions.ts`
- `stores/agui.ts`

### 3.3 名片库与人员主页

需保留：

- 关键词搜索
- 三级部门筛选
- 人员卡片展示
- 点击查看人员主页
- 人员主页展示自画像、他画像、发布内容

迁移后位置：

- `DirectoryView.vue`
- `ProfileView.vue`
- `stores/directory.ts`

### 3.4 个人中心与内容管理

需保留：

- 查看个人资料
- 编辑个人资料
- 查看我收到的评价
- 查看我发布的内容
- 发布内容
- 编辑内容
- 删除内容
- 置顶内容

迁移后位置：

- `MineView.vue`
- `PublishView.vue`
- `ContentSearchView.vue`
- `ContentDetailView.vue`
- `stores/content.ts`

### 3.5 他画像评价

需保留：

- 选择评价对象
- 填写评价内容
- 保存评价
- 查看我发出的评价
- 删除评价

迁移后位置：

- `ReviewView.vue`
- `stores/directory.ts`

### 3.6 后台看板

需保留：

- 人员规模
- 内容规模
- 推荐热度
- 活跃趋势
- 周切换逻辑

迁移后位置：

- `AdminView.vue`
- `stores/admin.ts`

### 3.7 操作手册

需保留：

- 手册卡片列表展示

迁移后位置：

- `ManualView.vue`

## 四、Vue 工程化迁移方案

### 4.1 迁移目标

把当前单文件式前端拆成“页面 + 组件 + Store + 服务层 + 类型层”的标准结构。

重点不是把现有函数原样拷贝到 Vue，而是做职责拆分：

- 页面负责结构和编排
- 组件负责局部 UI
- Store 负责状态
- Service 负责接口和 AGUI
- Utils 负责工具函数

### 4.2 页面拆分方案

建议按当前视图一一映射：

- `view-login` -> `LoginView.vue`
- `view-ask` -> `AskView.vue`
- `view-directory` -> `DirectoryView.vue`
- `view-mine` -> `MineView.vue`
- `view-manual` -> `ManualView.vue`
- `view-profile` -> `ProfileView.vue`
- `view-review` -> `ReviewView.vue`
- `view-publish` -> `PublishView.vue`
- `view-contentSearch` -> `ContentSearchView.vue`
- `view-contentDetail` -> `ContentDetailView.vue`
- `view-admin` -> `AdminView.vue`

### 4.3 组件拆分方案

问答页建议拆成：

- `ConversationSidebar.vue`
- `ConversationHistoryList.vue`
- `ConversationSearchPopover.vue`
- `ChatComposer.vue`
- `ThreadList.vue`
- `ThreadTurn.vue`
- `AssistantBubble.vue`
- `RecommendationCardGroup.vue`
- `ContentCardGroup.vue`
- `ActionConfirmCard.vue`
- `DetailSidebar.vue`
- `DetailPersonPanel.vue`
- `DetailContentPanel.vue`

通用组件建议抽出：

- `AppSidebar.vue`
- `MainTopbar.vue`
- `FeedbackButtons.vue`
- `TagList.vue`
- `ContentCard.vue`
- `PersonCard.vue`
- `EmptyState.vue`
- `MetricCard.vue`

### 4.4 核心函数迁移归属表

当前 `assets/main.js` 既有页面渲染函数，也有状态管理函数、mock 问答函数、工具函数和本地存储函数。迁移到 Vue 时，最容易犹豫的就是“这个函数到底放哪”。因此建议在迁移前先按下表固定归属。

| 原函数/函数组 | 迁入位置 | 迁移策略 |
| --- | --- | --- |
| `init()` | `src/main.ts` + `App.vue` + 各 Store 的初始化 action | 拆散，不保留单一入口函数 |
| `bindNavigation()` `navigateTo()` `applyRoute()` `switchView()` | `router/index.ts` + `MainLayout.vue` | 由 Vue Router 替代 |
| `bindHistory()` `bindBackButtons()` | Vue Router 导航守卫与组件内返回按钮 | 由路由系统替代 |
| `bindAvatarEntry()` `bindAvatarMenu()` `renderTopbarUser()` | `components/layout/MainTopbar.vue` + `stores/auth.ts` | 改为组件状态和鉴权状态驱动 |
| `bindLoginForm()` `bindPasswordForm()` `openPasswordModal()` | `LoginView.vue` `ChangePasswordDialog.vue` `stores/auth.ts` | 改为表单组件 + Store action |
| `ensureSessions()` `createSession()` `getActiveSession()` `getVisibleSessions()` `loadSessionIntoState()` `syncStateToActiveSession()` | `stores/sessions.ts` | 迁入 Store |
| `renderConversationHistory()` `renderConversationSearchResults()` | `components/ask/ConversationHistoryList.vue` `ConversationSearchPopover.vue` | 改为组件渲染 |
| `selectConversationSession()` `editSessionTitle()` `softDeleteSession()` `toggleHistoryMenu()` | `stores/sessions.ts` + 对话历史组件 | 状态放 Store，菜单交互放组件 |
| `bindQuestion()` `runCurrentQuestion()` | `components/ask/ChatComposer.vue` + `stores/agui.ts` | 发送入口改为 Store action |
| `renderLoadingState()` | `stores/agui.ts` + `ThreadList.vue` | 改为流式状态驱动 |
| `matchQuestion()` | `services/mock/matchQuestion.ts` | 保留为 mock 模式问答逻辑 |
| `analyzeQuestion()` | `services/mock/matchQuestion.ts` | mock 模式保留；真实模式由后端替代 |
| `extractTokens()` | `utils/normalize.ts` | 保留为前端关键词解析/高亮辅助工具 |
| `inferIntent()` | `services/mock/matchQuestion.ts` | mock 模式保留；真实模式由后端替代 |
| `buildAssistantAction()` | `services/mock/matchQuestion.ts` | mock 模式保留；真实模式由 AGUI 卡片事件替代 |
| `matchContent()` | `services/mock/matchQuestion.ts` | mock 模式保留；真实模式由后端检索替代 |
| `scorePerson()` | `services/mock/matchQuestion.ts` | mock 模式保留；真实模式由后端评分替代 |
| `renderConversation()` `renderConversationTurn()` `getAssistantReply()` | `components/ask/ThreadList.vue` `ThreadTurn.vue` `AssistantBubble.vue` | 拆为组件渲染 |
| `renderInlinePrimaryCard()` `renderInlineActionCard()` `renderInlineRecommendationCards()` `renderInlineContentCards()` | `RecommendationCardGroup.vue` `ContentCardGroup.vue` `ActionConfirmCard.vue` | 拆为组件 |
| `bindDetailSidebarToggle()` `openDetailPanel()` `renderDetailPanel()` | `components/ask/DetailSidebar.vue` + `stores/agui.ts` | 详情状态放 Store，渲染放组件 |
| `bindDirectory()` `renderDepartmentFilters()` `renderDirectory()` | `DirectoryView.vue` + `stores/directory.ts` | 筛选状态放 Store，列表渲染放页面/组件 |
| `renderProfile()` | `ProfileView.vue` + `stores/directory.ts` | 页面渲染 + Store 拉详情 |
| `bindMineForm()` `hydrateMyProfile()` `renderMineSummary()` | `MineView.vue` + `stores/auth.ts` | 表单逻辑迁到页面，资料状态迁到 Store |
| `bindPeerReviewForm()` `renderPeerReviewList()` `renderSentReviewList()` `deletePeerReview()` | `ReviewView.vue` `ProfileView.vue` `stores/directory.ts` | 评价数据迁入 Store |
| `bindContentForm()` `renderMineContentListMarkup()` `renderMineContentList()` | `PublishView.vue` `MineView.vue` `stores/content.ts` | 内容编辑/列表统一走 content Store |
| `bindContentSearch()` `renderContentSearch()` | `ContentSearchView.vue` + `stores/content.ts` | 搜索状态放 Store |
| `renderContentCard()` | `components/content/ContentCard.vue` | 抽成组件 |
| `bindContentDetail()` `openContentDetail()` `renderContentDetail()` | `ContentDetailView.vue` + Vue Router | 用真实路由详情页替代 |
| `renderAdmin()` `renderRankItem()` `buildWeeklyActiveTrend()` | `AdminView.vue` + `stores/admin.ts` | 指标状态放 Store，图卡渲染放页面/组件 |
| `renderManualPage()` | `ManualView.vue` | 页面渲染 |
| `bindGlobalDelegation()` | 各 Vue 组件事件 + emits | 删除，不保留事件代理模式 |
| `renderFeedbackButtons()` `toggleFeedback()` | `components/common/FeedbackButtons.vue` + `stores/agui.ts` / `stores/content.ts` | UI 组件化，行为事件由 Store 上报 |
| `loadContent()` `saveContent()` `loadPeerReviews()` `savePeerReviews()` `loadSessions()` `saveSessions()` `loadAuth()` `saveAuth()` | `services/mock/*` + `utils/storage.ts` | mock 模式保留，本地缓存工具化 |
| `normalizeContentRecord()` `normalizePersonRecord()` `normalize()` `splitTags()` `escapeHtml()` | `utils/normalize.ts` `utils/format.ts` | 保留为工具函数 |

迁移原则建议固定为三条：

- 与真实业务规则强绑定的本地问答函数，不直接迁入组件，统一收敛到 `services/mock/`。
- 与页面展示相关的 `render*` 函数，不迁函数本体，统一拆成 Vue 组件。
- 与会话、人员、内容、后台状态相关的函数，统一迁入对应 Store action。

### 4.5 Store 拆分方案

建议按业务拆 Store，而不是把原来 `state` 继续放在一个大对象里：

- `auth.ts`：登录态、当前用户、密码修改
- `app.ts`：全局视图、侧栏、顶部 UI 状态
- `sessions.ts`：历史会话、当前会话、会话搜索
- `agui.ts`：流式问答、消息事件、卡片事件、AGUI 会话状态
- `directory.ts`：人员列表、筛选、人员详情、评价
- `content.ts`：内容发布、搜索、详情、置顶、删除
- `admin.ts`：后台指标和排行

### 4.6 样式迁移方案

现有 `assets/main.css` 不建议一次性打碎重写。建议分两步：

第一步：

- 基本原样迁入 `src/styles/base.css`
- 保持现有类名，降低迁移风险
- 所有页面统一使用全局 CSS，不启用 `<style scoped>`
- 先由 `main.ts` 全局导入 `base.css`，保证 Vue 页面和原 Demo 视觉一致
- 迁移期间禁止出现“部分页面全局 CSS、部分页面 scoped CSS”混搭状态，避免优先级冲突和样式不一致

第二步：

- 逐步拆成 `layout`、`ask`、`profile`、`admin`、`content` 等页面样式
- 把颜色、圆角、阴影、间距抽成 token
- 等所有页面迁移完成并通过视觉验收后，再逐页切换到 `<style scoped>` 或 CSS Modules
- 切换 scoped 时，以页面或组件为单位推进，不跨多个页面混改

### 4.7 路由方案

建议使用真实路由替代当前 hash + view 切换方式。

建议路由：

- `/login`
- `/ask`
- `/directory`
- `/mine`
- `/manual`
- `/profile/:id`
- `/review`
- `/publish`
- `/content`
- `/content/:id`
- `/admin`

这样页面状态、分享链接、浏览器返回行为都会比当前单页视图切换更稳定。

建议布局嵌套关系如下：

- `/login`：独立布局，不显示侧边栏和顶栏
- `/ask`：`MainLayout`
- `/directory`：`MainLayout`
- `/mine`：`MainLayout`
- `/manual`：`MainLayout`
- `/profile/:id`：`MainLayout`
- `/review`：`MainLayout`
- `/publish`：`MainLayout`
- `/content`：`MainLayout`
- `/content/:id`：`MainLayout`
- `/admin`：`MainLayout`

建议路由守卫如下：

- 未登录访问除 `/login` 以外的页面时，统一重定向到 `/login`
- 已登录访问 `/login` 时，重定向到 `/ask`
- 路由守卫只判断登录态，不在守卫中写业务逻辑
- 页面级数据加载由各 View 或 Store action 负责

### 4.8 开发规范与协作约定

既然迁移目标是支持多人协作，建议在方案中提前固化以下约定：

- Vue 组件文件统一使用 `PascalCase` 命名，例如 `ConversationSidebar.vue`
- 组件标签在模板中统一使用 `PascalCase` 或 `kebab-case` 二选一，团队内保持一致，建议使用 `PascalCase`
- Store 文件统一使用领域命名，例如 `sessions.ts` `agui.ts` `content.ts`
- Store 对外 action 使用动词前缀，例如 `fetchPeople()` `createSession()` `sendMessage()`
- API 函数统一使用 `get/create/update/delete` 或 `fetch/create/update/remove` 风格，不混用
- `services/mock/` 和 `services/api/` 目录结构保持镜像，便于 mock/server 切换
- 迁移期间建议保留静态 Demo 在主分支可运行，新 Vue 工程在独立迁移分支推进，例如 `feat/vue-migration`
- 迁移完成前，不在 Vue 分支中删除原静态 Demo 文件，等功能对齐验收后再做收口
- 所有新增页面、组件、Store 都要附带最少的迁移说明，避免其他成员接手时反向读代码

## 五、问答页接入 AGUI 方案

### 5.1 改造目标

当前问答逻辑是：

- 前端拿到输入
- 本地分析问题
- 本地匹配人和内容
- 一次性渲染答案

迁移后问答逻辑要改成：

- 前端发消息给 AGUI / Agent
- 接收流式事件
- 边接边渲染消息
- 动态插入推荐卡片、内容卡片、确认卡片
- 把用户的点击、反馈、确认动作再回传给后端

### 5.2 AGUI 前端分层

建议新增以下 AGUI 模块：

- `services/agui/transport.ts`
- `services/agui/normalizer.ts`
- `services/agui/reporter.ts`
- `stores/agui.ts`

职责如下：

- `transport.ts`：建立流式连接，读取 chunk
- `normalizer.ts`：把后端 AGUI 事件整理成前端统一格式
- `reporter.ts`：负责反馈和交互事件上报
- `stores/agui.ts`：负责消息、卡片、流式状态和会话同步

### 5.3 AGUI 事件模型

建议前端统一消费以下事件：

- `message_start`
- `message_delta`
- `message_end`
- `card_recommendation`
- `card_content`
- `card_confirmation`
- `session_patch`
- `feedback_ack`
- `error`
- `done`

统一事件结构建议：

```ts
type AguiUiEvent =
  | { type: "message_start"; sessionId: string; messageId: string }
  | { type: "message_delta"; sessionId: string; messageId: string; delta: string }
  | { type: "message_end"; sessionId: string; messageId: string }
  | { type: "card_recommendation"; sessionId: string; messageId: string; cards: RecommendationCard[] }
  | { type: "card_content"; sessionId: string; messageId: string; cards: ContentCard[] }
  | { type: "card_confirmation"; sessionId: string; messageId: string; card: ConfirmationCard }
  | { type: "session_patch"; sessionId: string; patch: Partial<SessionMeta> }
  | { type: "feedback_ack"; sessionId: string; targetId: string }
  | { type: "error"; sessionId: string; message: string }
  | { type: "done"; sessionId: string };
```

### 5.4 问答 Store 结构

建议 `stores/agui.ts` 中维护：

```ts
{
  activeSessionId: "",
  streamStatus: "idle",
  messages: [],
  cards: [],
  pendingConfirm: null,
  feedbackMap: {},
  lastError: "",
  isDetailSidebarVisible: false,
  activeDetail: null
}
```

### 5.5 mock 模式与 AGUI 模式共用 Store 约定

第三阶段问答页迁移和第四阶段 AGUI 接入之间，建议不要切换 Store 结构，也不要让组件分别适配两套消息模型。最稳妥的做法是：mock 模式和 AGUI 模式共用同一个 `stores/agui.ts` 接口，差异只放在 action 实现层。

建议约定如下：

- `stores/agui.ts` 只维护一套统一的消息、卡片、流式状态结构。
- mock 模式通过 `services/mock/matchQuestion.ts` 生成结果，再模拟发出 `message_start -> message_delta -> card_* -> done` 事件。
- AGUI 模式通过 `services/agui/transport.ts` 接收真实事件流，再写入同一个 Store。
- Vue 组件只消费 `stores/agui.ts` 中的统一 state，不感知当前是 mock 还是 AGUI。
- 模式切换只改 `sendMessage()` 等 action 内部实现，不改 Store 结构，不改组件渲染逻辑。

这条约定的核心价值是：第三阶段先把问答页组件化并跑通 mock，第四阶段切真实 AGUI 时，不需要重写组件，也不需要改消息模型。

### 5.6 问答渲染策略

建议渲染顺序：

1. 用户发送后，先插入 user 消息
2. 插入一条空 assistant 消息草稿
3. 收到 `message_delta` 后不断追加文本
4. 收到 `card_recommendation` 时插入推荐卡片
5. 收到 `card_content` 时插入内容卡片
6. 收到 `card_confirmation` 时插入确认卡片
7. 收到 `done` 后结束本轮流式状态

### 5.7 问答页交互回传

问答页中以下动作要接后端事件：

- 回答点赞
- 回答点踩
- 推荐卡片点赞点踩
- 点击查看人员主页
- 点击关联内容
- 确认更新资料
- 确认发布内容
- 确认保存评价
- 取消确认
- 新建会话
- 重命名会话
- 删除会话

### 5.8 AGUI 接口建议

建议预留以下接口：

- `POST /api/agui/sessions`
- `GET /api/agui/sessions`
- `GET /api/agui/sessions/{id}`
- `POST /api/agui/sessions/{id}/messages`
- `POST /api/agui/events`

## 六、业务页面的后端与数据库接口预留方案

迁移到 Vue 后，不能继续让页面直接读写本地对象。即使第一阶段仍然展示 mock 数据，也要通过服务层和类型层访问。

### 6.1 接口层设计原则

每个业务域都要有自己的 API 文件，例如：

- `services/api/auth.ts`
- `services/api/sessions.ts`
- `services/api/people.ts`
- `services/api/reviews.ts`
- `services/api/content.ts`
- `services/api/admin.ts`
- `services/api/agui.ts`

页面和组件不能直接写 `fetch`，统一通过 service 层调用。

### 6.2 登录与用户信息接口

建议预留：

- `POST /api/auth/login`
- `POST /api/auth/logout`
- `POST /api/auth/change-password`
- `GET /api/me`
- `PUT /api/me/profile`

前端字段建议：

- `id`
- `name`
- `departmentPath`
- `role`
- `contact`
- `domains`
- `selfPortrait`
- `completeness`

### 6.3 会话与消息接口

建议预留：

- `GET /api/sessions`
- `POST /api/sessions`
- `PATCH /api/sessions/{id}`
- `DELETE /api/sessions/{id}`
- `GET /api/sessions/{id}/messages`

这部分最终会和 AGUI 会话接口衔接，但前端最好从一开始就抽成独立 session API。

### 6.4 名片库与人员主页接口

建议预留：

- `GET /api/people`
- `GET /api/people/{id}`
- `GET /api/departments/tree`

支持查询参数：

- `keyword`
- `level1`
- `level2`
- `level3`
- `page`
- `pageSize`

### 6.5 评价接口

建议预留：

- `POST /api/reviews`
- `GET /api/reviews/sent`
- `GET /api/people/{id}/reviews`
- `DELETE /api/reviews/{id}`

### 6.6 内容接口

建议预留：

- `GET /api/contents`
- `POST /api/contents`
- `GET /api/contents/{id}`
- `PUT /api/contents/{id}`
- `DELETE /api/contents/{id}`
- `POST /api/contents/{id}/pin`
- `POST /api/contents/{id}/feedback`

支持字段：

- `id`
- `ownerId`
- `title`
- `type`
- `tags`
- `summary`
- `body`
- `status`
- `publishedAt`
- `pinned`

### 6.7 后台接口

建议预留：

- `GET /api/admin/metrics`
- `GET /api/admin/rankings/recommend`
- `GET /api/admin/rankings/query`
- `GET /api/admin/trends/activity`

### 6.8 Mock 与真实接口双模式

建议环境变量控制：

- `VITE_API_MODE=mock`
- `VITE_API_MODE=server`

问答页再单独支持：

- `VITE_AGUI_MODE=mock`
- `VITE_AGUI_MODE=server`

这样前端可以做到：

- 没后端时仍能演示
- 联调时只切环境，不改页面代码

## 七、与后端、数据库、Agent 的依赖项

本方案落地过程中，前端并不是独立完成全部工作。除了 Vue 工程迁移本身可以由前端先推进之外，问答 AGUI 接入、业务接口接入、字段落库和会话闭环都依赖后端、数据库和 Agent 相关同学配合。因此，建议在开发启动前就把依赖项提前对齐。

### 7.1 与后端的依赖项

前端对后端的依赖，主要体现在“普通业务接口”和“会话/问答接口”两类。

第一类是普通业务接口，前端需要后端明确以下内容：

- 登录鉴权方案，例如 token、cookie、过期处理、退出登录方式。
- 人员列表和人员详情接口字段。
- 个人中心资料更新接口字段。
- 他画像评价的新增、查询、删除接口。
- 内容发布、编辑、删除、置顶、详情、列表接口。
- 后台指标、排行、趋势接口。
- 历史会话列表、会话详情、会话重命名、会话删除接口。

第二类是问答相关接口，前端需要后端明确以下内容：

- AGUI 会话创建接口。
- 会话消息发送接口。
- 会话快照查询接口。
- 会话状态同步接口。
- 反馈与行为事件上报接口。

前端在开发中最依赖后端先给出的交付物包括：

- 接口清单。
- 请求参数定义。
- 返回字段定义。
- 错误码和错误信息规范。
- 分页、筛选、排序规则。
- 联调环境地址和鉴权方式。

如果这些内容不先明确，前端只能先基于 mock service 开发，真正联调时会有较大返工风险。

### 7.2 与数据库的依赖项

前端虽然不直接操作数据库，但数据库表结构和字段设计会直接影响前端页面字段、表单结构和状态流转。

前端需要数据库或后端数据建模同学明确以下内容：

- 人员表有哪些基础字段，是否包含三级部门、角色、联系方式、负责领域、自画像完整度等信息。
- 人员评价表如何存储评价对象、评价人、评价时间、评价内容、删除状态。
- 内容表如何区分流程说明、常见问题、经验文章、审核状态、置顶状态、发布时间等字段。
- 会话表和消息表如何设计，是否支持标题、摘要、最后活跃时间、消息流状态、删除状态。
- 推荐记录表如何设计，是否记录推荐人、推荐理由、关联内容、排序位次。
- 反馈记录表如何设计，是否记录回答反馈、推荐卡片反馈、内容反馈、确认动作反馈。
- 后台指标所依赖的统计口径来自哪些表、哪些字段。

前端尤其需要提前确认两个问题：

1. 页面展示字段是否数据库中真实可落。
2. 页面状态流转是否有对应的库表状态支撑。

如果数据库没有提前定义这些字段，前端后面即使页面先做出来，也容易在真实接库时改动表单和展示结构。

### 7.3 与 Agent 的依赖项

问答页接入 AGUI 时，前端与 Agent 的依赖是最强的，因为问答页不是普通接口返回，而是事件流驱动。

前端需要 Agent 相关同学明确以下内容：

- 一轮问答中会输出哪些事件类型。
- 文本消息如何流式切片返回。
- 推荐卡片何时返回，是否与文本同轮挂接。
- 内容卡片何时返回，字段结构是什么。
- 确认卡片何时返回，确认动作 payload 长什么样。
- 一轮会话结束时用什么事件标记结束。
- 错误、中断、超时分别返回什么事件。
- 用户点击确认、点赞点踩、点击卡片后，Agent 是否继续响应，以及如何继续响应。

前端需要 Agent 侧至少明确以下协议内容：

- AGUI 事件格式。
- `messageId`、`sessionId`、`eventType` 的字段规范。
- 推荐卡片字段定义。
- 内容卡片字段定义。
- 确认卡片字段定义。
- 行为事件回传后的处理规则。

如果 Agent 侧输出结构不稳定，前端就无法稳定实现消息流、卡片渲染和确认交互。因此，AGUI 协议文档应在前端正式接入前先冻结一版。

### 7.4 前端可先行、需等待联调、必须共同确认的事项

前端可以先行完成的部分：

- Vue 工程初始化。
- 页面拆分和组件迁移。
- 样式迁移。
- Store 和 service 层骨架。
- mock 数据驱动的页面还原。
- mock 模式下的问答页组件化。

前端需要等待后端或 Agent 联调的部分：

- 登录态真实接入。
- 人员、评价、内容、后台等页面切真实接口。
- AGUI 流式输出接入。
- 会话状态同步。
- 反馈和行为事件真实上报。

前后端、数据库、Agent 必须共同确认的事项：

- 会话和消息字段口径。
- 推荐卡片、内容卡片、确认卡片的统一结构。
- 反馈事件口径。
- 状态字段命名，例如“已发布”“待审核”“已删除”“处理中”等枚举值。
- 详情页所展示字段是否真实可回。

### 7.5 建议提前对齐的三份文档

为了降低前端返工，建议在正式联调前至少先对齐以下三份文档：

1. 业务接口文档。
2. AGUI 事件协议文档。
3. 数据表与字段口径说明。

这三份内容一旦明确，前端迁 Vue、接 AGUI、接真实接口的推进就会顺很多。

## 八、迁移实施步骤

### 第一阶段：搭建 Vue 工程骨架

建议时间：`3-5` 个工作日。

目标：

- 建立 Vue 3 + Vite + Router + Pinia 工程
- 把现有静态资源迁入新工程
- 跑通基础布局

任务：

- 初始化 Vue 项目
- 导入当前样式和 logo
- 建立主布局和路由
- 抽出侧边栏、顶栏、空态、标签等通用组件

验收标准：

- Vue 项目能运行
- 主布局和现有 Demo 效果基本一致

对外依赖：

- 无强依赖，可由前端独立推进

### 第二阶段：静态页面逐页迁移

建议时间：`5-7` 个工作日。

目标：

- 在不接真实后端的情况下，把所有页面迁入 Vue

任务：

- 把登录页、名片库、个人中心、操作手册、人员主页、评价页、发布页、内容页、后台页迁成 Vue 页面
- 把现有本地数据改为 Store + Mock Service 驱动

验收标准：

- 除问答页外，其余页面功能与静态 Demo 一致
- 不再依赖 `index.html` 的手工 view 切换

对外依赖：

- 低依赖，可先用 mock service 推进
- 需要数据库和后端尽早提供字段口径，避免页面字段返工

### 第三阶段：问答页迁移到 Vue

建议时间：`4-6` 个工作日。

目标：

- 把历史会话、输入框、详情栏、消息线程改成组件化问答页

任务：

- 拆问答页组件
- 迁移本地会话功能
- 迁移当前推荐卡片、内容卡片、确认卡片 UI
- 先保留 mock 问答逻辑跑通 Vue 版页面

验收标准：

- Vue 版问答页在 mock 模式下能力等同当前 Demo

对外依赖：

- 可在 AGUI 协议未完成前先行推进
- 需要内部先确定统一 Store 结构和 mock 事件模型

### 第四阶段：AGUI 接入

建议时间：`5-8` 个工作日。

目标：

- 问答页从本地问答切换到 AGUI 流式链路

任务：

- 接入 `transport + normalizer + reporter + agui store`
- 实现流式消息渲染
- 实现推荐卡片、内容卡片、确认卡片的动态注入
- 实现反馈回传

验收标准：

- 问答页支持真实 Agent 流式输出
- 会话、卡片、反馈能正确联动

对外依赖：

- 依赖后端提供 AGUI 网关或问答接口
- 依赖 Agent 侧先冻结一版事件协议
- 依赖会话和事件上报接口联调环境

### 第五阶段：业务接口预留与双模式切换

建议时间：`4-6` 个工作日。

目标：

- 所有业务页面统一接到服务层，支持 mock 和真实接口切换

任务：

- 为用户、人员、评价、内容、后台、会话等页面补齐 API 层
- 给 Store 接入异步 action
- 用环境变量控制 mock / server 模式

验收标准：

- 页面不再直接依赖本地 seed 数据
- 即使还没后端，也能通过 mock service 运行

对外依赖：

- 依赖后端提供业务接口清单和联调环境
- 依赖数据库字段定义基本稳定

整体时间预估：

- 纯前端迁移最短约 `3-4` 周
- 如果要等待后端、数据库、Agent 协议同步推进，建议按 `4-6` 周安排更稳妥

## 九、关键风险与处理建议

### 风险一：迁移时功能回退

处理建议：

- 每迁一个页面就做对照验收
- 先列功能清单，再逐项迁移

### 风险二：问答页迁移与 AGUI 接入耦合过深

处理建议：

- 先把问答页组件化
- 再把数据源从 mock 切到 AGUI
- 不要在迁 Vue 的同时直接接真实 Agent

### 风险三：接口还没定，前端先写死

处理建议：

- 提前定义 TypeScript 类型
- 所有接口经过 service 层
- 不让页面直接依赖后端返回格式

### 风险四：样式在 Vue 中重构失真

处理建议：

- 第一阶段保留原始 class 和 CSS
- 先求效果一致，再做样式治理

### 风险五：后续 mock 和真实模式分裂成两套前端

处理建议：

- mock 和 server 只允许 service 层有差异
- 组件和页面逻辑保持一致
