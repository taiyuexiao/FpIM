# 模块：Agent 知识与解决模板（二期）

> 状态：🚧 模板沉淀 + R1 知识库代答均已落地（实测通过）　｜　最近更新：2026-10-05

## 摘要

二期 Agent 能力的"知识供给层"：① 用户**预提供知识库**给 Agent（个人库 + 可分享集合），群里命中专业域时代答；
② 问题解决后**沉淀为处理模板**（人工/Agent 发送，个人库与公共库双层），首问检索时与责任人一起返回。

## 动机

用户必须需求 #1（知识库代答）与「模板沉淀」需求；附件（IM-Agent 产品文档）§5 的知识接入与证据要求是设计基准。
差异化：首问平台本来就有 faqs/知识沉淀链路——模板是它的"可转发形态"。

## 范围与非范围

- 范围内（一期切片）：`issue_templates` 表（来源问题/解答/标签/可见性/责任人）；由已解决问题一键沉淀；模板卡片消息（人工发送到会话）；`/templates/match` 检索（首问问答页与 Agent 共用，返回"模板+责任人"）。
- 范围内（二期后续）：知识库绑定（个人知识文档集→授权分享给群）；Agent 代答时自动选模板发送（经动作确认）；模板使用统计回流帮助榜。
- 明确不做：向量索引重建（模板检索先 ILIKE/关键词，量大再入 RAG 空间）；模板版本树（一模板一现行版）。

## 上下游依赖

- 上游：issue-loop（解决确认后沉淀）、faqs（沉淀候选既有链路，模板是平行新表不合并）。
- 下游：agent-proxy/group-agent（代答素材）、AskView（首问检索展示模板卡）、stats-board（模板使用口径后续）。

## 关键接口与运行时信息

| 资产 | 路径 |
|---|---|
| DDL | `findperson/agent-service/scripts/ddl/17_issue_templates.sql` |
| API | `backend/app/api/v1/templates.py`（promote/list/match/send） |
| 消息类型 | `template`（content: {templateId,title,question,solution,ownerName}） |

## 设计决策与假设

- **模板与 faqs 不合并**：faqs 是"平台沉淀的标准答案"（管理员审核链），模板是"处理套路+责任人"的可转发卡片，语义不同；两边都可被检索命中。
- **可见性两级**：private（个人库，默认）/ public（公共库，全员可转发）；沉淀时选择。
- **检索联动走接口不改 agent-service**：`/templates/match` 由前端问答页与 Agent 共同调用，避免动智能内核（它只读只推理的边界不动）。
- **发送留痕**：模板卡片作为 `im.messages` 的 template 消息进入会话（同库留痕），不走旁路。

## Bug 与问题记录

暂无。

## 已知限制与待办

- [ ] 模板匹配目前关键词 ILIKE；模板多了再接 RAG（进 512 维 Concept 空间还是 1536 维 RAG 空间——**不合并双向量空间**，接入时定）。
- [x] ~~知识库绑定~~ → **已做**（R1，见上）；Agent 自动选模板发送仍待做（经动作确认）。
- [ ] 使用次数统计进画像/帮助榜口径。

## 变更历史

| 日期 | 变更 | 关联需求 / bug |
|---|---|---|
| 2026-10-05 | 二期立项：模板沉淀切片（表/接口/卡片消息/检索接口） | 二期：模板沉淀 |
| 2026-10-05 | 知识代答成文升级为 DeepSeek 生成（知识材料作上下文、注明依据、说明缺口；失败回退确定性拼接） | 二期 |
| 2026-10-05 | 落地 R1：DDL 18（agent_knowledge，shared_group_ids 授权即披露边界）+ `POST/GET/PUT/DELETE /agent/knowledge` + 群代答钩子（@知识库主人或 @Agent 命中知识 → 带来源代答；命中但没人问→保持安静）+ AgentPanel 知识库管理弹层；中文二元组切词（连续中文无空格，不能按空格分词）；HTTP 实测代答成功 | 二期必须需求 #1 |
| 2026-10-05 | 落地：DDL 17（issue_templates）+ `POST /issues/{id}/promote-template` + `GET /templates` + `GET /templates/match` + `POST /templates/{id}/send`（template 卡片消息进会话，use_count 累计）；IssueSidePanel「沉淀为处理模板」（个人库/公共库）；AskView 问答同步匹配模板并展示「模板+责任人」；实测全链路通过 | 二期 |
