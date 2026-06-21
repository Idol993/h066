from collections import defaultdict
from typing import Dict, List, Tuple
import pandas as pd
import numpy as np


class LatencyAnalyzer:
    def __init__(self):
        self.span_stats: Dict[Tuple[str, str], Dict] = {}
        self.service_stats: Dict[str, Dict] = {}

    def analyze(self, spans: List[dict]) -> Dict:
        if not spans:
            return {"span_stats": {}, "service_stats": {}, "slow_spans": []}
        df = pd.DataFrame(spans)
        grouped = df.groupby(["service_name", "operation_name"])
        for (service, operation), group in grouped:
            durations = group["duration_ms"].values
            stats = {
                "service_name": service,
                "operation_name": operation,
                "count": int(len(durations)),
                "p50_ms": float(np.percentile(durations, 50)),
                "p90_ms": float(np.percentile(durations, 90)),
                "p99_ms": float(np.percentile(durations, 99)),
                "avg_ms": float(np.mean(durations)),
                "max_ms": float(np.max(durations)),
                "min_ms": float(np.min(durations)),
                "total_ms": float(np.sum(durations)),
            }
            self.span_stats[(service, operation)] = stats
        service_grouped = df.groupby("service_name")
        for service, group in service_grouped:
            durations = group["duration_ms"].values
            self.service_stats[service] = {
                "service_name": service,
                "span_count": int(len(durations)),
                "operation_count": int(group["operation_name"].nunique()),
                "p50_ms": float(np.percentile(durations, 50)),
                "p90_ms": float(np.percentile(durations, 90)),
                "p99_ms": float(np.percentile(durations, 99)),
                "avg_ms": float(np.mean(durations)),
                "total_ms": float(np.sum(durations)),
            }
        slow_spans = sorted(
            spans,
            key=lambda s: s.get("duration_ms", 0),
            reverse=True,
        )
        return {
            "span_stats": list(self.span_stats.values()),
            "service_stats": list(self.service_stats.values()),
            "slow_spans": slow_spans,
        }

    def get_slowest_spans(self, n: int = 20) -> List[dict]:
        sorted_stats = sorted(
            self.span_stats.values(),
            key=lambda s: s["p99_ms"],
            reverse=True,
        )
        return sorted_stats[:n]

    def get_slowest_services(self, n: int = 10) -> List[dict]:
        sorted_stats = sorted(
            self.service_stats.values(),
            key=lambda s: s["total_ms"],
            reverse=True,
        )
        return sorted_stats[:n]
