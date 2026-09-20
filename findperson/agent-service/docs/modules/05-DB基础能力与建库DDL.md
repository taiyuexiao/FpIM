# 模块 05:DB 基础能力 + 建库 DDL

## 背景

对应 V1.2 §14.3(PostgreSQL 数据访问基础能力:「统一 asyncpg/连接池/事务/timeout/health/repository interface;禁止各业务模块自行维护数据库连接」)、§17(public/agent/rag 三 schema 职责边界)与 §10.8(RAG 1536 维 / Concept 1024 维两个独立向量空间)。按既定决策新建 `shouwenzeren_v2` 库,与旧项目完全隔离。

## 任务

- 输入:本机 PostgreSQL 18.4(localhost:5432)
- 输出:三 schema DDL + init_db.py 一键建库 + app/core/db.py 唯一 DB 入口
- 验收:连接池 health 通过;三 schema、核心表、双向量维度、trgm 索引核对无误;DDL 可重复执行

## 实现方式

- DDL(`scripts/ddl/`,全部 IF NOT EXISTS 可重跑):
  - `01_public.sql`:departments / people(沿用旧库 id 如 p-0001)/ contents / peer_reviews / **responsibility_assignments**(正式责任唯一事实源,含受理部门、责任部门、责任人、时限、转办条件、升级路径、version)
  - `02_agent.sql`:raw_tags(normalized_text 唯一判重)/ person_tags / concepts(**vector(1024)** + Candidate 专有字段)/ concept_aliases / tag_concept_map(mapping_type/confidence/generated_by/review_status)/ concept_relations / concept_review_queue + 运行态表(query_concept_logs / agent_traces / agent_node_spans / agent_sessions / agent_recommendation_logs / mcp_call_logs / feedback_events);concepts.canonical_name、aliases、rag content 建 gin_trgm_ops 索引
  - `03_rag.sql`:rag_documents / rag_chunks(**vector(1536)**)/ rag_index_jobs / **rag_index_pointer**(单行表,原子切换当前生效 index_version)/ rag_query_logs;(document_id/chunk_id, index_version) 复合主键支持多版本并存
- `scripts/init_db.py`:连 postgres 库建 shouwenzeren_v2 → CREATE EXTENSION vector/pg_trgm → 建 agent/rag schema → 顺序执行三份 DDL → 核心表抽查
- `app/core/db.py`:全局唯一 `asyncpg.Pool`(init_pool/close_pool/get_pool 未初始化即报错,防止隐式建连)、`connection()`/`transaction()` 上下文管理器、`health()`、`fetch/fetchrow/fetchval/execute` 便捷函数;异常统一转 AgentError(INTERNAL_ERROR)
- `pytest.ini`:`asyncio_mode = auto`
- 测试 `tests/test_core_db.py`:health、三 schema、核心表、双向量维度(1024/1536)、trgm 索引数量,全部通过(累计 24 passed)

## 遇到的问题报错及解决方法

1. **pytest-asyncio「attached to a different loop」**:module 级 async fixture 在一个事件循环建连接池,测试函数在另一个循环执行,asyncpg 连接绑错 loop,5 个 DB 测试全挂。
   解决:fixture 改用 pytest-asyncio 1.x 的 `pytest_asyncio.fixture(scope="module", loop_scope="module")` + `pytestmark = pytest.mark.asyncio(loop_scope="module")`,让 fixture 与该 module 全部测试共享同一事件循环,24 全过。
2. **PowerShell 内联 python -c 引号转义地狱**:验证脚本里的 SQL 单引号被吞导致 SyntaxError。
   解决:不写内联脚本,固化为 pytest 测试文件,既验证又留档。

## 上下游接口及依赖

- 上游:模块 01 config(PG 连接参数)、模块 04 契约(表结构按契约建模)
- 下游:
  - 模块 08 迁移脚本向 public 各表写 300 人/30 文
  - 阶段 1-2 所有语义层模块读写 agent.*;OKF/RAG(模块 19-24)读写 rag.*;Trace 落库(模块 27)写 agent_traces/agent_node_spans
  - 全部业务模块只允许通过 `app.core.db` 访问数据库
- 对外接口:`init_pool/close_pool/health/connection/transaction/fetch/fetchrow/fetchval/execute`;`scripts/init_db.py`
