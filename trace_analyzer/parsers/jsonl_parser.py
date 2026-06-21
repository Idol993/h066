import json
from typing import List, Optional

from .jaeger_parser import JaegerParser
from .zipkin_parser import ZipkinParser
from .otel_parser import OTelParser
from ..utils.time_utils import TimeUtils


class JSONLParser:
    FORMAT_NAME = "jsonl"

    @staticmethod
    def detect_format(content: str) -> bool:
        try:
            first_line = content.strip().split("\n")[0] if content.strip() else ""
            if not first_line:
                return False
            data = json.loads(first_line)
            if isinstance(data, dict):
                span_keys = {"trace_id", "traceId", "span_id", "spanId"}
                return any(k in data for k in span_keys)
            return False
        except (json.JSONDecodeError, TypeError):
            return False

    @staticmethod
    def parse_file(file_path: str, progress_callback=None) -> List[dict]:
        spans: List[dict] = []
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        total = len(lines)
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                span = JSONLParser._convert_span(data)
                if span:
                    spans.append(span)
            except json.JSONDecodeError:
                continue
            if progress_callback:
                progress_callback(i + 1, total)
        return spans

    @staticmethod
    def parse_content(content: str, progress_callback=None) -> List[dict]:
        spans: List[dict] = []
        lines = content.strip().split("\n")
        total = len(lines)
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                span = JSONLParser._convert_span(data)
                if span:
                    spans.append(span)
            except json.JSONDecodeError:
                continue
            if progress_callback:
                progress_callback(i + 1, total)
        return spans

    @staticmethod
    def _convert_span(data: dict) -> Optional[dict]:
        if "traceID" in data or "spans" in data:
            return JaegerParser._convert_span(data, data.get("traceID", ""), data.get("processes", {}))
        if "resourceSpans" in data:
            return None
        trace_id = data.get("trace_id") or data.get("traceId") or ""
        span_id = data.get("span_id") or data.get("spanId") or ""
        if not trace_id or not span_id:
            return None
        parent_span_id = data.get("parent_span_id") or data.get("parentSpanId") or data.get("parentId")
        if parent_span_id == "":
            parent_span_id = None
        service_name = data.get("service_name") or data.get("serviceName") or "unknown"
        operation_name = data.get("operation_name") or data.get("name") or data.get("operationName") or "unknown"
        timestamp = data.get("timestamp") or data.get("start_time") or data.get("startTime") or 0
        timestamp_ms = TimeUtils.normalize_to_epoch_ms(timestamp)
        duration = data.get("duration") or data.get("duration_ms") or 0
        if duration > 1e6:
            duration_ms = TimeUtils.epoch_ns_to_ms(duration)
        elif duration > 1e3:
            duration_ms = TimeUtils.epoch_us_to_ms(duration)
        else:
            duration_ms = float(duration)
        error = data.get("error", False)
        status_code = data.get("status_code")
        if status_code is not None:
            try:
                status_code = str(status_code)
                error = error or not status_code.startswith("2")
            except (TypeError, ValueError):
                pass
        return {
            "trace_id": trace_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "service_name": service_name,
            "operation_name": operation_name,
            "timestamp_ms": timestamp_ms,
            "duration_ms": duration_ms,
            "error": error,
            "status_code": status_code,
            "tags": data.get("tags", {}),
            "logs": data.get("logs", []),
        }
