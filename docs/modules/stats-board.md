# 模块：报表与看板（正向榜 + 知识缺口地图）

> 状态：🚧 首期已通（两个全员可见的聚合接口 + 看板页）　｜　最近更新：2026-09-18

## 摘要

"过程即数据"的出口之一：把问题闭环攒下的数据做成**全员可见的正向榜与知识缺口地图**。
领导看趋势、员工看榜样，但**不公示个人拖延明细**（决策 D3 的红线）。

## 动机

PRD P3 + 决策 D3：统计全员公开，但只公开**正向榜 + 知识缺口地图**。
「帮助榜」回答"谁最能帮到人"（人才选拔的正向输入）；「知识缺口地图」回答"哪些问题没人接得住"（知识沉淀的选题来源）。

## 范围与非范围

- 范围内：帮助榜接口、缺口地图接口、看板页（`BoardView`）。
- 明确不做：个人拖延明细、超时/未达标榜单（违背 D3）；自动报表推送（那是小管家的活）。

## 上下游依赖

- 上游：`public.issues`（assignee/status/时间戳）、`public.user2` + `public.departments`。
- 同源：个人画像 `GET /people/{id}/profile-stats`（directory-profile.md）与帮助榜共用同一套口径。

## 关键接口与运行时信息

| 接口 | 说明 |
|---|---|
| `GET /api/v1/issues/leaderboard?limit=` | 帮助榜：按解决数降序 → 被问数降序；每项含 rank/name/department/askedCount/resolvedCount/avgFirstResponseHours |
| `GET /api/v1/issues/gap-map` | 缺口地图：未结问题（not_contacted/processing）按责任人部门聚合，带该部门最新一条未结问题 |

⚠️ **两个接口必须声明在 `GET /issues/{issue_id}` 之前**，否则 "leaderboard" 被路径参数吞成 422（FastAPI 按声明顺序匹配）。

### 前端

- `src/views/BoardView.vue`（路由 `/board`，侧栏「看板」）：左列帮助榜（前三名标金、点击进个人主页），右列缺口地图（含"未联系"红标）。
- API：`services/api/issues.js` 的 `fetchLeaderboard` / `fetchGapMap`。

## 设计决策与假设

- **缺口按"责任人所在部门"聚合**，而不是按问题关键词——issues 没有领域字段，责任人归属是最可靠的维度；也符合"缺口 = 哪个部门接不住"的语义。
- **排名只排有数据的人**（与画像口径一致）：200+ 个零数据账号不应稀释榜单。
- 看板页用纯静态聚合（每次请求实时算 SQL），数据量级（千级问题）下无需缓存。

## Bug 与问题记录

### BUG-001 路由被路径参数吞掉（2026-09-18，已解决）

- 错误行为：WHEN `GET /issues/leaderboard` 声明在 `GET /issues/{issue_id}` 之后 THEN 请求被匹配到后者，int 解析失败返回 422。
- 期望行为：WHEN 访问字面量路径 THEN SHALL 命中字面量路由。
- 不可破坏的行为：WHEN 既有 `/issues/{issue_id}` 的调用 THEN SHALL CONTINUE TO 正常。
- 根因：FastAPI 按声明顺序匹配，`{issue_id}` 在前则吞掉所有 `/issues/<字面量>`。
- 解决方式：所有 `/issues/<字面量>` 路由集中声明在 `/issues/{issue_id}` 之前（assigned / leaderboard / gap-map），并在注释里标明。
- 验证方式：自测 §23 断言三个接口 200。

## 已知限制与待办

- [ ] 缺口地图的"最新未结"每部门只取 1 条示例（点击展开该部门全部未结的交互未做）。
- [ ] 帮助榜没有"按部门筛选"与"按周期切换"（累计/近30天）。
- [ ] 管理员视角的 `/admin/issues/overview`（既有）与本模块的公开榜未统一页面——后台管理里另有一套。

## 变更历史

| 日期 | 变更 | 关联需求 / bug |
|---|---|---|
| 2026-09-18 | 帮助榜 + 知识缺口地图 + `BoardView`（/board，侧栏「看板」）；路由顺序坑记入 BUG-001 | PRD P3 + D3 |
