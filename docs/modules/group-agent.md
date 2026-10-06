# 模块：群聊 Agent 网关（Cowork / 外部 IM 接入）

> 状态：🚧 MVP 已落地　｜　最近更新：2026-09-26

## 摘要

把“群聊中的 Agent”做成独立的平台无关能力：接收任意 IM 的群聊事件，识别 `@agent` / `/agent` 触发，调用可替换 Agent Brain 生成回复和待确认动作，再通过统一出口回写当前 FpIM 群聊或外部 IM。

本模块解决的是上一轮明确的产品缺口：当前群聊只有人与人协作，没有 Claude Code cowork / 飞书群 Agent 的“自动参与群聊上下文”能力。

## 动机

1. **复用价值**：群聊 Agent 的事件协议、动作确认、工具边界不应绑定 FpIM 的 `im.messages`。
2. **安全边界**：Agent 只能读上下文、产草稿、提建议；任何业务写入（立项、改状态）必须人工确认后由 backend 执行。
3. **多 IM 接入**：飞书、企业微信、Slack 等可以通过 webhook/HTTP 接入同一套能力，不必复制 Agent 内核。

## 范围与非范围

- 范围内：平台无关事件模型、@/slash 触发、上下文摘要、问题草稿、通用 HTTP API、回调式外部 IM 接入、当前 FpIM 群聊桥接、动作确认接口。
- 明确不做：Agent 自动修改 `issues.status`、未经确认直接发业务消息、群聊成员管理、音视频、复杂多 Agent 调度、跨实例动作持久化。

## 关键接口与运行时信息

### 代码位置

| 资产 | 路径 |
|---|---|
| 通用契约 | `/Users/shipeilin/projects/mine/FpIM/findperson/backend/app/group_agent/contracts.py` |
| 可替换 Brain | `/Users/shipeilin/projects/mine/FpIM/findperson/backend/app/group_agent/brains.py` |
| 编排服务 | `/Users/shipeilin/projects/mine/FpIM/findperson/backend/app/group_agent/service.py` |
| 当前 FpIM 适配器 | `/Users/shipeilin/projects/mine/FpIM/findperson/backend/app/group_agent/adapters.py` |
| FpIM 群聊桥接 | `/Users/shipeilin/projects/mine/FpIM/findperson/backend/app/group_agent/integration.py` |
| 外部 IM HTTP API | `/Users/shipeilin/projects/mine/FpIM/findperson/backend/app/api/v1/group_agent.py` |

### 当前 FpIM 群聊接入

1. 用户在群聊发普通文本消息；
2. `im_service.send_message()` 落库后调用 `group_agent.integration.handle_im_message()`；
3. 只有群聊且命中 `@agent` / `@小管家` / `/agent` / `/ask` 才会触发；
4. `FpIMReplySink` 将回复写回同一 `im.messages`，复用现有 WebSocket/REST 广播；
5. Agent 回复使用 `sender_id='group-agent'`，前端显示为“群聊 Agent”。
6. `FpIMReplySink` 通过 `Hub.send_to_users_sync()` 将回复推给在线成员；离线成员下次拉取历史即可看到。

### 外部 IM HTTP API

配置 `GROUP_AGENT_API_KEY` 后，外部 IM 使用 `X-Group-Agent-Key` 调用：

```http
POST /api/v1/group-agent/events
X-Group-Agent-Key: <key>
Content-Type: application/json

{
  "source": "feishu",
  "conversationId": "oc_123",
  "messageId": "m_456",
  "senderId": "u_1",
  "senderName": "张三",
  "text": "@agent summarize",
  "context": [
    {"senderId": "u_1", "text": "登录失败", "createdAt": "2026-09-26T10:00:00Z"}
  ],
  "replyUrl": "https://im.example.com/group-agent/callback"
}
```

响应：

```json
{
  "handled": true,
  "runId": "run-...",
  "traceId": "trace-...",
  "replies": [{"text": "...", "kind": "text", "actions": []}]
}
```

