# 模块：统一应用壳与飞书风格换肤（一期）

> 状态：🚧 单壳化 + 机械换肤已落地并浏览器实测；细节打磨待查漏　｜　最近更新：2026-10-04

## 摘要

把产品收敛为**单一应用壳**（ImLayout 极左 rail 全菜单），并把首问平台遗留页面（智能问答、名片库、知识库、我的、后台等）的旧 OA 皮肤**统一换成飞书 7.x 风格**。
铁律：**只改 UI 风格，不改内容**——DOM 结构、交互逻辑、接口调用一律不动，只动壳层导航与 CSS。

## 动机

1. 领导批评现有界面"很土"：当前双壳并存（ImLayout 新壳 + MainLayout 旧 OA 壳），一切换到问答/名片库就露出旧皮肤（box-shadow 分层、16px+ 大圆角、加粗按钮、渐变卡片），观感割裂。
2. 产品形态应该是"一个像飞书的办公客户端"，不是"IM 内核 + 外挂旧网站"。一期要求：消息、通讯录、待办、看板、智能问答、名片库同处一个壳、一套视觉。

## 范围与非范围

- 范围内：rail 全菜单化（消息/通讯录/待办/看板/智能问答/名片库/管理后台）；所有既有页面 reparent 进 ImLayout；旧皮肤（`assets/main.css` + `element-theme.css`）对齐飞书四基因；旧 OA 壳（AppSidebar/MainTopbar/MainLayout）退役。
- 明确不做：重构任何业务交互、改文案/信息架构、深色模式（token 变量化已预留）、Electron 壳（独立模块）。

## 壳与菜单结构

```
┌ rail(64px) ┬ 内容区 ────────────────────────────────┐
│ [头像]     │ /im/chat      消息（三栏会话）           │
│ [消息]     │ /im/contacts  通讯录（新，一期）         │
│ [通讯录]   │ /im/todo      待办                       │
│ [待办]     │ /im/board     看板                       │
│ [看板]     │ /im/ask       智能问答（原 AskView）      │
│ [问答]     │ /im/directory 名片库（原 DirectoryView）  │
│ [名片库]   │ /im/mine /im/profile/:id /im/knowledge … │
│ [管理]*    │ /im/admin     后台管理（*仅管理员可见）    │
│ ────      │                                          │
│ [设置/退出]│                                          │
└───────────┴──────────────────────────────────────────┘
```

- 路由全部挂到 ImLayout children；`/ask` `/directory` 等旧路径做重定向到新路径（外部书签/文档不失效）。
- 「问答」「名片库」等原旧壳页面**内容不动**，只换容器与皮肤。
- 旧 MainLayout/AppSidebar/MainTopbar 组件文件保留一版（过渡期对照），路由不再指向；稳定后删除。

## 旧皮肤 → 飞书皮肤对照（换肤规则）

| 旧基因（`assets/main.css` + `element-theme.css`） | 飞书基因（`styles/im.css` token） |
|---|---|
| `--blue`/`--line`/`--shadow`/`--radius-lg`(16px+) | `--im-primary` / `--im-line`（0.5px）/ 不用阴影 / `--im-radius` 6~8px |
| box-shadow 分层浮卡 | 0.5px 极轻分隔线，白底为主 |
| `font-weight: 800` 按钮、渐变、大圆角 | 字重 400/500，纯色小圆角 |
| 正文 #303133/纯黑混用 | 四级灰 #1F2329/#646A73/#8F959E/#BBBFC4 |

自检口诀沿用 im-frontend.md：出现 box-shadow / 1px 深边框 / 纯黑正文 / 20px+ 圆角即跑偏；状态徽标必须带文字。

## 实施要点

1. **类名不动、DOM 不动，只改 CSS**：`.view` `.page-heading` `.card-grid` `.toolbar` `.sidebar-nav` 等旧类的样式重写为飞书基因（"只改风格"的最稳落法）。
2. **Element Plus 主题**（`element-theme.css`）重对齐：按钮字重/圆角/边框/输入框描边全走 `--im-*`；Dialog/Popover 同步。
3. **token 单一来源**：`--im-*` 定义提升到 `:root`（原在 `.fpim` 作用域下，旧页面拿不到——这也是待办页 `--im-brand` 失效 bug 的土壤），`.fpim` 内只留布局。
4. 回归护栏：换肤后 `npm run build` 通过 + 主链路（登录 → 消息 → 问答搜人 → 立项 → 待办 → 看板）手动过一遍；不改任何 `services/` 与 `stores/`。

## 设计决策与假设

- **单壳化而非双壳同步换肤**：双壳意味着两套导航/挂载/长连接生命周期永远要同步维护；直接收敛到 ImLayout 一了百了。旧壳降级为"被换肤的页面集合"。
- **换肤与功能开发解耦**：本模块的 PR 不夹带功能变更，方便 review 时一眼分辨"风格改动"。
- **rail 保留 `-webkit-app-region: drag`**：Electron 预留不动。

## Bug 与问题记录

### BUG-001 单壳化/换肤引入的三处显示问题（2026-10-05，已解决）

