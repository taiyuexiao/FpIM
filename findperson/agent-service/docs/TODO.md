# 项目待办(TODO)

> 记录已确认要做但暂未实施的事项,做完一项删一项。

## 1. 接入真实 Embedding 模型(暂缓,后续会做)

- **背景**:当前 Embedding 是确定性 Mock(`EMBEDDING_USE_MOCK=1`),语义信号弱;接口 `EmbeddingPort` 已冻结,就是为替换准备的。
- **方案(已评估)**:本地下载 BGE 系列,推荐 `bge-base-zh-v1.5`(768 维,小快)或 `bge-m3`(1024 维,效果好);国内走 hf-mirror.com 镜像。备选:阿里 `text-embedding-v3` API(1024 维)。
- **接入时要动的三处**:
  1. `requirements.txt` 加 `sentence-transformers`(带 torch,包较大)
  2. `app/core/embedding_client.py` 新增实现类 + 改工厂两行
  3. **维度匹配**:DDL 写死 vector(1024)/vector(1536),选 768 维需改 DDL + 重建索引
- **换完必做**:改 `.env` → 重跑 `backfill_concept_embeddings.py` 和 `build_rag_index.py`(Mock 向量全废,新旧不混)→ 重跑评测对比(重点看 expert_finding Top1,当前 71.4% 的主要失分点)

## 其他已知缺口(V1.2 标注的后续事项)

- 正式 JWT 鉴权(当前 Demo X-User-Id 桩,接口已预留)
- 权限策略(机制已有,部门/角色/敏感级规则待定)
- 会话历史/多轮对话(`agent_sessions` 表已建未用,做追问能力前必须先补)
- edit 写操作闭环(负责领域填写 API 已有底层 `register_raw_tag`,缺接入层)
- 知识库补流程/制度/FAQ 类 OKF(当前仅责任/人员/内容/部门 4 类)