其他端点：

- `GET /api/v1/group-agent/capabilities`：能力发现；
- `GET /api/v1/group-agent/actions/{actionId}`：读取动作；
- `POST /api/v1/group-agent/actions/{actionId}/confirm`：确认动作，确认后才执行业务写入。

`replyUrl` 可选；配置后额外投递 `group_agent.reply` 回调，适配只支持 webhook 的 IM。

### 触发与命令

| 触发 | 说明 |
|---|---|
| `@agent` / `@小管家` / `@群聊 Agent` | 默认触发 |
| `/agent ...` / `/ask ...` | 命令式触发 |
| `triggerMode="always"` | 外部 IM 可显式要求每条消息都处理 |
| `/agent summarize` | 总结上下文 |
| `/agent draft-issue <问题>` | 生成立项草稿动作 |
| `/agent help` | 查看能力 |

## 设计决策与假设

- **Brain 可替换**：默认 `HeuristicBrain` 无外部依赖；配置 `GROUP_AGENT_USE_AGENT_SERVICE=true` 时优先调用现有 `agent-service`，失败自动降级，IM 主链不依赖 AI。
- **动作必须确认**：`create_issue` 等动作先生成 `AgentAction`，调用 `/actions/{id}/confirm` 后才执行；群聊立项仍要求唯一责任人。
- **回复是服务消息，不是登录用户**：`group-agent` 不进入 `user2`、名片库、登录系统，避免伪造人类成员。
- **事件幂等**：`source + conversationId + messageId` 去重，外部 IM 重投不会重复回复。
- **当前动作执行器只覆盖 `create_issue`**；其他工具通过 `ActionExecutor` 接口扩展。

## Bug 与问题记录

### BUG-001 桥接自 MVP 起从未触发（导入路径 + 键名双错）（2026-10-05，已解决）

- 错误行为：WHEN 用户在群聊发普通文本消息 THEN 群 Agent 桥接**静默不触发**（无代答、无 @Agent 响应）。
- 期望行为：WHEN 消息命中触发条件 THEN SHALL 进入 GroupAgentService/知识代答流程。
- 不可破坏的行为：WHEN 桥接自身异常 THEN SHALL CONTINUE TO 不影响用户原消息发送（既有 try/except 兜底保留）。
- 根因（两个叠加，都被兜底 except 静默吞掉）：① `services/im.py` 里 `from .group_agent...` 相对导入少一层（应为 `..group_agent`）→ ModuleNotFoundError；② 桥接读 `message.get("msg_type")` 等蛇形键，但消息字典是驼峰（`_msg_dict_from_row` 输出 `msgType`/`senderId`/`conversationId`）→ 守卫恒真直接 return。**单测绕过了真实链路（直接喂蛇形 dict 给 handle_im_message），所以 3 个用例全绿也掩盖了它——教训：MVP 必须有一条走真实调用链的集成测试。**
- 解决方式：导入改 `..group_agent`；`integration.handle_im_message` 入口加 `_norm()` 统一两种键名；`agent_proxy` 同步适配。
- 验证方式：HTTP 实测——群内 @知识库主人触发代答、@Agent 触发工具执行；`fpim_smoke` 57/57 + 13/13。

## DeepSeek 大脑 + 全会话常驻（2026-10-05）

- **所有 Agent 能力的默认大脑 = DeepSeek**（用户决策）：`DeepSeekBrain`（OpenAI 兼容 chat/completions，失败自动降级启发式）；
  `build_brain` 优先级 DeepSeek > agent-service（兼容路径）> 启发式。key 在 `.env`（gitignore），仓库只留占位符。
- **只要有会话就有 Agent**（群+单聊）：① 会话成员列表常驻「群聊 Agent」卡（`isAgent`，不可踢/不可转让/不可当责任人）；
  ② 输入 `@` 候选首位是 Agent；③ 输入框工具栏 🤖 一键召唤（填入 `@群聊 Agent`）；④ 裸召唤（无正文）→固定问候「我在，有何吩咐」。
