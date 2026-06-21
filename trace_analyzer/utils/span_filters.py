from typing import List, Optional


class SpanFilters:
    @staticmethod
    def filter_by_service(spans: List[dict], service_name: str) -> List[dict]:
        return [s for s in spans if s.get("service_name") == service_name]

    @staticmethod
    def filter_by_operation(spans: List[dict], operation_name: str) -> List[dict]:
        return [s for s in spans if s.get("operation_name") == operation_name]

    @staticmethod
    def filter_by_time_range(
        spans: List[dict], start_ms: Optional[float] = None, end_ms: Optional[float] = None
    ) -> List[dict]:
        result = []
        for s in spans:
            ts = s.get("timestamp_ms", 0)
            if start_ms is not None and ts < start_ms:
                continue
            if end_ms is not None and ts > end_ms:
                continue
            result.append(s)
        return result

    @staticmethod
    def filter_min_duration(spans: List[dict], min_duration_ms: float) -> List[dict]:
        return [s for s in spans if s.get("duration_ms", 0) >= min_duration_ms]

    @staticmethod
    def filter_errors(spans: List[dict]) -> List[dict]:
        return [s for s in spans if s.get("error", False)]

    @staticmethod
    def get_unique_services(spans: List[dict]) -> List[str]:
        return sorted({s.get("service_name", "unknown") for s in spans})

    @staticmethod
    def get_unique_operations(spans: List[dict]) -> List[str]:
        return sorted({s.get("operation_name", "unknown") for s in spans})
