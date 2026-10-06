"""最小指标集（04-生产加固技术方案 §2.5）：零依赖 Prometheus 文本格式。

P0 范围：消息计数/发送延迟/Agent 调用/WS 连接数；进程内聚合（重启清零可接受），
多实例阶段替换为 prometheus-client + /metrics 网关。
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict

_lock = threading.Lock()
_counters: dict[str, float] = defaultdict(float)
_hists: dict[str, list[float]] = defaultdict(list)
_gauges: dict[str, callable] = {}
_HIST_CAP = 500
_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10)


def _key(name: str, labels: dict | None) -> str:
    if not labels:
        return name
    return name + "|" + ",".join(f"{k}={v}" for k, v in sorted(labels.items()))


def incr(name: str, labels: dict | None = None, n: float = 1) -> None:
    with _lock:
        _counters[_key(name, labels)] += n


def observe(name: str, value: float, labels: dict | None = None) -> None:
    with _lock:
        h = _hists[_key(name, labels)]
        h.append(float(value))
        if len(h) > _HIST_CAP:
            del h[: len(h) - _HIST_CAP]


def register_gauge(name: str, fn) -> None:
    with _lock:
        _gauges[name] = fn


def render() -> str:
    """Prometheus 文本格式输出。"""
    lines: list[str] = []

    def emit(name, key, kind, value):
        labels = ""
        if "|" in key:
            pairs = key.split("|", 1)[1].split(",")
            labels = "{" + ",".join(p.replace("=", '="', 1) + '"' for p in pairs) + "}"
        lines.append(f"{name}{labels} {value}")

    with _lock:
        for key, v in sorted(_counters.items()):
            emit(key.split("|")[0], key, "counter", v)
        for key, fn in sorted(_gauges.items()):
            try:
                lines.append(f"{key} {fn()}")
            except Exception:  # noqa: BLE001
                pass
        for key, values in sorted(_hists.items()):
            base = key.split("|")[0]
            labels = ""
            if "|" in key:
                pairs = key.split("|", 1)[1].split(",")
                labels = "{" + ",".join(p.replace("=", '="', 1) + '"' for p in pairs) + "}"
            total = sum(values)
            lines.append(f"{base}_count{labels} {len(values)}")
            lines.append(f"{base}_sum{labels} {round(total, 4)}")
            for b in _BUCKETS:
                lines.append(f'{base}_bucket{labels[:-1] if labels else ""}{{le="{b}"{"," if labels else ""}}} '
                             f'{sum(1 for v in values if v <= b)}')
            lines.append(f'{base}_bucket{labels[:-1] if labels else ""}{{le="+Inf"{"," if labels else ""}}} {len(values)}')
    return "\n".join(lines) + "\n"