- 知识代答/私聊代答的成文也走 DeepSeek（`answer_with_llm`：知识材料作上下文、必须注明依据、未覆盖部分说明缺口；失败回退确定性拼接）。

## 二期扩展（R4，2026-10-05 立项）

## 已知限制与待办

- [ ] 动作存储目前在进程内存；多实例部署需迁移到数据库或共享存储。
- [ ] 外部 IM 的签名验签尚未接入，当前使用独立 API Key；接入企业 IM 时应增加 HMAC/平台签名。
- [ ] `HttpAgentBrain` 解析 AGUI/agent-chat SSE；agent-service 不可用时只降级到启发式回答。
- [ ] 暂无前端动作确认卡片；当前通过 API 确认。
- [ ] 暂未接入 @提及成员解析，`mentions` 可由外部 IM 直接传入。

## DeepSeek 大脑 + 全会话常驻（2026-10-05）

- **所有 Agent 能力的默认大脑 = DeepSeek**（用户决策）：`DeepSeekBrain`（OpenAI 兼容 chat/completions，失败自动降级启发式）；
  `build_brain` 优先级 DeepSeek > agent-service（兼容路径）> 启发式。key 在 `.env`（gitignore），仓库只留占位符。
- **只要有会话就有 Agent**（群+单聊）：① 会话成员列表常驻「群聊 Agent」卡（`isAgent`，不可踢/不可转让/不可当责任人）；
  ② 输入 `@` 候选首位是 Agent；③ 输入框工具栏 🤖 一键召唤（填入 `@群聊 Agent`）；④ 裸召唤（无正文）→固定问候「我在，有何吩咐」。
- 知识代答/私聊代答的成文也走 DeepSeek（`answer_with_llm`：知识材料作上下文、必须注明依据、未覆盖部分说明缺口；失败回退确定性拼接）。

## 二期扩展（R4，2026-10-05 立项）

- 群 @ 询问处理升级：接入知识库代答（agent-knowledge）与工具调用（agent-tools）；跨会话检索用 `/im/messages/search`（天然 ACL：只搜我参与的会话）+ **披露检查**（能读≠能分享给当前受众，附件 §8.1 红线）。
- 多 Agent 抢答：问题归属记录防止同时回复（不能只靠提示词谦让，附件 §5.2）。
- 触发扩展：除 @ 外支持「@委托人或回复其消息」与「专业域主动参与」（介入决策层见 agent-proxy 的决策器，两处共用）。

## 变更历史

| 日期 | 变更 | 关联需求 / bug |
|---|---|---|
| 2026-09-26 | 新增群聊 Agent 网关、FpIM 群聊桥接、外部 IM HTTP API、动作确认接口与契约测试 | 群聊 Agent / Cowork MVP |
| 2026-10-05 | 修 BUG-001（桥接双错致从未触发）；桥接接入 R1 知识代答与 R3 文件工具钩子 | BUG-001 / 二期 |
| 2026-10-05 | DeepSeek 接入（所有 Agent 能力的默认大脑）+ Agent 全会话常驻（成员卡/@ 候选/🤖 召唤/裸召唤问候）；冒烟断言同步更新（人类成员 4 人 + Agent 在场，58/58） | 二期 |
| 2026-10-05 | 修「艾特之后没反应」（用户反馈）：① **@真人必有响应**——命中其知识 LLM 代答，未命中且像提问→实质交接+小管家提醒本人（此前未命中知识就静默）；② 触发词归一化（`@群聊Agent`/`@Agent` 大小写与空格不敏感，event.mentions 兜底）；③ MessageComposer 补 **IME 回车防护**（中文输入法确认回车不再误发截断/空正文，此前问答侧有防护而消息侧遗漏）。实测：@真人交接响应、无空格触发 DeepSeek 总结均通过 | 二期 |
