# 模块：小管家（IM 内通知系统号）

> 状态：🚧 首期已通（立项/解决两个触发点）　｜　最近更新：2026-09-18

## 摘要

「小管家」是 IM 内的通知系统号（`user2.id='system'` 的 bot 行）。所有系统通知都进它跟每个用户的**那一栏固定单聊**——立项、解决结论先走这里，后续报表周报也走这里（决策 D6：推送渠道 = 小管家，不上短信/邮件）。

## 动机

责任人不一定会盯着业务会话——立项后他需要一个"被点名"的入口。企业 IM 的惯例是系统号一栏收纳全部通知，我们也照这个做。

## 范围与非范围

- 范围内（已做）：bot 用户行、`notify_user()` 服务、立项→通知责任人、解决→通知责任人、实时广播。
- 明确没做：**周报/报表卡推送**（需要调度器，report_card 消息类型已预留）；用户侧"通知设置"（免打扰）。

## 上下游依赖

- 上游：user2 的 bot 行（`10_bot_user.sql`）、im 服务层（`send_message` 的 SYSTEM_SENDER 约定）。
- 下游：会话列表（小管家作为 peer 出现，未读数正常累计）。

## 关键接口与运行时信息

| 资产 | 说明 |
|---|---|
| `user2` bot 行 | `id='system'`, `account='sysbot'`, `active=false`（登录被拒 + 名片库隐藏，纯后台发送者） |
| `im_service.notify_user(db, user_id, text, issue_id)` | 取或建 bot↔user 单聊（`direct_key` 去重，天然一人一栏）+ 插 system 消息；返回 (msg, cid) |
| 触发点 1 | `create_issue_in_conversation`：立项 → 通知责任人（响应体带 `notify`，REST handler 广播） |
| 触发点 2 | `insert_resolve_confirm`：解决/未解决 → 通知责任人（同上） |

### 关键约束

- **一人一栏**：通知不进业务会话（那里放 issue_card/resolve_confirm），进 bot 单聊；`direct_key('system', uid)` 去重保证永远同一栏。
- **bot 不能登录**：`active=false` 被登录接口的 `if not user.active: 403` 挡住；同时 `list_people` 过滤 `active=true` 自动把 bot 从名片库隐藏——不用写额外排除逻辑。
- WS 广播由 REST handler 做（`notify.toUserId`），service 层只管落库。

## 设计决策与假设

- **通知不做"已读回执"类追踪**：小管家消息只供人看；问题的"首次已读留痕"仍走业务会话的 `record_issue_read`，二者无关。
- 用户在 bot 会话里可以直接回复（技术上）——没人读，但不拦截；后续如需可加"该会话为通知栏"的只读提示。

## Bug 与问题记录

暂无（首期自测 7 项全过）。

## 已知限制与待办

- [ ] 报表周报推送（`report_card` 消息类型 + 调度器）。
- [ ] 通知免打扰设置。
- [ ] bot 会话里用户回复的兜底提示（"这里是通知栏"）。

## 变更历史

| 日期 | 变更 | 关联需求 / bug |
|---|---|---|
| 2026-09-18 | bot 用户行（10_bot_user.sql）+ `notify_user` + 立项/解决两个触发点 + 广播；自测 §24 七项 | PRD F10 前置 / 决策 D6 |
