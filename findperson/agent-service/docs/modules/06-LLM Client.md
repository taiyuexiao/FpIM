# 模块 06:LLM Client(DeepSeek + Mock)

## 背景

对应 V1.2 §14.1(LLM Client:「Hermes/OpenAI-compatible API、timeout、concurrency、model config、Mock、usage、Token、error mapping;不维护业务 Prompt」)、§5.2(「LLM 输出必须限制为 Schema」「Schema 二次失败率 < 0.5%」)、§23(LLM 服务未确认时「OpenAI-compatible Adapter + Mock」推进)。LLM 是主链唯一的外部非确定性依赖,必须把它关在统一端口后面,业务 Node 只依赖抽象接口。

## 任务

- 输入:各 Node 的 messages(业务 Prompt 由 Node 自己维护)
- 输出:LLMPort 抽象 + DeepSeek 真实实现 + Mock 实现 + 工厂
- 验收:Mock 离线确定性;真实 DeepSeek 调通;JSON 模式 + 字段校验 + 重试;超时/HTTP 错误映射为统一错误码

## 实现方式

- `app/core/llm_client.py`
  - `LLMPort` Protocol:`chat()` + `structured_chat()`,业务模块只依赖此接口
  - `DeepSeekLLM`:
    - httpx 直连 `.env` 的 DeepSeek 地址,`asyncio.Semaphore(8)` 做并发控制,超时从 config 读(30s)
    - `structured_chat()`:`response_format={"type": "json_object"}` JSON 模式 + `required_keys` 校验,失败重试(max_retries=1),仍失败抛 `LLM_ERROR` —— 对应 Schema 二次失败率要求
    - error mapping:`httpx.TimeoutException → TIMEOUT`;网络/HTTP 非 200/响应结构异常 → `LLM_ERROR`(带 body 摘要入 detail);API key 缺失 → `LLM_ERROR`
    - 返回 `LLMResult(content/tokens/model/latency_ms)`,tokens 供 Trace span 的 llm_tokens(§15.1)
  - `MockLLM`:确定性应答(相同输入相同输出),structured_chat 按 required_keys 返回骨架,离线开发/CI 用
  - `get_llm()` 工厂:按 `LLM_USE_MOCK` 切换 Real/Mock
- 测试 `tests/test_core_llm.py`:Mock 确定性、Mock 键覆盖、非法 JSON 重试后抛错、缺字段重试、工厂类型;真实 API 冒烟(`REAL_LLM=1` 显式开启)
- 结果:29 passed + 1 skipped;**真实 DeepSeek 冒烟通过**(chat 有 token 统计,structured_chat JSON 模式返回正确),耗时 2.84s

## 遇到的问题报错及解决方法

无功能问题。设计上的一处取舍:`structured_chat` 的缺字段与坏 JSON 统一走「重试→抛 AgentError」路径,测试用 `monkeypatch` 替换 `_call` 注入坏输出,并用 `DeepSeekLLM.__new__` 绕过 `__init__` 避免读 .env,保证离线可测。

## 上下游接口及依赖

- 上游:模块 01 config(LLM_API_KEY/BASE_URL/MODEL/USE_MOCK/timeout)、模块 02 错误模型
- 下游:
  - 意图识别(模块 11)、QueryStructurer(模块 12)、LLM 受约束消歧(模块 18)、AnswerBuilder(模块 16)、Knowledge QA(模块 24)都经 `get_llm()` 拿 LLMPort
  - Trace(模块 27)消费 LLMResult.tokens
  - 评测(模块 28)用 MockLLM 做离线基线
- 对外接口:`LLMPort`、`LLMResult`、`LLMUsage`、`DeepSeekLLM`、`MockLLM`、`get_llm()`
