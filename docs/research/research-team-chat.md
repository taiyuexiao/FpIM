# Rocket.Chat / Mattermost / Zulip 对比调研

三家 2026-09-17 当天均有提交，无停更风险；均有 Web 端 + 官方 Electron 桌面端（Win/Mac/Linux）。

| 维度 | Rocket.Chat | Mattermost | Zulip |
|---|---|---|---|
| Star | 46,130 | 39,082 | 25,915 |
| 协议 | MIT + ee/ 专有目录，免费功能持续收缩 | 官方二进制 MIT，自编译 AGPLv3 | **Apache-2.0 全量** |
| 服务端 | Node.js (Meteor) + **MongoDB** | Go + **PostgreSQL** ✅ | Python (Django) + **PostgreSQL** ✅ |
| 部署复杂度 | app + Mongo 副本集（内存 4GB+） | 最简（server + PG，2 组件） | 最重（~5 容器，PG 需 pgroonga，不能复用现有实例） |
| 已读回执 | **Premium 付费** | 无原生（社区插件） | **免费内置** |
| 免费 SSO | 收紧中（9.0 起 LDAP/SAML 需 Premium） | **免费版仅剩邮箱密码** | **免费 SAML/OIDC/LDAP/SCIM** |
| 用户上限风险 | 无 | **v11 免费版 250 人上限**（208 人踩线） | 无 |
| 嵌入现有门户 | **最成熟**（`?layout=embedded` iframe SSO + JS SDK） | v10.7 起可配 frame-ancestors | 无官方嵌入模式 |
| 用量统计 | Engagement Dashboard 付费 | 弱 | **自带免费 /stats 分析页** |
| 移动推送 | 社区版 1 万条/月 | 有额度限制 | >10 用户需付费（PC 优先可忽略） |

## 与本项目的匹配点

- 三家都**没有**飞书式组织树通讯录，只有用户目录 + 自定义字段——需保留现有 Vue3 组织树页面，API 同步人员，深链直起单聊（RC `/direct/<username>`、MM `/@<username>`、Zulip DM narrow URL）
- "AI 搜人 → 直接进聊天"三家都能用 API 创建 DM + 深链实现
- 消息落库做报表：Mattermost/Zulip 是 PG 可直接 SQL；Rocket.Chat 在 Mongo 需另建管道

## 结论

- **Zulip 可选**：协议最干净、PG 栈一致、免费 SSO + 已读回执 + 统计页；代价是部署最重、内嵌要绕、话题模型有学习成本
- **Rocket.Chat 可选**：形态最像飞书、嵌入最成熟，但已读回执/统计付费、Mongo 割裂、免费范围逐年收缩
- **Mattermost 不推荐**：250 人上限 + 无 SSO + 无已读回执 + 自编译 AGPLv3

共同问题：三家都是"团队聊天工具"产品形态，与"AI 搜人 → 问题闭环 → 人才报表"的业务纵深整合仍需大量外围开发，聊天内核之外的差异化价值（状态机、催办、报表）都得自己做。
