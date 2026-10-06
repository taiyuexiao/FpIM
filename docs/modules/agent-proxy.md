# 模块：私聊代理（R2，二期）

> 状态：🚧 R2 核心已落地（三模式/未读触发/代答/交接，实测通过）　｜　最近更新：2026-10-05

## 摘要

1-on-1 私聊的 Agent 自动代理：用户开启后（OFF/DRAFT/AUTO 三模式），**对方消息在用户未读期间**由 Agent 自主评估——
能处理就先处理（多轮推进、可调工具），不行就交接等待用户。禁止"用户没看到请稍后"式废话回复。

## 动机

用户必须需求 #2；附件 §6 全章是设计基准。**自建 IM 无平台阻塞**（附件对第三方 IM 的 R2 警告不适用于我们）：
私聊事件、已读游标（未读触发信号）、发送身份、人工接管全部自有。

## 范围与非范围

- 范围内：三模式开关（会话级配置+联系人白名单+时段）；未读触发（5s 等待窗口可调，已读即停）；决策器五动作
  （IGNORE/ANSWER/CLARIFY/EXECUTE/HANDOFF，附件 §9.1）；澄清≤2 轮；交接包；人工接管（control_epoch CAS）；
  「张三的 Agent 代处理」发送标识（principal_user_id + automation_actor_id）。
- 明确不做：长任务/定时任务（三期）；本地设备执行（三期，先用 agent-tools 的服务端工具）；跨租户。

## 上下游依赖

- 上游：agent-knowledge（代答素材）、agent-tools（可执行动作）、im 后端（消息/已读/接管）。
- 下游：通知（交接时通知本人，走小管家）、审计。

## 关键接口与运行时信息

| 资产 | 路径（规划） |
|---|---|
| 委托配置 | `PUT /api/v1/im/conversations/{cid}/delegation`（mode/contacts/tools/share_scope/revision） |
| 人工接管 | `POST /api/v1/im/conversations/{cid}/takeover`（原子递增 control_epoch） |
| 触发 | `im_service.send_message` 落库后的桥（复用 group-agent integration 形态，但私聊+未读条件） |

## 设计决策与假设

- **未读触发用现成游标**：`conversation_members.last_read_seq` 就是"用户是否看到"的权威信号；等待窗口内用户已读则不启动（附件 §6.2）。
- **沉默优于废话**：决策器无把握时 IGNORE（附件红线：不能把机械回复当代理）；DRAFT 模式下草稿只给本人看。
- **接管强保证**：发送与接管同库同进程，可实现"旧 epoch 消息绝不发出"（比附件对第三方的保证更强）。
- 执行前重检授权与控制权（附件 §13.5 伪码照用）。

## Bug 与问题记录

暂无。

## 已知限制与待办

- [ ] control_epoch 字段与 outbox 未建——当前接管语义=模式开关+已读即停（简单场景够用）；强保证版按附件 §11.3/§11.4 补。
- [ ] 「持续委托至完成」选项（已读后仍由 Agent 推进）后置。
- [ ] 多轮澄清（缺参追问）与决策器五动作完整版——当前为「命中即答/不命中沉默或交接」的三值决策。

## 变更历史

| 日期 | 变更 | 关联需求 / bug |
|---|---|---|
| 2026-10-05 | 二期立项：R2 设计定稿（模式/未读触发/决策器/接管） | 二期必须需求 #2 |
| 2026-10-05 | 代答/草稿成文升级为 DeepSeek 生成（同 agent-knowledge 的 answer_with_llm） | 二期 |
| 2026-10-05 | 落地 R2 核心：DDL 19（agent_delegations 三模式）+ `GET/PUT /im/conversations/{cid}/delegation` + 未读触发（5s 等待窗口，已读即停）+ 知识命中 auto 代答（`content.automation` 标识 + 前端「Agent 代处理」徽标）/ draft 走小管家草稿 / 无把握沉默或交接通知；HTTP 实测未读代答成功 | 二期必须需求 #2 |
