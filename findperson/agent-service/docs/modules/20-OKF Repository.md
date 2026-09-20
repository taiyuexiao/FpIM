# 模块 20:OKF Repository(Git 受控文件仓库)

## 背景

对应 V1.2 §10.3(Published OKF Repository:版本历史/Diff/Review/Publish/Rollback/Source Trace;**不承担**在线向量检索、Agent 会话、用户实时负责领域、动态 RawTag、推荐排名)。文档要求「任意正式版本可定位和回滚」「Published / Draft 边界清楚」「RAG Indexer 只消费 Published OKF」。§23 待确认项中 Repository 最终形态未定,先以本地 Git 仓库实现(可整块交付)。

## 任务

- 输入:Publisher 校验通过的 OkfDocument
- 输出:Git 文件仓库(8 类目录)+ 版本管理 API
- 验收:每次发布一个 git 版本;历史可查;两版本可 diff;可回滚;只列 Published

## 实现方式

- `app/okf/repository.py` **OkfRepository**:
  - 目录即 §10.1 的 8 类知识(responsibilities/people/departments/processes/policies/faqs/contents/relationships),文档路径 `{type}/{id}.md`
  - `write()`:写文件 + `git add + commit`(每次发布一个版本,commit message 含 id 与版本号)
  - `get_latest(id)` / `list_published_ids()` / `list_published()`(只返回 status=published,RAG Indexer 的唯一输入)
  - **版本管理**:`history()`(git log 该文件)、`diff(commit_a, commit_b)`、`rollback(commit)`(git checkout 旧版 + 再 commit,回滚本身也留痕)
  - `_git()` 异步封装(asyncio subprocess),失败统一转 AgentError;`ensure_git_initialized()` 幂等 init
- 测试 `tests/test_okf.py`(部分):发布 v1 → 相同内容跳过 → 改内容升 v2;校验失败仓库零污染;history≥2 commit、diff 含新增内容、rollback 回 v1 再恢复 v2,全部通过(累计 96 passed)

## 遇到的问题报错及解决方法

无(Git 版本管理测试一次通过;tmp_path 隔离,不污染项目 knowledge-okf 目录)。备注:回滚采用「checkout 旧版 + 新 commit」而非 reset,保证历史不可篡改、Review 可追踪。

## 上下游接口及依赖

- 上游:模块 19 OkfPublisher(唯一写入方)、系统 git 命令
- 下游:
  - 模块 21 责任/PersonProfile 发布链的落点
  - 模块 23 RAG Indexer 经 `list_published()` 消费(只读)
  - 模块 25 MCP get_document/list_sources 从仓库取文档与版本信息
- 对外接口:`OkfRepository`(write/get_latest/list_published_ids/list_published/history/diff/rollback/ensure_git_initialized)
