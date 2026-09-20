# 模块：IM 数据层（`im` schema）

> 状态：✅ 稳定　｜　最近更新：2026-09-17

## 摘要

独立 schema `im`，承载 IM 内核的持久化：会话、会话成员（含已读游标）、消息、附件元数据。
另在 `public.issues` 上扩展 3 列，把「问题」与「会话」打通。

## 动机

1. **消息必须与问题同库同事务**——报表、闭环、人才画像全是 SQL 聚合；分库必然出现"报表数字 ≠ 聊天记录"。
2. **`public.sessions` / `public.messages` 已被 AI 问答占用**，IM 不能复用这两个表名，必须另起 schema。

## 范围与非范围

- 范围内：`im.conversations` / `im.conversation_members` / `im.messages` / `im.attachments`；`issues` 的 3 个扩展列；4 个关键唯一索引。
- 明确不做：**好友关系表**（本系统免加好友，任何两人可直接建单聊——反而要防引入好友体系）；**逐条消息回执表**（208 人规模下是纯浪费，用游标式已读替代）；超时/催办/升级相关字段（已从方案移除，见 `issue-loop.md`）。

## 上下游依赖

- 上游：PostgreSQL（Docker `pgvector/pgvector:pg17`）；`public.user2`（参与者 id 来源）、`public.issues` / `public.issue_events`（闭环打通）。
- 下游：[`im-backend.md`](im-backend.md)（ORM 模型 + 服务层）、[`issue-loop.md`](issue-loop.md)（`conversation_id` 关联）。

## 关键接口与运行时信息

### 关键文件

- **DDL（单一来源）**：`agent-service/scripts/ddl/08_im.sql`（111 行，幂等，可重复执行）
- SQLAlchemy 模型：`backend/app/models/im.py`

### 应用方式

```bash
docker exec -i swzr-pg psql -U swzr_admin -d fpim_dev -v ON_ERROR_STOP=1 \
  < agent-service/scripts/ddl/08_im.sql
```

### 表与关键索引

| 表 | 关键点 |
|---|---|
| `im.conversations` | `type` = `direct`/`group`；`direct_key` 单聊去重键（两 id 升序拼接）；`last_seq` 会话内序号分配器；`issue_id` 主问题锚点 |
| `im.conversation_members` | PK `(conversation_id, user_id)`；`last_read_seq`（可覆盖，供红点）；`unread_count`（冗余，免 COUNT）；`pinned`/`muted` |
| `im.messages` | `seq` 会话内严格递增（排序与增量拉取的唯一依据，**不用时间戳**）；`content` JSONB；`client_msg_id` 幂等键；`issue_id` |
| `im.attachments` | `sha256` 内容寻址；`rel_path` = `{yyyy}/{mm}/{sha前2位}/{sha256}.{ext}`；`ref_count` |

| 索引 | 作用 |
|---|---|
| `uq_conv_direct_key` | 单聊唯一（`WHERE direct_key IS NOT NULL`，群聊不受影响） |
| `uq_msg_conv_seq` | `(conversation_id, seq)` 唯一 |
| `uq_msg_client_idem` | `(sender_id, client_msg_id)` 唯一 → **消息幂等由数据库兜底**，应用层无需判重 |
| `uq_ev_read_per_actor` | `issue_events(issue_id, operator_id) WHERE event_type='read'` 唯一 → **首次已读不可篡改由数据库兜底** |

### 与问题闭环打通的 3 列（`public.issues`）

```
conversation_id     BIGINT       -- 该问题在哪聊的；发起会话时回填
first_read_at       TIMESTAMPTZ  -- 责任人首次看到（证据，永不覆盖）
first_response_at   TIMESTAMPTZ  -- 责任人首次回复（停"响应表"）
```

## 设计决策与假设

- **参与者统一用 `public.user2.id`（TEXT）**，与 `issues.user_id` / `assignee_person_id` 同源，**不做 id 转换**——避免引入一层映射带来的错配风险。
- **排序依据用 `seq` 而非 `created_at`**：同毫秒并发写入时时间戳会并列，序号能在单事务内严格递增。
- **已读有两处，语义不同，不能混用**（这是「只做已读未读」方案的关键）：
  - `conversation_members.last_read_seq` —— 供红点，**会被覆盖**；
  - `issue_events` 的 `read` 事件 —— 作为「责任人何时第一次看到」的**证据，永不覆盖**。
  - 用前者当证据 = 证据会被后续已读冲掉。详见 [`issue-loop.md`](issue-loop.md)。
- **`unread_count` 做冗余而非实时 COUNT**：会话列表是高频读，写入时增量维护成本远低于每次聚合。
- **附件内容寻址**：天然去重 + 秒传；同时把存储收敛为可替换接口，便于将来换对象存储（多实例时本地盘无法共享）。
- **群聊第一天就进数据模型**（`type='group'`），避免后期改表。

## Bug 与问题记录

暂无（DDL 已验证可幂等重复执行）。

## 已知限制与待办

- [ ] 消息全文检索首期用 `pg_trgm`；中文分词不依赖 DB 扩展，走 P3 应用层 jieba + 原生 tsvector。
- [ ] `im.attachments` 已有表但**上传链路尚未端到端验证**（`ref_count` 的自增/回收策略未定型）。
- [ ] 单聊与群聊的 `members` 表共用，`left_at` 退出语义已留但未实现退出流程。

## 变更历史

| 日期 | 变更 | 关联需求 |
|---|---|---|
| 2026-09-17 | 新建 `im` schema（4 表 + 4 索引）+ `issues` 扩展 3 列；在 `fpim_dev` 应用并验证幂等 | FpIM P0-a：IM 内核 |
