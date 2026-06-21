from typing import Dict, List, Optional

from ..utils.time_utils import TimeUtils


class SummaryGenerator:
    def generate_text_summary(
        self,
        latency_stats: List[Dict],
        error_summary: Dict,
        bottleneck_services: Optional[List[Dict]] = None,
        total_traces: int = 0,
        total_spans: int = 0,
    ) -> str:
        lines = []
        lines.append("=" * 60)
        lines.append("DISTRIBUTED TRACE ANALYSIS SUMMARY")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"Total traces analyzed: {total_traces}")
        lines.append(f"Total spans analyzed: {total_spans}")
        lines.append("")
        overall_rate = error_summary.get("overall_error_rate", 0.0)
        total_errors = error_summary.get("total_errors", 0)
        lines.append(f"Overall error rate: {overall_rate * 100:.2f}% ({total_errors} errors)")
        lines.append("")
        lines.append("-" * 60)
        lines.append("TOP SLOWEST OPERATIONS")
        lines.append("-" * 60)
        if latency_stats:
            for i, stat in enumerate(latency_stats[:10], 1):
                service = stat.get("service_name", "-")
                operation = stat.get("operation_name", "-")
                p99 = stat.get("p99_ms", 0)
                avg = stat.get("avg_ms", 0)
                count = stat.get("count", 0)
                lines.append(
                    f"{i}. {service} / {operation}: "
                    f"P99={p99:.2f}ms, Avg={avg:.2f}ms, Count={count}"
                )
        else:
            lines.append("  (no data)")
        lines.append("")
        high_error_services = [
            s for s in error_summary.get("services", [])
            if s.get("error_rate", 0) >= 0.01
        ]
        lines.append("-" * 60)
        lines.append("HIGH ERROR SERVICES")
        lines.append("-" * 60)
        if high_error_services:
            for s in high_error_services[:10]:
                svc = s.get("service_name", "-")
                rate = s.get("error_rate", 0) * 100
                ec = s.get("error_count", 0)
                tc = s.get("total_count", 0)
                lines.append(f"  - {svc}: {rate:.2f}% error rate ({ec}/{tc} spans)")
        else:
            lines.append("  No services with error rate >= 1%")
        lines.append("")
        if bottleneck_services:
            lines.append("-" * 60)
            lines.append("BOTTLENECK SERVICES (by critical path time)")
            lines.append("-" * 60)
            for i, b in enumerate(bottleneck_services[:10], 1):
                svc = b.get("service_name", "-")
                total = b.get("total_critical_duration_ms", 0)
                count = b.get("critical_count", 0)
                lines.append(
                    f"{i}. {svc}: {TimeUtils.format_duration_ms(total)} "
                    f"across {count} critical path occurrences"
                )
            lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)

    def generate_brief_hint(self, latency_stats: List[Dict], error_summary: Dict) -> str:
        hints = []
        if latency_stats:
            slowest = latency_stats[0]
            hints.append(
                f"Slowest operation: {slowest.get('service_name')} {slowest.get('operation_name')} "
                f"(P99={slowest.get('p99_ms', 0):.2f}ms)"
            )
        high_error = [
            s for s in error_summary.get("services", [])
            if s.get("error_rate", 0) >= 0.05
        ]
        if high_error:
            worst = high_error[0]
            hints.append(
                f"Highest error rate: {worst.get('service_name')} "
                f"({worst.get('error_rate', 0) * 100:.2f}%)"
            )
        overall = error_summary.get("overall_error_rate", 0)
        if overall >= 0.05:
            hints.append("⚠️  Overall error rate exceeds 5% threshold")
        if not hints:
            hints.append("No significant issues detected")
        return " | ".join(hints)
