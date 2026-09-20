---
type: contents
id: content-C00314
title: Agent Tracing：用一条 Trace 还原 Agent 为什么失败
version: 2
status: published
visibility: internal
sensitivity: 0
source_type: public.contents
source_id: C00314
source_uri: public.contents/C00314
owner_department_id: 4
updated_at: 1789519092.356719
content_hash: 1ecf9d0a1912b67b7b0d85bf3efccfeb6279de5fd2b0c27a16766684ba8f36ac
extra:
  author_person_id: P0001
  tags: []
---

Agent Tracing：用一条 Trace 还原 Agent 为什么失败

图片 线上告警只有一行： 提示词 2026-08-03T10:14:22Z ERROR tool call failed 它说明某个工具失败了，却没有告诉我： Agent 当时读取了哪份资料； 模型选择了哪个动作； 失败的是第一次调用还是重试； 写操作是否已经在外部系统生效； 接管任务的新 Worker 是否沿用了同一个执行上下文； 当时运行的是哪个 Prompt、工具合同和策略版本。 如果任务只是一次普通函数调用，多加几行日志也许就够了。但 Agent 会检索、调用模型、选择工具、等待审批、重试和恢复，一行行日志很快变成一堆缺少因果关系的碎片。 这时需要的不是“记录更多文字”，而是 Agent Tracing：把一次端到端任务拆成有父子关系的工作单元，并为每一步保留足以排障、复现和审计的证据。 本文是 AI Agent 工程进阶 第 7 篇。上一篇 Durable Loop 已经让 Agent 能在重启、重试和取消后继续正确运行；这一篇继续回答：它恢复以后究竟走过哪条路径，第一次失败在哪里，我们又凭什么相信这次重试是安全的。

作者:刘成彦
