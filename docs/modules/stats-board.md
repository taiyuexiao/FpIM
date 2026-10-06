# 模块：报表与看板（正向榜 + 知识缺口地图 + 分析统计）

> 状态：🚧 首期已通；一期扩充统计指标（科室被问/回复时间/解决占比）　｜　最近更新：2026-10-04

## 摘要

"过程即数据"的出口之一：把问题闭环攒下的数据做成**全员可见的正向榜与知识缺口地图**。
领导看趋势、员工看榜样，但**不公示个人拖延明细**（决策 D3 的红线）。
一期新增领导要求的**数据分析与统计**：科室被问次数、被提问人回复时间、解决件数/占被问比例。

## 动机

PRD P3 + 决策 D3：统计全员公开，但只公开**正向榜 + 知识缺口地图**。
「帮助榜」回答"谁最能帮到人"（人才选拔的正向输入）；「知识缺口地图」回答"哪些问题没人接得住"（知识沉淀的选题来源）。
一期领导追加："要进行数据分析与统计——每个科室被提问的次数、被提问人回复时间、解决件数/占总被问的比例"。

## 范围与非范围

- 范围内：帮助榜接口、缺口地图接口、看板页（`BoardView`）。
- 范围内（一期扩充）：**科室维度统计**（被问次数、解决件数与解决率、回复时长分布）、看板分析区、口径与画像/帮助榜对齐。
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

## 一期统计指标（领导点名，2026-10-04）

新增接口 `GET /api/v1/issues/department-stats`（**必须同样声明在 `/issues/{issue_id}` 之前**，见 BUG-001），按**责任人所在科室/部门**聚合（与缺口地图同维度口径）：

| 指标 | 口径 | 说明 |
|---|---|---|
| 被问次数 | `count(issues)` 按 `assignee` 所属科室分组 | 领导点名第 1 项；**以知识缺口形态呈现，不做科室排名**（红线 1） |
| 解决件数 / 解决率 | `count(status='resolved')` / 被问次数 | 领导点名第 3 项；unresolved 不计入分子 |
| 回复时间 | `avg/median(first_response_at - created_at)`（小时） | 领导点名第 2 项「被提问人回复时间」；只算已回复的，输出中位数为主（P50）+ 均值参考 |

口径联动（与 directory-profile.md / 画像一致）：

- 回复时间用 `first_response_at - created_at`（与画像 `avgFirstResponseHours` 同源）；分位数输出 P50/P90（PRD M4/M5 口径）。
- 解决只认 `status='resolved'`（提问方确认，BR-02）。
- 呈现红线：科室被问量**不做排名**，做成"职责模糊/知识缺口"视角；个人回复时间只给聚合（科室级），个人明细仅管理员（D3）。

前端落点：`BoardView.vue` 增设「分析统计」区（科室表格：被问次数 / 解决件数 / 解决率 / 回复时长中位数），全员可见聚合数据。

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
| 2026-10-04 | 一期立项：科室维度统计（被问次数/解决件数与占比/回复时间中位数），`/issues/department-stats` 规格定义 | 一期：数据分析与统计 |
| 2026-10-04 | 落地：`GET /issues/department-stats`（实测：总经理室 5/1、综合管理部 3/3）+ `BoardView` 分析统计区（科室表格，含解决率与回复时长 P50/均值） | 一期 |
| 2026-10-05 | 修看板页横排显示问题（`.fpim` flex 误用，见 ui-shell.md BUG-001） | ui-shell#BUG-001 |
