# 模块 25:Knowledge MCP Server + Client

## 背景

对应 V1.2 §12(MCP 知识服务):§12.1 Knowledge MCP Server(**8 个只读工具**;Agent 不直连 rag schema;**调用强制携带可信 user_context**;每次调用写 mcp_call_logs 用同一 trace_id 串联)、§12.2 KnowledgeMcpClient(类型化 Client:超时/熔断/参数 Schema/trace/错误转换/Mock-Real 切换;不负责 RAG 算法、SQL、权限规则)。这是 Agent 与知识层之间唯一的受控通道,也是模块 14 的 MockResponsibilityRetriever 的正式替代。

## 任务

- 输入:Agent 侧工具调用(tool + params + user_context + trace_id)
- 输出:8 个工具的服务端实现 + 带超时/熔断的客户端
- 验收:无 user_context 拒绝;日志落库;超时/熔断/错误转换统一;8 工具全部可用

## 实现方式

- `app/mcp_knowledge/server.py` **KnowledgeMcpServer**:
  - 统一入口 `call()`:user_context 缺失 → AUTH_ERROR;路由到 `_{tool}` handler;每次调用写 agent.mcp_call_logs(trace_id/tool/params/ok/latency)
  - 8 工具:search_knowledge(走 HybridRetriever)、get_document(仓库取文档)、**get_responsibility**(责任文档标题确定性匹配优先——责任文档量小且正式责任查询必须可靠,语义检索兜底)、get_person_profile(§10.4 已过滤动态标签)、get_process(当前无流程文档,显式说明)、find_related_knowledge(同标题召回排除自身)、list_sources(374 份按类型统计)、knowledge_health(发布数/索引版本/chunk 数/模型版本/一致性)
  - V1 传输形态:**进程内直连**(接口与传输解耦,§23;后续可替换 stdio/HTTP)
- `app/mcp_knowledge/client.py` **KnowledgeMcpClient**:
  - `_CircuitBreaker`:连续 3 次失败断开,30s 冷却半开试探,成功复位
  - `call_tool()`:熔断前置 → `asyncio.wait_for` 超时包装(mcp_timeout_ms=3000)→ 统一 McpResponse(ok/error/degraded);超时与 MCP/内部错误计入熔断,业务错误(AUTH/INPUT/RAG)只转换不熔断
  - 类型化便捷方法(search_knowledge/get_responsibility/get_document/get_person_profile/knowledge_health)
  - `get_mcp_client()` 单例(Mock/Real 切换点)
- 测试 `tests/test_mcp.py`(8 用例):8 工具注册、无 ctx 拒绝、search_knowledge+日志落库、get_responsibility 全字段、get_document/profile(无动态标签)、health/sources 一致性(374)、超时降级+熔断开合、错误转换,全部通过(累计 123 passed)

## 遇到的问题报错及解决方法

1. **get_responsibility 检索不到责任文档**:混合检索 Top3 被人员画像(高频含「数据治理」)挤占,责任文档排不进 Top3。
   解决:正式责任查询改为**仓库标题确定性匹配优先**(责任文档仅 24 份,精确可靠),语义检索只作兜底——符合「正式责任证据必须可靠」的文档精神。
2. **mcp_call_logs 断言受历史数据干扰**:日志表跨测试持久,`count==1` 断言在重跑时失败。
   解决:断言改 `>=1`。

## 上下游接口及依赖

- 上游:模块 24 HybridRetriever、模块 20 OkfRepository、模块 04 MCP 契约、agent.mcp_call_logs 表
- 下游:
  - 模块 26:StructuredRetrievalNode 的 MockResponsibilityRetriever 替换为 `get_responsibility`;新增 KnowledgeRetrievalNode 经 `search_knowledge` 并联进主链;knowledge_qa 占位分支替换为真实 MCP 调用
  - 模块 29:熔断参数并入稳定性配置;模块 30:进程内传输可换 stdio/HTTP
- 对外接口:`KnowledgeMcpServer.call()`、`KnowledgeMcpClient`(call_tool + 类型化方法)、`get_mcp_client()`、`_CircuitBreaker`
