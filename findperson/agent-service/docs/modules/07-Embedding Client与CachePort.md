# 模块 07:Embedding Client + CachePort

## 背景

对应 V1.2 §14.2(Embedding Client:embed_query/embed_documents/model_version/dimension,Concept 与 RAG 不同配置实例)、§10.8(两个独立向量空间:RAG 1536 维、Concept 1024 维,不得跨表比较)、§14.4(Redis/LocalCache:V1 无 Redis 资源,按 §23 用 LocalCache,业务模块只依赖 CachePort)。真实 Embedding 模型是 §23 待确认事项,因此必须先冻结接口、用 Mock 推进。

## 任务

- 输出:EmbeddingPort 抽象 + Mock 实现 + 双实例工厂;CachePort 抽象 + LocalCache + 统一缓存键
- 验收:双空间维度/模型版本正确;Mock 确定性;向量保留词汇重叠信号(候选召回可用);跨空间比较被拒绝;TTL 生效

## 实现方式

- `app/core/embedding_client.py`
  - `EmbeddingPort` Protocol:dimension / model_version / embed_query / embed_documents
  - `MockEmbedding`:sha256(token+模型版本) → 撒布到 K=8 个维度 → L2 归一化。同一文本必然同向量(确定性);词汇重叠越多余弦越高(保留召回信号)。分词为中英混合:英文按词、中文单字 + 中文二字组(提升中文短语区分度)
  - `cosine_similarity()`:维度不一致直接 `ValueError` —— 把「不得跨空间比较」做成运行时红线
  - 工厂:`get_rag_embedding()`(1536/mock-rag-embedding-v1)、`get_concept_embedding()`(1024/mock-concept-embedding-v1),模型版本化,符合 §23「索引模型版本化,不跨模型混写」
- `app/core/cache.py`
  - `CachePort` Protocol:get/set(ttl)/delete/clear,后续可无缝换 Redis 实现
  - `LocalCache`:dict + TTL 惰性过期;`get_cache()` 单例
  - `CacheKeys`:集中管理 §14.4 五类缓存键(concept 词典、tcm、query→concept、MCP 短缓存、session)
- 测试 `tests/test_core_embedding_cache.py`:7 个用例(双空间维度、确定性、语义信号「AgentOS 智能体开发平台」比无关文本更接近「智能体平台」、跨空间比较报错、TTL、单例、缓存键模板),全部通过(累计 36 passed)

## 遇到的问题报错及解决方法

无功能问题。设计上的一个关键点:Mock 不能只返回随机向量,否则阶段 2 的 Concept Vector Recall(§7.3 第五级)无法离线验证,因此特意让 Mock 向量携带词汇重叠信号,并用测试断言「近义文本相似度 > 无关文本」。

## 上下游接口及依赖

- 上游:模块 01 config(维度/模型版本/Mock 开关)
- 下游:
  - 模块 17(Concept Vector Recall)、模块 23(RAG Indexer 写向量)、模块 24(Hybrid Retriever pgvector 查询)依赖 EmbeddingPort
  - 模块 13(ConceptLinker 词典缓存)、模块 25(MCP 短缓存)、会话状态(模块 16)依赖 CachePort
  - 真实 Embedding 确认后,只需新增实现类并改工厂,业务代码零改动
- 对外接口:`EmbeddingPort`、`MockEmbedding`、`cosine_similarity`、`get_rag_embedding`、`get_concept_embedding`、`CachePort`、`LocalCache`、`CacheKeys`、`get_cache`
