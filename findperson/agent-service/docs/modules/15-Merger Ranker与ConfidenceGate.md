# 模块 15:CandidateMerger + PeopleRanker + ConfidenceGate

## 背景

对应 V1.2 §12(候选融合与排序):§12.2 CandidateMerger(按 person_id 去重但保留全部证据,**禁止 structured_score + rag_score 直接相加**)、§12.3 PeopleRanker(**不用一套全局排序**,按 query_type 选 RankPolicy;Hermes 不能重排输出)、§12.4 ConfidenceGate(Top1 可信度/Top1-Top2 差距/正式证据/概念歧义/弱证据 → answer/clarify/no_result/degraded_answer)。这是「证据语义分层」真正变成排序行为的地方。

## 任务

- 输入:retrieval 三路证据(结构化/RAG 人员证据/正式责任)
- 输出:merged_candidates、ranked_candidates、rank_policy、confidence、gate_decision
- 验收:去重保留全证据;四种 policy 排序语义正确;闸门五态判定正确

## 实现方式

- `app/agent/candidate_merger.py`
  - `MergedPersonCandidate`:一人一条,evidences + responsibilities 分开存放;`has_formal` 属性供 policy 与闸门使用
  - `CandidateMerger.merge()`:三路输入按 person_id 融合;正式责任记录挂到责任人头上,责任人不在候选池也带入(§8.1:正式责任证据始终最高);无具体责任人的部门级责任进特殊桶 `__department_responsibility__`(不进人员排名,由 AnswerBuilder 单独呈现);稳定排序:正式责任者优先
- `app/agent/people_ranker.py`
  - **确定性打分**:`证据语义基础权重(6 类)× 置信度 × 匹配层级修正(leaf_exact=1.0 / generalized=0.7)`,同类型证据取 max 后按 policy 组合——不是一套全局公式,每个 policy 有自己的组合方式:
    - responsibility_policy:有正式责任 → 10+ 直通;否则精确自填 > 画像 > 评价 > 文章(§12.3 优先级)
    - diagnostic_policy:正式责任 + 精确职责为主,画像辅助
    - expert_policy:领域自填+画像实践+文章+评价,**正式责任仅 0.3 权重**(正式负责人≠最佳专家,§12.3)
    - directory_policy:仅身份校验
  - `PeopleRanker.rank()` 返回 (ranked, policy, top1_score);`ConfidenceGate.decide()` 实现五态(空→no_result;degraded→degraded_answer;概念歧义→clarify;低分无正式→no_result;Top1/2 差距过小且均无正式→clarify;否则 answer)
- `app/agent/nodes/ranking.py`:三个 Node 挂编排(Merger/Ranker/Gate),仅 find_person 执行
- 测试 `tests/test_ranking.py`(5 用例):去重保留全证据、正式责任置顶、responsibility_policy 泛化降权、expert_policy 文章专家压过正式责任人、闸门五态,全部通过(累计 76 passed)

## 遇到的问题报错及解决方法

无。一处设计决策:打分聚合采用「同证据类型取 max 再组合」而非累加,避免一个人靠堆同类证据刷分,更符合「证据语义分层」的文档精神;权重表集中为模块常量,评测阶段(模块 28)可基于 dev 集调参。

## 上下游接口及依赖

- 上游:模块 14 structured_candidates/responsibility_evidence、模块 26(未来)rag_person_evidence、模块 04 PersonEvidence 契约
- 下游:
  - 模块 16 AnswerBuilder 消费 ranked_candidates + gate_decision 组织回答(不得重排、不得新增人员)
  - 模块 27 agent_recommendation_logs 落库 ranked 结果
  - 模块 28 评测:PeopleRanker Top1 / Final Top1 / MRR 评本模块输出
- 对外接口:`CandidateMerger`、`MergedPersonCandidate`、`PeopleRanker`、`ConfidenceGate`、三个 Node
