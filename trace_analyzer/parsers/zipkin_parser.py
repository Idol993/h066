import json
from typing import List, Optional

from ..utils.time_utils import TimeUtils


class ZipkinParser:
    FORMAT_NAME = "zipkin"

    @staticmethod
    def detect_format(content: str) -> bool:
        try:
            data = json.loads(content)
            if isinstance(data, list) and len(data) > 0:
                first = data[0]
                required = {"traceId", "id", "name"}
                return required.issubset(set(first.keys()))
            return False
        except (json.JSONDecodeError, TypeError):
            return False

    @staticmethod
    def parse_file(file_path: str, progress_callback=None) -> List[dict]:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return ZipkinParser.parse_content(content, progress_callback)

    @staticmethod
    def parse_content(content: str, progress_callback=None) -> List[dict]:
        data = json.loads(content)
        spans: List[dict] = []
        total = len(data) if isinstance(data, list) else 0
        for i, span in enumerate(data):
            spans.append(ZipkinParser._convert_span(span))
            if progress_callback:
                progress_callback(i + 1, total)
        return spans

    @staticmethod
    def _convert_span(span: dict) -> dict:
        local_endpoint = span.get("localEndpoint", {})
        remote_endpoint = span.get("remoteEndpoint", {})
        service_name = local_endpoint.get("serviceName") or remote_endpoint.get("serviceName") or "unknown"
        tags = span.get("tags", {})
        timestamp_ms = TimeUtils.normalize_to_epoch_ms(span.get("timestamp", 0))
        duration_ms = TimeUtils.epoch_us_to_ms(span.get("duration", 0))
        status_code = tags.get("http.status_code") if isinstance(tags, dict) else None
        error = False
        if status_code is not None:
            try:
                status_code = str(status_code)
                error = not status_code.startswith("2")
            except (TypeError, ValueError):
                pass
        if isinstance(tags, dict) and "error" in tags:
            error = True
        return {
            "trace_id": span.get("traceId", ""),
            "span_id": span.get("id", ""),
            "parent_span_id": span.get("parentId"),
            "service_name": service_name,
            "operation_name": span.get("name", "unknown"),
            "timestamp_ms": timestamp_ms,
            "duration_ms": duration_ms,
            "error": error,
            "status_code": status_code,
            "tags": tags if isinstance(tags, dict) else {},
            "annotations": span.get("annotations", []),
        }
