import os
from typing import Any, Dict, Optional


class ConfigLoader:
    DEFAULT_CONFIG: Dict[str, Any] = {
        "thresholds": {
            "latency_green_ms": 100,
            "latency_yellow_ms": 500,
            "latency_orange_ms": 1000,
            "error_rate_high": 0.05,
            "error_rate_medium": 0.01,
        },
        "colors": {
            "latency_green": "#00ff00",
            "latency_yellow": "#ffff00",
            "latency_orange": "#ffa500",
            "latency_red": "#ff0000",
            "error_high": "#ff0000",
            "error_medium": "#ffff00",
            "error_low": "#00ff00",
        },
        "top_n": 20,
        "service_colors": {},
    }

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> Dict[str, Any]:
        config = cls.DEFAULT_CONFIG.copy()
        if config_path and os.path.exists(config_path):
            try:
                import yaml

                with open(config_path, "r", encoding="utf-8") as f:
                    user_config = yaml.safe_load(f) or {}
                config = cls._deep_merge(config, user_config)
            except ImportError:
                pass
            except Exception:
                pass
        return config

    @classmethod
    def _deep_merge(cls, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = cls._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    @staticmethod
    def get_latency_color(duration_ms: float, config: Dict[str, Any]) -> str:
        thresholds = config["thresholds"]
        colors = config["colors"]
        if duration_ms < thresholds["latency_green_ms"]:
            return colors["latency_green"]
        if duration_ms < thresholds["latency_yellow_ms"]:
            return colors["latency_yellow"]
        if duration_ms < thresholds["latency_orange_ms"]:
            return colors["latency_orange"]
        return colors["latency_red"]

    @staticmethod
    def get_error_color(error_rate: float, config: Dict[str, Any]) -> str:
        thresholds = config["thresholds"]
        colors = config["colors"]
        if error_rate >= thresholds["error_rate_high"]:
            return colors["error_high"]
        if error_rate >= thresholds["error_rate_medium"]:
            return colors["error_medium"]
        return colors["error_low"]
