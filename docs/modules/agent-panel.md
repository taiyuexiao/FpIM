# 模块：Agent 交互面板（右侧 LLM 面板，二期）

> 状态：🚧 切片 1 已落地（同步对话+双 tab，实测通过）　｜　最近更新：2026-10-05

## 摘要

会话页右栏可展开为 LLM 交互面板（参考飞书右侧「豆包工作」）：在任意会话里与 Agent 自然语言交互——
问历史、跨会话检索、生成处理建议/模板、发起任务；与「问题详情」面板并列切换。

## 动机

用户需求：右侧边栏在 AI 场景下展开为 LLM 交互面板。Agent 内核（group-agent 的 brain 可替换架构）已就位，
面板是它的第二个入口（第一个是群内 @）。

## 范围与非范围

- 范围内：右栏「问题详情 / AI 助手」双 tab；对话流（引用当前会话上下文）；流式回复（SSE/WS）；
  动作确认卡（复用 group-agent 的 AgentAction）；沉淀模板入口（把 AI 结论存为模板）。
- 明确不做：多 Agent 会话管理、任务中心全量 UI（三期随长任务）。

## 上下游依赖

- 上游：group-agent（brain/service 复用）、agent-knowledge（模板）、agent-tools（工具）。
- 下游：im 会话（引用/发送回会话）、问题闭环（发起立项草稿）。

## 关键接口与运行时信息

| 资产 | 路径（规划） |
|---|---|
| 面板会话 | `POST /api/v1/agent/chat`（SSE 流式；context 带当前会话 id） |
| 前端 | `src/components/im/AgentPanel.vue`，IssueSidePanel 旁 tab 切换 |

## 设计决策与假设

- **同一个 Agent 内核**：面板与群 @走同一 GroupAgentService（brain 可替换），不另起一套。
- 面板里的写动作仍要确认（ActionExecutor 红线）。
- 面板对话不进 `im.messages`（不是群聊留痕），单独存 agent 对话表或内存——留痕边界在开发时定（倾向单独表+审计）。

## Bug 与问题记录

暂无。

## 已知限制与待办

- [ ] 流式输出通道选型（SSE vs WS 复用）；切片 1 为同步 JSON。
- [ ] 面板对话持久化表（切片 1 前端内存态，刷新丢失）。
- [ ] 动作草稿卡的确认执行链（复用 ActionExecutor）与「沉淀为模板」入口。

## 变更历史

| 日期 | 变更 | 关联需求 / bug |
|---|---|---|
| 2026-10-05 | 二期立项：面板设计（双 tab 内核复用） | 二期：右侧面板 |
| 2026-10-05 | 落地切片 1：`POST /api/v1/agent/chat`（复用 build_brain/BrainRequest，带会话上下文，降级启发式）+ `AgentPanel.vue`（对话流/动作草稿卡）+ ChatView 右栏双 tab（问题详情/AI 助手）；实测问答返回责任人推荐 | 二期 |
