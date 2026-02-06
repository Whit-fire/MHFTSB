import time
import logging
from typing import Dict, List
from collections import deque

logger = logging.getLogger("metrics")


class MetricsService:
    def __init__(self):
        self._start_time = time.time()
        self._counters: Dict[str, int] = {}
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, deque] = {}
        self._latency_samples: deque = deque(maxlen=1000)

    def increment(self, name: str, value: int = 1):
        self._counters[name] = self._counters.get(name, 0) + value

    def set_gauge(self, name: str, value: float):
        self._gauges[name] = value

    def record_latency(self, name: str, value_ms: float):
        if name not in self._histograms:
            self._histograms[name] = deque(maxlen=500)
        self._histograms[name].append({"value": value_ms, "ts": time.time()})
        self._latency_samples.append({"name": name, "value": round(value_ms, 2), "ts": time.time()})

    def get_snapshot(self) -> dict:
        result = {
            "uptime_seconds": round(time.time() - self._start_time, 1),
            "counters": dict(self._counters),
            "gauges": {k: round(v, 4) for k, v in self._gauges.items()},
            "histograms": {}
        }
        for name, samples in self._histograms.items():
            values = [s["value"] for s in samples]
            if values:
                sv = sorted(values)
                result["histograms"][name] = {
                    "count": len(values),
                    "avg": round(sum(values) / len(values), 2),
                    "min": round(min(values), 2),
                    "max": round(max(values), 2),
                    "p50": round(sv[len(sv) // 2], 2),
                    "p99": round(sv[int(len(sv) * 0.99)], 2) if len(sv) > 1 else round(sv[0], 2)
                }
        return result

    def get_recent_latencies(self, limit: int = 100) -> List[dict]:
        return list(self._latency_samples)[-limit:]

    def get_prometheus_text(self) -> str:
        lines = []
        for name, val in self._counters.items():
            lines.append(f"# TYPE {name} counter")
            lines.append(f"{name} {val}")
        for name, val in self._gauges.items():
            lines.append(f"# TYPE {name} gauge")
            lines.append(f"{name} {round(val, 4)}")
        return "\n".join(lines)
