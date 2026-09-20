# 模块：通讯录与个人主页（F1 + F2）

> 状态：🚧 开发中（数据画像已通；物理合并与拼音搜索未做）　｜　最近更新：2026-09-18

## 摘要

PRD F1/F2：通讯录从"人员名录"升级为可直达对话的通讯录；个人主页承载**数据画像**（被问/解决/帮助榜排名/知识沉淀/首响时长），把"过程即数据"接到人才画像叙事上。

## 动机

领导要的是"画像进 HR 链路"：问题闭环攒下来的数据（谁被问、谁解决、响应多快）必须有个看得见的地方。个人主页就是那个出口。

## 范围与非范围

- 范围内（本轮已做）：数据画像接口 + 画像区组件（他人主页与个人中心共用）。
- 范围内（既有，未动）：组织树 + 人员列表（DirectoryView）、上级跳转、免加好友发消息、部门职责展示/编辑。
- 明确没做（见待办）：`/mine` 与 `/profile/:id` **物理合并为一个组件**；拼音/首字母搜索；`responsibility_assignments` 展示（PRD 提到但该表是否存在待核）。

## 上下游依赖

- 上游：`public.issues`（assignee/status/first_response_at）、`public.faqs`（owner）、`public.user2`。
- 下游：报表与看板模块（帮助榜就是画像排名的全量版）。

## 关键接口与运行时信息

| 接口 | 说明 |
|---|---|
| `GET /api/v1/people/{id}/profile-stats` | 数据画像。返回 askedCount / resolvedCount / resolveRate / helpRank(+Total) / faqCount / avgFirstResponseHours / last30d / period |

口径约定（**改动前先读这里**）：

- **被问数/解决数**：`issues.assignee_person_id = 本人`；解决 = `status='resolved'`（只认提问方确认，见 issue-loop.md）。
- **帮助榜排名**：全公司按「解决数降序 → 被问数降序」，只排进有数据的人；无数据的人 rank=null（前端显示 "—"）。
- **知识沉淀数**：`faqs.owner_person_id = 本人 AND status='published'`。
- **首响时长**：`avg(first_response_at - created_at)`，只算已响应的，单位小时（保留 1 位小数）。
- **统计周期**：`period.since` = 库里最早问题的创建日期，label 渲染成"累计（自 X 起）"；另有近 30 天窗口。

### 前端

- 组件 `src/components/profile/ProfileStats.vue`：5 格统计卡 + 周期标注 + 近 30 天脚注；**他人主页（ProfileDetail）与个人中心（MineView）共用同一个组件**。
- API：`services/api/people.js` 的 `fetchProfileStats(id)`。

## 设计决策与假设

- **先"数据同源、视觉同构"，不做物理合并**：PRD 要求 `/mine` 与 `/profile/:id` 合并为一个组件，但 MineView（431 行：我的问题管理 + 职责管理 + 发布管理 + 编辑）与 ProfileDetail（356 行：只读展示）职责差异太大，硬合并回归风险高。本轮把两页的画像区收敛到同一组件同一接口，物理合并留作后续（视觉参照物是飞书个人卡片，合并时再拆组件）。
- **画像全员可见但只给正向指标**：排名/首响是正向榜口径（决策 D3）；不给"谁拖得久"这类负向明细。
- **helpRank 分母只含有数据的人**：避免 200+ 个 0 分账号把排名稀释成无意义。

## Bug 与问题记录

暂无。

## 已知限制与待办

- [ ] **物理合并** `/mine` + `/profile/:id` 为单一组件（PRD F2 需求点 1）——本轮刻意不做，理由见设计决策。
- [x] ~~拼音/首字母搜索~~ → **已做**（2026-09-18）：`list_people` 对纯字母 keyword 追加内存拼音匹配（pypinyin，进程内缓存；全拼包含 / 首字母前缀），自测 §23 断言 `yuhaohan` / `yhh` 都能搜到"于浩瀚"。
- [ ] `responsibility_assignments` 责任关系展示（PRD F2 需求点 2）——表结构与数据待核实。
- [ ] 头像体系未接入画像区（现用文字头像）。
- [ ] 首响时长在数据稀疏时（新平台）参考价值低，分母 <3 时前端可考虑弱化显示（未做）。

## 变更历史

| 日期 | 变更 | 关联需求 / bug |
|---|---|---|
| 2026-09-18 | 数据画像：`GET /people/{id}/profile-stats` + `ProfileStats.vue`（两页共用）；接口自测 5 项（有数据/无数据/404/401/字段口径） | PRD F2 |
| 2026-09-18 | 拼音搜索：`list_people` 支持全拼/首字母（pypinyin 内存匹配 + 进程缓存）；自测固化进 §23 | PRD F1 验收 |
