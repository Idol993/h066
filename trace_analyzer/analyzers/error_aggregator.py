from collections import Counter, defaultdict
from typing import Dict, List


class ErrorAggregator:
    def __init__(self):
        self.service_errors: Dict[str, Dict] = {}

    def aggregate(self, spans: List[dict]) -> Dict:
        service_stats: Dict[str, Dict] = defaultdict(lambda: {
            "total_count": 0,
            "error_count": 0,
            "error_types": Counter(),
            "error_spans": [],
        })
        for span in spans:
            service = span.get("service_name", "unknown")
            service_stats[service]["total_count"] += 1
            if span.get("error", False):
                service_stats[service]["error_count"] += 1
                status = span.get("status_code") or "unknown"
                service_stats[service]["error_types"][str(status)] += 1
                service_stats[service]["error_spans"].append({
                    "trace_id": span.get("trace_id", ""),
                    "span_id": span.get("span_id", ""),
                    "operation_name": span.get("operation_name", ""),
                    "status_code": span.get("status_code"),
                    "duration_ms": span.get("duration_ms", 0),
                })
        for service, stats in service_stats.items():
            total = stats["total_count"]
            stats["service_name"] = service
            stats["error_rate"] = stats["error_count"] / total if total > 0 else 0.0
            stats["error_types"] = dict(stats["error_types"].most_common())
            self.service_errors[service] = stats
        sorted_services = sorted(
            self.service_errors.values(),
            key=lambda s: s["error_rate"],
            reverse=True,
        )
        return {
            "services": sorted_services,
            "total_spans": len(spans),
            "total_errors": sum(s["error_count"] for s in self.service_errors.values()),
            "overall_error_rate": (
                sum(s["error_count"] for s in self.service_errors.values()) / len(spans)
                if spans else 0.0
            ),
        }

    def get_high_error_services(self, threshold: float = 0.05) -> List[dict]:
        return [s for s in self.service_errors.values() if s["error_rate"] >= threshold]
