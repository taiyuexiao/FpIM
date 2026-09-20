# 模块：IM 后端内核（REST + WebSocket）

> 状态：✅ 稳定（HTTP 37 项 + WS 13 项自测全通过）　｜　最近更新：2026-09-17

## 摘要

IM 的服务端：13 个 REST 接口 + 1 个 WebSocket 网关。
自研（不用 JuggleIM / OpenIM / 野火），**决定性理由是消息必须与 issue 同库同事务**，否则报表口径必然与聊天记录对不上。

## 动机

领导要求把「找到人之后的线下邮件沟通」换成 IM。沟通要留痕、要能统计，所以消息不能落在外部 IM 系统的库里。

## 范围与非范围

- 范围内：会话（单聊去重 / 建群 / 拉人）、消息（发送 / 幂等 / 历史 / 增量 / 撤回）、已读游标、实时推送（ack / 广播 / 已读回执 / typing / presence）、附件上传下载、问题首次已读留痕。
- 明确不做：**多实例横向扩展**（当前为单实例内存 Hub，多实例需加 Redis pub/sub）；**消息编辑**；**音视频通话**；**超时提醒与升级调度器**（已从方案移除）。

## 上下游依赖

- 上游：[`im-database.md`](im-database.md)、`public.user2`（人员姓名/头像）、`public.issues`（关联问题）、`backend/app/middleware/deps.py`（`get_current_user`、`get_db`）。
- 下游：[`im-frontend.md`](im-frontend.md)（REST + WS 消费方）、[`issue-loop.md`](issue-loop.md)（问题状态随消息联动）。

## 关键接口与运行时信息

### 关键文件

| 文件 | 行数 | 职责 |
|---|---|---|
| `backend/app/models/im.py` | 90 | 4 张表的 ORM 模型 |
| `backend/app/services/im.py` | ~700 | **全部业务逻辑**（REST 与 WS 共用同一服务层），含立项与解决确认 |
| `backend/app/api/v1/im.py` | ~290 | REST 路由 + 附件上传/下载 |
| `backend/app/ws/im_gateway.py` | 263 | WS 网关：`Hub` + 帧分发 |
| `backend/app/models/issue.py` | — | ⚠️ IM 加的 3 列（`conversation_id` 等）**必须在此同步声明**，否则走 ORM 的既有接口会 500（见 issue-loop.md BUG-001） |

### REST 接口（前缀 `/api/v1/im`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/conversations` | 我的会话列表（带 lastMessage / unreadCount / peer） |
| POST | `/conversations/direct` | **取或建单聊**（免加好友） |
| POST | `/conversations/group` | 建群（上限 100 人） |
| GET | `/conversations/{cid}` | 会话详情 |
| POST | `/conversations/{cid}/members` | 群聊拉人 |
| GET | `/conversations/{cid}/messages` | 历史 / 增量（`beforeSeq` / `afterSeq` / `limit`） |
| POST | `/conversations/{cid}/messages` | **HTTP 兜底发消息**（WS 不可用时） |
| POST | `/conversations/{cid}/read` | 推进已读游标 |
| DELETE | `/messages/{mid}` | 撤回（2 分钟内） |
| GET | `/conversations/{cid}/issues` | 会话关联的问题 + 时间线 |
| POST | `/conversations/{cid}/issues` | **会话内立项**（广播 issue_card 给会话成员） |
| POST | `/issues/{iid}/read` | 问题首次已读留痕（不可覆盖） |
| POST | `/upload` · GET | 附件上传（内容寻址）/ 下载（`/files/{rel_path:path}`） |

### WebSocket

- 端点：**`/api/v1/ws/im?token=<JWT>`**（token 走 query，浏览器 WS 不能自定义 header）
- 上行帧：`send` / `read` / `typing` / `ping`
- 下行帧：`ready` / `ack` / `message` / `read` / `typing` / `presence` / `pong` / `error`
- 鉴权失败以 `4401` 关闭。
- **REST 侧的广播**：`POST .../issues`（立项卡）与 `PATCH /issues/{id}`（resolve_confirm）直接从 REST handler `await hub.send_to_users(...)` 推给其他成员；Hub 与 `_load_member_ids` 从 `ws/im_gateway` 导入，无循环依赖。

### 关键实现要点

- **单聊去重不需要分布式锁**：`get_or_create_direct()` 用 `direct_key`（两个 user_id 升序拼接）+ `ON CONFLICT DO UPDATE ... RETURNING` 一步完成"查或建"。
- **seq 在事务内分配**：`UPDATE conversations SET last_seq = last_seq + 1 ... RETURNING last_seq`，保证单会话内单调。
- **幂等靠唯一索引**：`uq_msg_client_idem`，重复提交返回已存在的那条，响应带 `created: false`（WS `ack` 同）。
- **WS 与 REST 走同一服务层**：WS 只是传输壳，业务语义完全一致，不存在两套逻辑分叉。
- **消息自动挂接活跃问题**：`send_message` 未显式带 `issue_id` 时，若会话锚点指向 `processing` 状态的问题则自动挂接（"过程即数据"的关键，见 issue-loop.md）。
- **系统消息**：`sender_id='system'`（该列 NOT NULL 不能真空），成员校验放行但只允许 `system/resolve_confirm/report_card` 类型；resolve_confirm **不带** `client_msg_id`（重开→再解决是合法重复事件，不能被幂等键吞掉）。

