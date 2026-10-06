"""模块 06:LLM Client 测试。

默认跑 Mock 离线测试;真实 DeepSeek 调用用 REAL_LLM=1 环境变量显式开启。
"""
import os

import pytest

from app.contracts.errors import AgentError, ErrorCode
from app.core.llm_client import DeepSeekLLM, MockLLM, get_llm


async def test_mock_chat() -> None:
    """Mock chat 离线可用、确定性。"""
    llm = MockLLM()
    r1 = await llm.chat([{"role": "user", "content": "你好"}])
    r2 = await llm.chat([{"role": "user", "content": "你好"}])
    assert r1.content == r2.content
    assert "你好" in r1.content


async def test_mock_structured_chat_keys() -> None:
    """Mock structured_chat 覆盖 required_keys。"""
    llm = MockLLM()
    data, result = await llm.structured_chat(
        [{"role": "user", "content": "x"}], required_keys=["intent", "confidence"],
    )
    assert set(data.keys()) == {"intent", "confidence"}


async def test_structured_chat_retry_on_bad_json(monkeypatch) -> None:
    """输出非法 JSON 时按 max_retries 重试,仍失败则抛 LLM_ERROR(§5.2)。"""
    from app.core.llm_client import LLMResult

    llm = DeepSeekLLM.__new__(DeepSeekLLM)  # 不读配置
    llm._model = "test"
    llm._sem = __import__("asyncio").Semaphore(1)

    async def bad_call(payload):
        return LLMResult(content="not-json", tokens=1, model="test")

    monkeypatch.setattr(llm, "_call", bad_call)
    with pytest.raises(AgentError) as exc:
        await llm.structured_chat([{"role": "user", "content": "x"}], required_keys=["k"], max_retries=1)
    assert exc.value.code == ErrorCode.LLM_ERROR


async def test_structured_chat_missing_key(monkeypatch) -> None:
    """缺 required_keys 字段判为失败并重试。"""
    import json

    from app.core.llm_client import LLMResult

    llm = DeepSeekLLM.__new__(DeepSeekLLM)
    llm._model = "test"
    llm._sem = __import__("asyncio").Semaphore(1)

    async def incomplete(payload):
        return LLMResult(content=json.dumps({"a": 1}), tokens=1, model="test")

    monkeypatch.setattr(llm, "_call", incomplete)
    with pytest.raises(AgentError):
        await llm.structured_chat([{"role": "user", "content": "x"}], required_keys=["a", "b"], max_retries=0)


def test_get_llm_factory() -> None:
    """工厂按配置返回 Mock/Real(当前 .env LLM_USE_MOCK=0 → Real)。"""
    llm = get_llm()
    assert type(llm).__name__ in ("MockLLM", "DeepSeekLLM")


@pytest.mark.skipif(os.getenv("REAL_LLM") != "1", reason="真实 DeepSeek 调用,设 REAL_LLM=1 开启")
async def test_real_deepseek_chat() -> None:
    """真实 API 冒烟:问候 + JSON 模式。"""
    llm = DeepSeekLLM()
    r = await llm.chat([{"role": "user", "content": "用一句话介绍你自己"}])
    assert r.content and r.tokens > 0
    data, _ = await llm.structured_chat(
        [{"role": "user", "content": '输出JSON: {"ok": true, "msg": "你好"}'}],
        required_keys=["ok", "msg"],
    )
    assert data["ok"] is True
