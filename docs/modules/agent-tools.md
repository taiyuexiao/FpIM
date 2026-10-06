# 模块：Agent 工具网关（R3，二期）

> 状态：🚧 二期半「ReAct 内核」已落地（10 轮循环 + 过程可见 + 本地执行节点 + MCP 网关）　｜　最近更新：2026-10-05

## 摘要

给 IM Agent 装上 coding-agent 式的工具调用：经 Tool Broker 受控执行文件/网络/业务工具（`file.search`、
`file.export`、`web.search`…），带授权、幂等、结果验证。核心场景："把本地名为 xxx 的文件发给对方"→ Agent 自主检索、消歧、发送、回报凭据。

## 动机

用户必须需求 #3；附件 §7/§14 是设计基准（本地文件完整流程、执行引擎红线）。
借鉴 dsh/codex/kimi-code 的工具接口与任务循环（附件 [S10–S13]）——但**不能把 coding agent 的默认终端权限暴露给群员**。

## 范围与非范围

- 范围内（二期）：Tool Broker（schema 校验/授权检查/幂等键/结果记录）；服务端文件工具（在 FPIM 文件库与服务器授权目录检索、导出、走 `im.upload` 发送）；`web.search`；工具结果结构化（status/result_ref/evidence/retryable，模型不可覆写）。
- 范围内（三期）：Local Companion 本地伴随程序（附件 §7 全套：配对/目录授权/安全打开/快照/上传凭据/设备离线排队）。
- 明确不做：任意 shell、浏览器写操作、多 Agent 子任务。

## 上下游依赖

- 上游：agent-proxy/group-agent（任务侧调用）、policy（授权）。
- 下游：im 文件通道（内容寻址上传=「已发送」凭据）、审计（ToolInvocation 记录）。

## 关键接口与运行时信息

| 资产 | 路径（规划） |
|---|---|
| 工具调用 | `POST /api/v1/tool-invocations`（严格 schema + 幂等键） |
| 工具定义 | `backend/app/agent_tools/`（file.search / file.export / web.search …） |
| 复用 | `group_agent` 的 ActionExecutor 接口形态（确认后执行） |

## 设计决策与假设

- **先结构化工具后 shell**（附件 §14.1）：文件查找不给 shell。
- **"已发送"必须有凭据**：消息 id/回执才算（附件 §7.2 红线：上传完成≠发送成功）。
- 幂等键稳定（`clientMsgId` 传统）；执行前重检授权与控制权。
- 工具返回与聊天内容都是不可信数据（提示注入防护，附件 §14.1）。

## ReAct 内核升级（二期半，2026-10-05）

对标 codex/zcode/deepseek-harness 的 agent 形态（用户拍板的权限观：**本地机器=用户自己的地盘，默认大权限**，危险操作强提示即可）：

- **循环**：3 轮 → **10 轮** ReAct 式函数调用（推理→调工具→观察→再决策），失败自纠错（实测：相对路径写错→模型改绝对路径重试成功）；
- **过程可见**：每步工具调用发「执行日志」小灰条（`🔧 shell_exec(...)` → `→ 完成：{ok:true}`），像 zcode 的执行面板；
- **本地执行节点**（`scripts/local_companion.py` 升级）：`fs.list/read/write` + `shell.exec`——在**用户自己的电脑**上执行，权限默认全开；
- **危险操作强提示闭环**：`rm -rf/drop table/格式化`等高危命令不自动执行 → 回 `needConfirm` + 风险说明 → 模型转告用户 → 用户回「确认执行」→ 模型带 `confirmed=true` 重试放行（实测 rm -rf 全流程）；
- **MCP 网关**（`app/mcp_gateway.py`）：MCP 协议客户端，接入的 server 工具自动注册为 `mcp__<server>__<tool>`；`.env` 配 `MCP_SERVERS` 即接（如官方 filesystem server）；
- 服务端红线不变：IM 服务端不暴露 shell；shell 只存在于用户本地节点。

**实测**（线上 150.158.164.254）：「在工作目录建 server-test.txt…然后 cat 验证」→ fs_write→shell_exec→报告，**3 秒**完成，文件真实落盘。

## Bug 与问题记录

### BUG-001 工具回包永久悬挂（跨事件循环 Future）（2026-10-05，已解决）

- 错误行为：WHEN agent 调用本地工具（fs/shell）THEN 回包不达，任务悬挂（实测 55s+ 无结果），模型干等。
- 期望行为：WHEN companion 回包 THEN 工具结果 SHALL 在亚秒级返回模型。
- 不可破坏的行为：companion 未连接时 SHALL 立即返回明确离线提示。
- 根因：`request_tool` 的同步桥**自建了事件循环**执行协程，而 ws 对象归 uvicorn 主循环所有——跨线程 `send_json`/`set_result` 都是未定义行为，Future 对方醒不过来。
- 解决方式：`_run_sync` 改为把协程投递到 **ws 所属主循环**执行（accept 时记录 `_main_loop`）；不再自建 loop。
- 验证方式：线上实测工具往返亚秒级（发出→执行→回包 <5s）；双端探针日志确认链路。

## 已知限制与待办

- [x] ~~ToolInvocation 表 + 预算~~ → 循环预算 10 轮已设；审计表随二期审计增强补。
- [ ] MCP 目前为客户端骨架 + 可配置接入；尚未内置常用 server 清单。
- [ ] web.search 工具未做（P1 后补）。
- [ ] companion 的 shell 无命令白名单（用户拍板：默认全开，靠危险确认兜底）。

## 已知限制与待办

- [ ] ToolInvocation 表 + 预算（工具步数/墙钟，附件 §9.2 初值）——当前工具为直调，审计表待建。
- [x] ~~Local Companion 配套~~ → 最小版已做（`scripts/local_companion.py`：授权目录/防逃逸/上传凭据）；短时签名令牌+在线撤销按附件 §12.3 在三期强化。
- [ ] `web.search` 与业务系统工具未做。

## 变更历史

| 日期 | 变更 | 关联需求 / bug |
|---|---|---|
| 2026-10-05 | 二期立项：R3 设计定稿（Tool Broker/文件工具/凭据语义） | 二期必须需求 #3 |
| 2026-10-05 | **ReAct 内核升级**：10 轮循环 + 过程小灰条 + 本地执行节点（fs/shell）+ 危险操作确认闭环 + MCP 网关骨架；修 BUG-001（跨循环 Future 悬挂）；线上实测 3 秒全链路 | 二期半 |
| 2026-10-05 | **工具调用升级为 DeepSeek 函数调用循环**（像 zcode/codex）：`get_tool_specs()`（file_search/file_send 的 OpenAI tools 规格）+ `make_tool_executor()` 执行器 + DeepSeekBrain 3 轮 tool_calls 循环；旧正则快路径移除（会误切自然语言）；实测"把部署验证手册这份文件发给我"→模型自主搜索→发送→回执凭据 | 二期 |
| 2026-10-05 | 落地切片 1：`app/agent_tools.py`（file.search 本地伴随优先→平台文件库回退；file.send 走 im 文件通道；「把名为 xx 的文件发给对方」意图解析；同名多版本消歧不猜）+ `ws/companion_gateway.py`（`/api/v1/ws/companion` 设备注册/请求路由）+ `scripts/local_companion.py`（授权目录边界/防逃逸/REST 上传）+ 面板与群 @Agent 链路接入；实测指令→搜到→发送→回消息凭据 | 二期必须需求 #3 |
