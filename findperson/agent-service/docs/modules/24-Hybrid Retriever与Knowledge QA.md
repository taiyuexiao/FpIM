# 模块 24:Hybrid Retriever + Knowledge QA

## 背景

对应 V1.2 §10.9(Hybrid Retriever:权限预过滤 → FTS/pg_trgm Top20 与 pgvector Top20 并行 → RRF 融合 → 可选 Reranker → 二次权限校验 → 按文档/章节去重 → Top5;RAG 不生成最终回答)和 §10.10(Knowledge QA Pipeline:知识回答必须附 document_id + version + source_uri;**没有检索证据时不得根据 LLM 常识编造内部制度或流程**)。这是 818 个索引 chunk 变成在线知识证据的检索引擎。

## 任务

- 输入:query + user_context + filters + top_k
- 输出:RagHit[](带 score/来源/版本)+ KnowledgeQAService(facts/citations/has_evidence)
- 验收:双路召回 RRF 融合;权限预过滤;Top5 去重;无证据不编造

## 实现方式

- `app/rag/retriever.py`
  - **HybridRetriever.retrieve()**:
    - 权限预过滤:`d.sensitivity <= user.sensitivity_level`(在 SQL 内,两路都带)
    - FTS 路:`content % query`(pg_trgm)+ `similarity()` 排序取 Top20
    - 向量路:`embedding <=> query_vec` 余弦距离取 Top20(1536 维 RAG 空间)
    - **RRF 融合**(k=60,`Σ 1/(k+rank)`)
    - 二次权限校验(防御性)+ 按 `document_id#section_path` 去重 → Top5
    - 写 rag_query_logs(失败不阻断)
  - **KnowledgeQAService.answer()**:hits → facts + citations(document_id/chunk_id/version/source_uri);**无命中 → has_evidence=False、facts/citations 为空**,编造防线留给 AnswerBuilder(§10.10)
- 测试 `tests/test_retriever.py`(6 用例):FTS 召回数据治理、向量语义召回责任文档(换说法「问题需要转交和逐级上报」)、RagHit 契约字段、Top5+去重、QA 有证据带引用、QA 无证据不编造,全部通过(累计 115 passed)

## 遇到的问题报错及解决方法

1. **asyncpg 把 jsonb 读成字符串(第二次踩同类坑)**:`row["metadata"]` 是 str 不是 dict,`isinstance(dict)` 判断为 False 导致 RagHit 的 document_type/source_uri 全空。
   解决:对 str 类型 `json.loads` 解析。(第一次是 vector 列读成字符串——asyncpg 对 pgvector/jsonb 扩展类型默认都返回字符串,后续涉及这两类字段一律做类型适配。)
2. **语义测试查询与实际语料不匹配**:「平台运行维护找谁」在真实语料(24 份 Mock 责任文档)中没有对应措辞,向量路也召不回责任类文档。
   解决:改用语料中真实存在的语义(「问题需要转交和逐级上报」对应转办条件/升级路径字段),测试反映真实检索行为而非臆想语料。

## 上下游接口及依赖

- 上游:模块 23 RAG 索引(active_version chunks)、模块 07 RAG Embedding、模块 03 UserContext(sensitivity_level)
- 下游:
  - 模块 25:MCP search_knowledge/get_document 的检索实现
  - 模块 26:KnowledgeRetrievalNode 经 MCP 调用本服务,Knowledge QA 替换模块 16 的 knowledge_qa 占位
  - 模块 28 评测:RAG Recall@5 / 引用覆盖率
- 对外接口:`HybridRetriever.retrieve()`、`KnowledgeQAService.answer()`、`RagHit`