用户反馈："待办、看板的显示问题依旧存在；名片库出现了新的显示问题"。

- 错误行为：WHEN 打开「待办」/「看板」THEN 页头、标签、筛选、列表被排成**横排四列**挤压在半屏；WHEN 打开「名片库」等旧页面 THEN 内容**顶到 rail 边缘无留白**。
- 期望行为：WHEN 打开待办/看板 THEN SHALL 纵向文档流（页头 → 标签 → 列表）；WHEN 打开旧页面 THEN SHALL 与旧壳一致有 12px/24px 外边距。
- 不可破坏的行为：WHEN 打开消息/通讯录页 THEN SHALL CONTINUE TO 全幅三栏布局（它们依赖 `.fpim` 的 flex）。
- 根因（两个）：① TodoView/BoardView 根节点借 `.fpim` 类取设计 token，但 `.fpim` 是 **flex 容器**，子节点被排成横排——这是待办页最初"UI 很多 bug"的主因，此前只修了颜色与跳转，没修布局；② 单壳化 reparent 时旧壳 `.main-content` 的 `padding: 12px 24px 24px` 丢失，`.view` 类旧页面（名片库/问答/我的等）全部贴边。
- 解决方式：① `.todo-page` / `.board-page` 显式 `display: block` 覆盖；② `im.css` 补 `.im-app-main > .view.active { padding: 12px 24px 24px }`（收在壳作用域内，登录页的 `.view` 不受影响）。
- 验证方式：浏览器几何探测——待办子节点 x 递增→x 相同 y 递增（20/61/112/153）；看板三段纵向（20/63/518）；名片库内容 x=88（离 rail 24px）。

## 实施记录（2026-10-04 落地）

1. **单壳化**：`router/index.js` 重写——全部页面挂 ImLayout children；旧页面 reparent 时**路由 name 不变**（ask/directory/mine/profile/…），全仓 `push({name})` 零改动；`chat`/`todo`/`board` 旧名与 `/ask` 等旧路径做重定向兼容。MainLayout/AppSidebar/MainTopbar 不再被路由引用（文件保留，稳定后删）。
2. **rail 全菜单**：消息/通讯录/待办/看板/问答/名片库/管理(仅管理员) + 底部「我的/退出」。
3. **换肤机械 pass**：`assets/main.css` 的 `:root` token 整体替换为飞书基因（`--shadow:none`、圆角 28/22/16/14px→8px、999px 胶囊→6px（铃铛角标保留）、`font-weight:800→500`、body 渐变→平白、字体换 PingFang 系统栈）；35 处 box-shadow 清零；Element Plus 主题（element-theme.css）按钮字重 800→500、字体同步。
4. **token 提升**：`--im-*` 从 `.fpim` 作用域提升到 `:root`（旧页面与新页面共用一套变量；也是 BUG-003 的土壤修复）。
5. **浏览器实测**：token 探测（body 白底 / radius 8px / shadow none / #3370ff）；rail DOM 9 项菜单；/im/ask 在新壳内渲染且阴影清零；通讯录/待办页样式正常。

## 已知限制与待办

- [ ] 换肤是**机械 pass + token 层**，个别旧组件（AskView 卡片、AdminView、LoginView）的细节观感需逐页目检打磨（建议用截图对照飞书再收一轮）。
- [ ] `assets/main.css` 里 `--blue`/`--line` 等旧 token 名保留（值已换飞书），后续可更名收敛到 `--im-*` 单一体系。
- [ ] MainLayout/AppSidebar/MainTopbar 文件退役删除。
- [ ] 后台管理（AdminView）换肤优先级最低，可滞后。

## 变更历史

| 日期 | 变更 | 关联需求 / bug |
|---|---|---|
| 2026-10-04 | 新建模块（一期）：单壳化 + 旧 UI 换肤计划立项 | 一期：UI 统一对齐飞书 |
| 2026-10-04 | 落地：单壳路由重写 + rail 全菜单 + main.css/element-theme.css 机械换肤 + token 提升 `:root`；浏览器实测通过 | 一期 |
| 2026-10-05 | 修 BUG-001（待办/看板横排、旧页丢边距三处显示问题） | BUG-001 |
| 2026-10-05 | 登录页重设计：**FpIM 品牌简洁版**（白底居中卡 + Fp logo + 标语 + 主按钮，旧「首问必答平台」品牌移除），登录逻辑零改动、成功直达 IM 壳；浏览器实测登录流转正常 | 一期：UI 统一 |
| 2026-10-05 | 头像字形终修：rail 头像**直接复用 .fpim-avatar 类**（此前字距 hack 反而显乱），与会话区逐像素同源 | 一期：UI 统一 |
| 2026-10-05 | UI 精修：rail 头像字形与会话区 .fpim-avatar 统一（13px/500 + 字距）；智能问答输入框**框套框修复**（Element 内层 :focus 内框特异性盖过外层样式 → 强制清内框、焦点反馈收至外框）、宽度与内容区对齐、发送钮换纸飞机图标、侧栏「历史对话/搜索/新对话」排布规整（统一 32px 控件） | 一期：UI 统一 |
