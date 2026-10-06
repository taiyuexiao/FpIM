"""真实 DeepSeek 意图识别冒烟(一次性验证脚本,非 pytest)。"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent.intent import IntentService  # noqa: E402


async def main() -> None:
    svc = IntentService()
    for q in ("谁负责智能体平台?", "Dify并发一高就超时,该找谁?",
              "GPU算力申请流程是什么?", "王丹的电话是多少", "今天天气不错"):
        r = await svc.classify(q)
        print(f"Q: {q}\n  → intent={r.intent.value}, query_type={r.query_type and r.query_type.value},"
              f" conf={r.confidence}, clarify={r.needs_clarification}\n")


if __name__ == "__main__":
    asyncio.run(main())
