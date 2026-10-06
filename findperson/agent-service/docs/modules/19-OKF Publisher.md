# 模块 19:OKF Schema + Publisher

## 背景

对应 V1.2 §10.1(OKF 知识模型:8 类目录 + 13 必备元数据 + Markdown 正文)与 §10.2(OKF Publisher:业务事实 → Candidate OKF → 六步校验链 → Published OKF → 触发增量索引)。OKF 是「业务事实」与「RAG 在线索引」之间的正式知识治理层,文档铁律:业务库不得直接向量化,RAG 只消费 Published OKF。Publisher 不负责向量召回和推荐排序。

## 任务

- 输入:业务事实数据(责任/人员/内容/部门等)
- 输出:OKF 文档序列化格式、校验链、发布器(含增量判断)
- 验收:校验失败不污染仓库;相同内容跳过;内容变化升版本

## 实现方式

- `app/okf/document.py`:**OKF 文档格式** = YAML frontmatter(13 必备字段 + extra 类型专有字段)+ Markdown 正文;`to_markdown()`/`from_markdown()` 序列化往返(PyYAML,allow_unicode)
- `app/okf/publisher.py`
  - **OkfValidator.validate()** 六步校验链(§10.2):
    1. YAML Schema:13 必备字段 + 正文非空 + version≥1
    2. Stable ID:`^[a-z][a-z0-9-]*$` + 类型前缀匹配(显式映射 TYPE_ID_PREFIX,responsibilities→responsibility 等)
    3. Source:Published 必须有 source_type/source_id(能反查业务来源)
    4. Visibility/Sensitivity:枚举合法 + 敏感级 0~3
    5. 链接完整性:extra.related_okf_ids 必须存在于已发布集合
    6. content_hash:sha256(发布前由 Publisher 计算)
  - **OkfPublisher.publish()**:先算 hash → 全量校验(失败直接返回,不写仓库,§10.2「发布失败不能污染当前可查询版本」)→ 与仓库旧版 hash 相同则跳过(changed=False,§10.6 增量)→ 否则 version+1 置 PUBLISHED 写仓库
- 测试 `tests/test_okf.py`(部分):序列化往返(13 字段+extra)、校验链(好文档零错误;坏 ID/坏敏感级/坏链接全部被拦),通过

## 遇到的问题报错及解决方法

1. **`str.rstrip("s")` 陷阱**:类型前缀用 `"responsibilities".rstrip("s")` 得到 "responsibilitie"(rstrip 按字符集剥离,把 'e' 前的所有 's' 连根拔),导致稳定 ID 校验误杀全部合法文档(publish 全失败)。
   解决:改为显式映射表 TYPE_ID_PREFIX(8 个目录→单数前缀),96 全过。

## 上下游接口及依赖

- 上游:模块 04 OkfDocument/OkfMetadata 契约、模块 20 OkfRepository(写入落点)
- 下游:
  - 模块 21:ResponsibilityPublisher/PersonProfilePublisher/ContentPublisher 用本模块发布真实数据
  - 模块 23 RAG Indexer 的输入校验:只消费 Publisher 产出的 Published OKF
  - 模块 25 MCP list_sources/knowledge_health 反映发布统计
- 对外接口:`to_markdown/from_markdown`、`OkfValidator`、`OkfPublisher.publish()`、`PublishResult`
