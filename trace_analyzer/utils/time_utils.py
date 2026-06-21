from datetime import datetime, timezone
from typing import Union


class TimeUtils:
    @staticmethod
    def epoch_ms_to_iso(epoch_ms: Union[int, float]) -> str:
        dt = datetime.fromtimestamp(epoch_ms / 1000.0, tz=timezone.utc)
        return dt.isoformat()

    @staticmethod
    def iso_to_epoch_ms(iso_str: str) -> int:
        if iso_str.endswith("Z"):
            iso_str = iso_str[:-1] + "+00:00"
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)

    @staticmethod
    def epoch_us_to_ms(epoch_us: Union[int, float]) -> float:
        return epoch_us / 1000.0

    @staticmethod
    def epoch_ns_to_ms(epoch_ns: Union[int, float]) -> float:
        return epoch_ns / 1_000_000.0

    @staticmethod
    def normalize_to_epoch_ms(value: Union[int, float, str]) -> float:
        if isinstance(value, str):
            return TimeUtils.iso_to_epoch_ms(value)
        if value > 1e18:
            return TimeUtils.epoch_ns_to_ms(value)
        if value > 1e12:
            return TimeUtils.epoch_us_to_ms(value)
        return float(value)

    @staticmethod
    def format_duration_ms(duration_ms: float) -> str:
        if duration_ms >= 1000:
            return f"{duration_ms / 1000:.2f}s"
        if duration_ms >= 1:
            return f"{duration_ms:.2f}ms"
        if duration_ms >= 0.001:
            return f"{duration_ms * 1000:.2f}μs"
        return f"{duration_ms * 1_000_000:.2f}ns"

    @staticmethod
    def now_timestamp() -> str:
        return datetime.now().strftime("%Y%m%d_%H%M%S")
