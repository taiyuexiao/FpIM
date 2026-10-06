"""并发压测脚本(§19 阶段 8:Concurrency / Pressure Test)。

对 /agent/chat 发并发请求,统计成功率、P50/P95 延迟、降级率。
验收参考(§21):简单找人路径 P95 < 2.5s;复杂诊断路径 P95 < 6s。

用法:先启动服务,再运行
  .\\venv\\Scripts\\python.exe scripts\\pressure_test.py [--concurrency 10] [--requests 30]
"""
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE = "http://127.0.0.1:8100"
SIMPLE_QUERIES = ["王丹的电话是多少", "刘旭的联系方式", "谁负责数据治理?"]
COMPLEX_QUERIES = ["数据治理平台出问题了该找谁?", "谁比较懂数据仓库?", "大模型相关事务找谁?"]


def _arg(name: str, default: int) -> int:
    for i, a in enumerate(sys.argv):
        if a == name and i + 1 < len(sys.argv):
            return int(sys.argv[i + 1])
    return default


async def one_request(client: httpx.AsyncClient, query: str) -> dict:
    start = time.time()
    try:
        resp = await client.post(
            f"{BASE}/agent/chat",
            json={"query": query},
            headers={"X-User-Id": "p-0002"},
            timeout=45,
        )
        latency = (time.time() - start) * 1000
        body = resp.text
        return {
            "ok": resp.status_code == 200 and "run_error" not in body,
            "latency_ms": latency,
            "degraded": '"degraded": true' in body,
            "query": query,
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "latency_ms": (time.time() - start) * 1000,
                "degraded": True, "query": query, "error": str(e)[:100]}


async def main() -> None:
    concurrency = _arg("--concurrency", 10)
    n_requests = _arg("--requests", 30)
    queries = (SIMPLE_QUERIES + COMPLEX_QUERIES) * (n_requests // 6 + 1)
    queries = queries[:n_requests]

    async with httpx.AsyncClient() as client:
        sem = asyncio.Semaphore(concurrency)

        async def bounded(q):
            async with sem:
                return await one_request(client, q)

        start = time.time()
        results = await asyncio.gather(*(bounded(q) for q in queries))
        total_time = time.time() - start

    latencies = sorted(r["latency_ms"] for r in results)
    ok = sum(1 for r in results if r["ok"])
    degraded = sum(1 for r in results if r["degraded"])
    simple = sorted(r["latency_ms"] for r in results if r["query"] in SIMPLE_QUERIES)
    complex_ = sorted(r["latency_ms"] for r in results if r["query"] in COMPLEX_QUERIES)

    def pct(values, p):
        return round(values[min(len(values) - 1, int(len(values) * p))], 0) if values else 0

    print(f"[压测] 并发={concurrency} 请求={n_requests} 总耗时={total_time:.1f}s")
    print(f"[压测] 成功率: {ok}/{n_requests} ({ok / n_requests * 100:.0f}%)")
    print(f"[压测] 降级率: {degraded / n_requests * 100:.0f}%")
    print(f"[压测] 全部延迟: P50={pct(latencies, .5)}ms P95={pct(latencies, .95)}ms max={latencies[-1]:.0f}ms")
    print(f"[压测] 简单找人 P95: {pct(simple, .95)}ms (基线 <2500ms)")
    print(f"[压测] 复杂诊断 P95: {pct(complex_, .95)}ms (基线 <6000ms)")
    for r in results:
        if not r["ok"]:
            print(f"  [失败] {r['query']}: {r.get('error', 'run_error')}")


if __name__ == "__main__":
    asyncio.run(main())
