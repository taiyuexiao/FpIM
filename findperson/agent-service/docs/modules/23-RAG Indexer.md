# 模块 23:RAG Indexer(增量 + 版本原子切换)

## 背景

对应 V1.2 §10.6(RAG 文档发布与索引):**只消费 Published OKF**(§11.1 红线:不得业务表直接向量化);变化判断用 id + version + content_hash;五类更新规则(新增/正文替换/仅元数据/删除废止/全量 rebuild 原子切换);§23「索引模型版本化,不跨模型混写」。这是 OKF 治理链与在线检索之间的转换器,也是模块 21 的 374 份 OKF 变成可检索知识的落点。

## 任务

- 输入:knowledge-okf 仓库的 374 份 Published OKF
- 输出:rag_documents/rag_chunks(818 chunks,1536 维向量)+ index_version 管理 + Smoke Test + 原子切换 + 增量 API
- 验收:全量 rebuild 原子切换;增量四规则正确;chunk 向量非空、模型版本化

## 实现方式

- `app/rag/indexer.py` **RagIndexer**:
  - `rebuild(docs)`:new index_version → 事务内全量写(Chunker 切片 + MockEmbedding 1536 维逐块嵌入)→ **Smoke Test**(文档数一致/无空向量/无零块文档/样例可查,失败则不切换并报 RAG_ERROR)→ `rag_index_pointer` **原子切换** → job 状态机(running→smoke_test→published/failed)
  - `incremental(docs)`:在当前版本上按规则逐文档处理——无记录→新增;content_hash 变→删旧 chunks 整体替换;仅 okf_version 变→只更新 metadata/filter;未变→跳过
  - `invalidate(ids)`:删除/废止 → status='invalidated'
  - 向量以 `[x,y,z]::vector` 字面量写入;`embedding_model` 逐块记录(mock-rag-embedding-v1)
- `scripts/build_rag_index.py [--incremental]`:从 OkfRepository.list_published() 取唯一输入
- **真实运行**:v1 全量 = 374 文档 / 818 chunks,Smoke Test 通过,原子切换
- 测试 `tests/test_rag_indexer.py`(4 用例):增量三规则、invalidate、rebuild 版本递增+指针切换+job 记录、embedding_model 版本化,全部通过(累计 109 passed)

## 遇到的问题报错及解决方法

1. **诡异的"写入消失"悬案(耗时最长的一次排障)**:增量测试报「写入后查不到数据」,psql 与应用查询结果互相矛盾——fetchrow 能找到旧行、count 却为 0、写入后行消失。
   排查过程:先后怀疑事务回滚(写探针验证 db.transaction() 正常)、双数据库(写 probe-xyz 证明 psql 与应用同库)、连接池多 loop。最后用行内 DEBUG 打印发现:**document_id 是 `content-content-test-inc-1`(双前缀)**——`build_content_doc` 自动加 `content-` 前缀,而测试又传了带前缀的 doc_id。测试查询用单前缀 ID 自然查不到,且残留的双前缀行导致后续重跑从 added 变 replaced/skipped 连锁失败。
   解决:测试改用不带前缀的 doc_id;清理 6 行双前缀残留。**教训:构建器自动加前缀的约定必须在测试数据构造时留意;排查先打印真实数据再怀疑事务/连接。**

## 上下游接口及依赖

- 上游:模块 21 Published OKF(list_published)、模块 22 Chunker、模块 07 RAG Embedding(1536)
- 下游:
  - 模块 24 Hybrid Retriever 从 active_version 的 chunks 检索
  - 模块 25 MCP knowledge_health 反映索引状态;OKF Publisher「触发 RAG 增量索引」挂到 incremental()
  - 模块 26 RAG 证据的向量来源
- 对外接口:`RagIndexer.rebuild()/incremental()/invalidate()/current_version()`、`scripts/build_rag_index.py`
