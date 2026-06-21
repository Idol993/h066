import json
from typing import List, Optional

from ..utils.time_utils import TimeUtils


class JaegerParser:
    FORMAT_NAME = "jaeger"

    @staticmethod
    def detect_format(content: str) -> bool:
        try:
            data = json.loads(content)
            if isinstance(data, dict) and "data" in data:
                traces = data.get("data", [])
                if isinstance(traces, list) and len(traces) > 0:
                    first = traces[0]
                    return "spans" in first and "traceID" in first
            if isinstance(data, list) and len(data) > 0:
                first = data[0]
                return "spans" in first and "traceID" in first
            return False
        except (json.JSONDecodeError, TypeError):
            return False

    @staticmethod
    def parse_file(file_path: str, progress_callback=None) -> List[dict]:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return JaegerParser.parse_content(content, progress_callback)

    @staticmethod
    def parse_content(content: str, progress_callback=None) -> List[dict]:
        data = json.loads(content)
        if isinstance(data, dict):
            traces = data.get("data", [])
        else:
            traces = data
        spans: List[dict] = []
        total = sum(len(t.get("spans", [])) for t in traces) if isinstance(traces, list) else 0
        processed = 0
        if isinstance(traces, list):
            for trace in traces:
                trace_id = trace.get("traceID", "")
                process = trace.get("processes", {})
                for span in trace.get("spans", []):
                    spans.append(JaegerParser._convert_span(span, trace_id, process))
                    processed += 1
                    if progress_callback:
                        progress_callback(processed, total)
        return spans

    @staticmethod
    def _convert_span(span: dict, trace_id: str, processes: dict) -> dict:
        process_id = span.get("processID", "")
        process = processes.get(process_id, {})
        service_name = process.get("serviceName", "unknown")
        tags_raw = process.get("tags", []) + span.get("tags", [])
        tags = {t.get("key"): JaegerParser._get_tag_value(t) for t in tags_raw}
        parent_span_id = None
        for ref in span.get("references", []):
            if ref.get("refType") == "CHILD_OF":
                parent_span_id = ref.get("spanID")
                break
        timestamp_ms = TimeUtils.normalize_to_epoch_ms(span.get("startTime", 0))
        duration_ms = TimeUtils.epoch_us_to_ms(span.get("duration", 0))
        error = tags.get("error", False)
        status_code = tags.get("http.status_code")
        if status_code is not None:
            try:
                status_code = str(status_code)
                error = error or not status_code.startswith("2")
            except (TypeError, ValueError):
                pass
        return {
            "trace_id": trace_id,
            "span_id": span.get("spanID", ""),
            "parent_span_id": parent_span_id,
            "service_name": service_name,
            "operation_name": span.get("operationName", "unknown"),
            "timestamp_ms": timestamp_ms,
            "duration_ms": duration_ms,
            "error": error,
            "status_code": status_code,
            "tags": tags,
            "logs": span.get("logs", []),
        }

    @staticmethod
    def _get_tag_value(tag: dict):
        for key in ("value", "vStr", "vBool", "vInt64", "vFloat64"):
            if key in tag:
                return tag[key]
        return None
