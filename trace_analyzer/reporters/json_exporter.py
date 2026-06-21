import json
import time
from typing import Dict, List, Optional

from ..utils.time_utils import TimeUtils


class JSONExporter:
    def export(
        self,
        output_path: str,
        critical_paths: Optional[Dict[str, List[Dict]]] = None,
        slow_spans: Optional[List[Dict]] = None,
        error_summary: Optional[Dict] = None,
        latency_stats: Optional[Dict] = None,
        bottlenecks: Optional[List[Dict]] = None,
        extra: Optional[Dict] = None,
    ) -> str:
        timestamp = TimeUtils.now_timestamp()
        if not output_path.endswith(".json"):
            output_path = f"{output_path}_{timestamp}.json"
        result = {
            "generated_at": TimeUtils.epoch_ms_to_iso(time.time() * 1000),
            "critical_path": self._serialize_critical_paths(critical_paths or {}),
            "slow_spans": self._serialize_slow_spans(slow_spans or []),
            "error_summary": self._serialize_error_summary(error_summary or {}),
        }
        if latency_stats:
            result["latency_stats"] = latency_stats
        if bottlenecks:
            result["bottleneck_services"] = bottlenecks
        if extra:
            result.update(extra)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False, default=str)
        return output_path

    def _serialize_critical_paths(self, paths: Dict[str, List[Dict]]) -> Dict:
        serialized = {}
        for trace_id, spans in paths.items():
            total_dur = sum(s.get("duration_ms", 0) for s in spans)
            serialized[trace_id] = {
                "total_duration_ms": total_dur,
                "span_count": len(spans),
                "spans": [self._serialize_span(s) for s in spans],
            }
        sorted_paths = sorted(
            serialized.items(),
            key=lambda x: x[1]["total_duration_ms"],
            reverse=True,
        )
        return dict(sorted_paths)

    def _serialize_slow_spans(self, spans: List[Dict], top_n: int = 100) -> List[Dict]:
        return [
            {
                "service_name": s.get("service_name"),
                "operation_name": s.get("operation_name"),
                "trace_id": s.get("trace_id"),
                "span_id": s.get("span_id"),
                "duration_ms": s.get("duration_ms", 0),
                "timestamp_ms": s.get("timestamp_ms", 0),
                "error": s.get("error", False),
                "status_code": s.get("status_code"),
            }
            for s in spans[:top_n]
        ]

    def _serialize_error_summary(self, summary: Dict) -> Dict:
        services = summary.get("services", [])
        serialized_services = []
        for s in services:
            serialized_services.append({
                "service_name": s.get("service_name"),
                "total_count": s.get("total_count", 0),
                "error_count": s.get("error_count", 0),
                "error_rate": s.get("error_rate", 0.0),
                "error_types": s.get("error_types", {}),
                "error_spans": [
                    {
                        "trace_id": es.get("trace_id"),
                        "span_id": es.get("span_id"),
                        "operation_name": es.get("operation_name"),
                        "status_code": es.get("status_code"),
                        "duration_ms": es.get("duration_ms", 0),
                    }
                    for es in s.get("error_spans", [])[:10]
                ],
            })
        return {
            "total_spans": summary.get("total_spans", 0),
            "total_errors": summary.get("total_errors", 0),
            "overall_error_rate": summary.get("overall_error_rate", 0.0),
            "services": serialized_services,
        }

    def _serialize_span(self, span: Dict) -> Dict:
        return {
            "span_id": span.get("span_id"),
            "parent_span_id": span.get("parent_span_id"),
            "service_name": span.get("service_name"),
            "operation_name": span.get("operation_name"),
            "duration_ms": span.get("duration_ms", 0),
            "timestamp_ms": span.get("timestamp_ms", 0),
            "error": span.get("error", False),
            "status_code": span.get("status_code"),
            "pct_of_critical_path": span.get("pct_of_critical_path"),
        }
