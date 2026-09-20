# 轻量级 IM 项目与自研可行性评估

## 轻量级开源项目

### JuggleIM —— 集成派首选 ✅
- 仓库：https://github.com/juggleim/im-server ★3553（Go 内核）、jugglechat-server ★52（业务 Demo）、imsdk-web ★91
- 活跃度：非常活跃，im-server 2026-09-17 当天有推送
- 协议：**Apache-2.0**，商用无限制
- 技术栈：Go，Protobuf + WebSocket；消息存 **MySQL**（可选 MongoDB）；自带管理控制台
- PC 形态：**Web SDK（纯 JS 无 UI，可直接在 Vue3 集成）**、Web Demo；桌面 SDK 未开源
- 能力：单聊/群聊/聊天室、离线消息、多端在线、已读、撤回、Webhook 事件推送
- 集成模型（关键优势）：**"IM 内核 + 自有业务后端"**——FastAPI 调其 Server API 注册用户/签 token，前端拿 token 直连 WebSocket；**内核无好友概念，免加好友单聊天然支持**；组织树/人员库完全留在自己库
- 部署：docker compose ≈ 2~3 个容器
- 风险：项目年轻（2024 年发布）、社区小；Web SDK 无 UI，聊天界面全自研

### LumenIM —— 不推荐但可参考 ⚠️
- https://github.com/gzydong/LumenIM ★1634（Vue3 + Naive UI）+ go-chat ★368（Go）
- 2025-10 后基本停更；**两仓库均无 LICENSE，商用有侵权风险**
- 价值：是"Vue3 + 薄 IM"的成熟样本，自研时可借鉴交互与表结构（仅借鉴思路）

### WuKongIM / 唐僧叨叨 —— 备选内核
- https://github.com/WuKongIM/WuKongIM ★4943，Apache-2.0，活跃；唐僧叨叨 ★3594
- Go，**内置存储单二进制零外部依赖**，部署最简；同为"内核+自有业务"模型
- 风险：v3 beta，API 和持久化格式可能变更

### HuLa —— 仅桌面客户端场景
- https://github.com/HuLaSpark/HuLa ★7718，Apache-2.0，活跃；Tauri + Vue3 桌面客户端，**Web 端官方不支持**；仿微信好友制需改造

### 其它
- Tailchat（★3623）：React 前端 + Discord 群组模型，双重不匹配，不推荐
- box-im（★684，MIT）：Java/Vue 仿微信好友制，仅作功能清单参考

## FastAPI 全自研 WebSocket IM 可行性

**现状**：backend 与 agent-service 的 requirements 均已有 `uvicorn[standard]`（自带 websockets），FastAPI 原生支持 WebSocket；项目内无现存 WS 代码，属全新开发。

**规模判断**：208 人、单聊为主，并发峰值 ≤100 长连接，单实例 uvicorn 轻松承载；多实例扩容加 Redis pub/sub 即可。技术可行性没有问题。

**真实成本在 IM 长尾细节**：可靠投递（ACK/重发/幂等）、离线拉取、已读回执、历史漫游、断线重连、多端同步。粗估单聊 MVP（发收+离线+已读+历史）**2~4 人周**，打磨到生产可用再加 2~4 周。

**自研的独特优势（与业务目标强相关）**：
- 消息直接落自己的 PostgreSQL → 提问/解决成果统计报表零数据打通成本
- 账号体系/组织树/"AI 搜人→进聊天"链路完全自控
- 可定义业务自定义消息类型（问题卡、解决确认、催办），与问题闭环状态机原生一体
- 不引入新语言栈和新组件

**风险**：团队无 IM 经验时易在消息可靠性上踩坑；后期上群聊/多端/音视频需返工。

## 对比结论

| 方案 | 结论 | 理由 |
|---|---|---|
| JuggleIM 内核 + Vue3 自研 UI | 推荐 | 协议干净活跃，集成模型与现状严丝合缝 |
| FastAPI 自研 | 推荐 | 报表/AI 链路/自定义消息零对接成本，规模完全可行 |
| WuKongIM | 可选 | 部署最简，v3 beta 是变数 |
| HuLa | 特定场景可选 | 仅当要桌面客户端 |
| Tailchat / 野火 / LumenIM | 不推荐 | 栈不符 / 协议坑 / 无协议停更 |
