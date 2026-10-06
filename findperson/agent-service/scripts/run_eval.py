"""一条命令跑评测(§16.1 验收)。

用法:
  .\\venv\\Scripts\\python.exe scripts\\run_eval.py [--split dev|test] [--baselines A,B,C,D,E]
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.db import close_pool, init_pool  # noqa: E402
from app.eval.runner import run_evaluation  # noqa: E402


def _arg(name: str, default: str) -> str:
    for i, a in enumerate(sys.argv):
        if a == name and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return default


async def main() -> None:
    split = _arg("--split", "dev")
    baselines = tuple(_arg("--baselines", "A,B,C,D,E").split(","))
    await init_pool()
    try:
        output = await run_evaluation(split, baselines=baselines)
    finally:
        await close_pool()
    for b, data in output["baselines"].items():
        m = data["metrics"]
        print(f"\n===== Baseline {b} ({split}) =====")
        for k, v in m.items():
            if k != "Error Attribution":
                print(f"  {k}: {v}")
        if m.get("Error Attribution"):
            print(f"  错误归因: {m['Error Attribution']}")
        for fc in data["failed_cases"][:5]:
            print(f"    [失败] {fc['id']} {fc['query'][:40]} → {fc['attribution']}")
    out_path = Path(__file__).resolve().parent.parent / "data" / "eval" / f"report_{split}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=1)
    print(f"\n[eval] 报告已写入 {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
