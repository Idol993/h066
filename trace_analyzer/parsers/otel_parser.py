import json
from typing import List, Optional

from ..utils.time_utils import TimeUtils


class OTelParser:
    FORMAT_NAME = "otel"

    @staticmethod
    def detect_format(content: str) -> bool:
        try:
            data = json.loads(content)
            return "resourceSpans" in data
        except (json.JSONDecodeError, TypeError):
            return False

    @staticmethod
    def parse_file(file_path: str, progress_callback=None) -> List[dict]:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return OTelParser.parse_content(content, progress_callback)

    @staticmethod
    def parse_content(content: str, progress_callback=None) -> List[dict]:
        data = json.loads(content)
        spans: List[dict] = []
        total = OTelParser._count_spans(data)
        processed = 0
        for resource_span in data.get("resourceSpans", []):
            resource = resource_span.get("resource", {})
            resource_attrs = OTelParser._parse_attrs(resource.get("attributes", []))
            service_name = resource_attrs.get("service.name", "unknown")
            for scope_span in resource_span.get("scopeSpans", []):
                for span in scope_span.get("spans", []):
                    spans.append(OTelParser._convert_span(span, service_name))
                    processed += 1
                    if progress_callback:
                        progress_callback(processed, total)
        return spans

    @staticmethod
    def _count_spans(data: dict) -> int:
        count = 0
        for rs in data.get("resourceSpans", []):
            for ss in rs.get("scopeSpans", []):
                count += len(ss.get("spans", []))
        return count

    @staticmethod
    def _convert_span(span: dict, service_name: str) -> dict:
        attrs = OTelParser._parse_attrs(span.get("attributes", []))
        status = span.get("status", {})
        status_code = status.get("code")
        error = status_code in ("STATUS_CODE_ERROR", 2)
        http_status = attrs.get("http.status_code")
        if http_status is not None:
            try:
                status_code = str(http_status)
                error = error or not status_code.startswith("2")
            except (TypeError, ValueError):
                pass
        timestamp_ms = TimeUtils.epoch_ns_to_ms(span.get("startTimeUnixNano", 0))
        end_time_ms = TimeUtils.epoch_ns_to_ms(span.get("endTimeUnixNano", 0))
        duration_ms = max(0, end_time_ms - timestamp_ms)
        parent_span_id = span.get("parentSpanId")
        if parent_span_id == "":
            parent_span_id = None
        return {
            "trace_id": span.get("traceId", ""),
            "span_id": span.get("spanId", ""),
            "parent_span_id": parent_span_id,
            "service_name": service_name,
            "operation_name": span.get("name", "unknown"),
            "timestamp_ms": timestamp_ms,
            "duration_ms": duration_ms,
            "error": error,
            "status_code": str(status_code) if status_code else None,
            "tags": attrs,
            "events": span.get("events", []),
        }

    @staticmethod
    def _parse_attrs(attrs: list) -> dict:
        result = {}
        for attr in attrs:
            key = attr.get("key")
            value = attr.get("value", {})
            for k in ("stringValue", "intValue", "boolValue", "doubleValue"):
                if k in value:
                    result[key] = value[k]
                    break
        return result