### 配置与环境变量

| 变量 | 用途 | 默认 |
|---|---|---|
| `DATABASE_URL` | 数据库（独立开发用 `fpim_dev`） | 见 `backend/.env` |
| `FPIM_FILE_ROOT` | 附件物理存储根目录 | `/tmp/fpim-files`（开发） |
| `CORS_ORIGINS` | 允许的前端来源，**换端口必须同步加** | `http://localhost:5173,http://localhost:5174` |

### 如何运行与验证

```bash
# 起服务（独立开发实例，不碰正在跑的 8001）—— 口令不入库，从 backend/.env 取
cd backend
DATABASE_URL="postgresql://swzr_admin@localhost:5432/fpim_dev" \
  PGPASSWORD="<数据库口令，见 backend/.env>" \
  FPIM_FILE_ROOT=/tmp/fpim-files \
  CORS_ORIGINS="http://localhost:5173,http://localhost:5174,http://localhost:5175" \
  venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8002

# 自测（脚本已固化进仓库）
venv/bin/python scripts/fpim_smoke_http.py --reset   # 37 项（含立项闭环）
venv/bin/python scripts/fpim_smoke_ws.py             # 13 项
```

## 设计决策与假设

- **自研而非集成 JuggleIM**：`D1`。集成派的优势是省事，但会把消息放进 MySQL，报表必须维护同步管道。**D1 与「小管家在 IM 内推报表」这条需求是绑定的**——只有自研才两全。
- **不做逐条消息回执**：游标式 `last_read_seq` 已足够表达"读到哪"，208 人规模做逐条回执是纯开销。
- **WS 只做实时，历史/上传仍走 REST**：避免在 WS 上自造二进制分片协议。
- **`_msg_dict_from_row` 统一消息序列化**：REST 与 WS 共用，保证两端字段完全一致——**代价是所有查询的列清单必须与它对齐**（见 BUG-001）。

## Bug 与问题记录

### BUG-001 会话列表 500：最后一条消息的列清单与序列化函数不匹配（2026-09-17，已解决）

- 错误行为：WHEN 调 `GET /im/conversations` THEN 服务端抛 `IndexError`，会话列表 500。
- 期望行为：WHEN 同一请求 THEN 系统 SHALL 返回会话列表，且每条的 `lastMessage` 字段完整。
- 不可破坏的行为：WHEN 任何路径构造消息 dict THEN 系统 SHALL CONTINUE TO 通过 `_msg_dict_from_row` 统一序列化，REST 与 WS 返回的消息结构保持一致。
- 根因：会话列表里"批量取每会话最后一条消息"的 SQL 只 `SELECT` 了 7 列，却复用了按 10 列（含 `client_msg_id` / `reply_to_id` / `issue_id`）设计的 `_msg_dict_from_row`。
- 解决方式：改 `backend/app/services/im.py` 的 `list_conversations()`，SQL 列清单补齐并对齐顺序，并在该查询上加了注释说明约束。
- 验证方式：`scripts/fpim_smoke_http.py` 第 9 组断言（会话出现在列表 / 最后一条消息已带出 / 未读为 1）全绿。

### BUG-002 后台服务进程随 shell 结束被回收（2026-09-17，已解决）

- 错误行为：WHEN 用 `nohup ... &` 在一条命令里启动 uvicorn THEN 该 shell 退出后服务随即消失，端口空出。
- 期望行为：WHEN 启动开发服务 THEN 服务 SHALL 持续存活到显式停止。
- 不可破坏的行为：WHEN 重启开发服务 THEN 系统 SHALL CONTINUE TO 使用独立端口（8002），不影响正在运行的 8001 实例。
- 根因：非交互式运行下进程随命令结束被回收。
- 解决方式：改用后台任务方式常驻启动。
- 验证方式：启动后隔 6 秒再 `curl /health`，返回 `{"status":"ok"}`。

## 已知限制与待办

- [ ] **单实例假设**：`Hub` 的在线连接表在进程内存里。扩多实例需引入 Redis pub/sub 做扇出。
- [ ] **typing 未节流**：客户端每次输入都发帧，群聊 100 人场景需加节流。
- [ ] 上传大小上限、`ref_count` 回收策略未定型。
- [ ] `presence` 目前是"连上/断开广播"，未做离线延迟判定。
- [ ] 撤回只校验 2 分钟窗口，未校验"仅发送者本人"以外的规则（当前逻辑见 `revoke_message()`）。

## 变更历史

| 日期 | 变更 | 关联需求 / bug |
|---|---|---|
| 2026-09-17 | 新建 IM 内核：12 REST + WS 网关 + 服务层；`main.py` 注册路由与 `08_im.sql` 启动自检 | FpIM P0-a |
| 2026-09-17 | 修 BUG-001（列清单不匹配）、BUG-002（进程回收） | BUG-001 / BUG-002 |
| 2026-09-17 | 自测脚本固化进仓库 `backend/scripts/fpim_smoke_{http,ws}.py` | — |
