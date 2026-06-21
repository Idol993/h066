from typing import Dict, List, Optional
from rich.console import Console
from rich.table import Table
from rich.tree import Tree
from rich import box
from rich.text import Text

from ..utils.config_loader import ConfigLoader
from ..utils.time_utils import TimeUtils


class TerminalReporter:
    def __init__(self, config: Optional[Dict] = None):
        self.console = Console()
        self.config = config or ConfigLoader.DEFAULT_CONFIG

    def print_summary(
        self,
        total_spans: int,
        total_traces: int,
        error_summary: Optional[Dict] = None,
    ):
        self.console.rule("[bold blue]Trace Analysis Summary[/bold blue]")
        table = Table(box=box.ROUNDED, show_header=True, header_style="bold magenta")
        table.add_column("Metric")
        table.add_column("Value", justify="right")
        table.add_row("Total Spans", f"{total_spans:,}")
        table.add_row("Total Traces", f"{total_traces:,}")
        if error_summary:
            total_errors = error_summary.get("total_errors", 0)
            error_rate = error_summary.get("overall_error_rate", 0.0) * 100
            rate_style = self._get_error_rate_style(error_rate / 100)
            table.add_row("Total Errors", f"[red]{total_errors:,}[/red]" if total_errors > 0 else f"[green]{total_errors:,}[/green]")
            table.add_row("Overall Error Rate", Text(f"{error_rate:.2f}%", style=rate_style))
        self.console.print(table)

    def print_slowest_spans(self, span_stats: List[Dict], top_n: int = 20):
        self.console.rule(f"[bold blue]Top-{top_n} Slowest Operations (by P99)[/bold blue]")
        if not span_stats:
            self.console.print("[yellow]No span data available[/yellow]")
            return
        table = Table(box=box.ROUNDED, show_header=True, header_style="bold magenta")
        table.add_column("#", justify="right")
        table.add_column("Service")
        table.add_column("Operation")
        table.add_column("Count", justify="right")
        table.add_column("P50 (ms)", justify="right")
        table.add_column("P90 (ms)", justify="right")
        table.add_column("P99 (ms)", justify="right")
        table.add_column("Avg (ms)", justify="right")
        for i, stat in enumerate(span_stats[:top_n], 1):
            p99 = stat.get("p99_ms", 0)
            color = self._get_latency_color(p99)
            table.add_row(
                str(i),
                stat.get("service_name", "-"),
                stat.get("operation_name", "-"),
                str(stat.get("count", 0)),
                f"{stat.get('p50_ms', 0):.2f}",
                f"{stat.get('p90_ms', 0):.2f}",
                Text(f"{p99:.2f}", style=color),
                f"{stat.get('avg_ms', 0):.2f}",
            )
        self.console.print(table)

    def print_error_summary(self, error_services: List[Dict], top_n: int = 10):
        self.console.rule(f"[bold blue]Error Summary (Top-{top_n})[/bold blue]")
        if not error_services:
            self.console.print("[green]No errors found[/green]")
            return
        table = Table(box=box.ROUNDED, show_header=True, header_style="bold magenta")
        table.add_column("Service")
        table.add_column("Total", justify="right")
        table.add_column("Errors", justify="right")
        table.add_column("Error Rate", justify="right")
        table.add_column("Top Error Types")
        for s in error_services[:top_n]:
            rate = s.get("error_rate", 0)
            style = self._get_error_rate_style(rate)
            error_types = s.get("error_types", {})
            type_str = ", ".join(f"{k}:{v}" for k, v in list(error_types.items())[:3])
            table.add_row(
                s.get("service_name", "-"),
                str(s.get("total_count", 0)),
                f"[red]{s.get('error_count', 0)}[/red]",
                Text(f"{rate * 100:.2f}%", style=style),
                type_str or "-",
            )
        self.console.print(table)

    def print_critical_path(self, trace_id: str, path: List[Dict], duration_ms: float):
        self.console.rule(f"[bold red]Critical Path - Trace {trace_id}[/bold red]")
        if not path:
            self.console.print("[yellow]No critical path found[/yellow]")
            return
        total = TimeUtils.format_duration_ms(duration_ms)
        self.console.print(f"[bold]Total critical path duration:[/bold] [red]{total}[/red]")
        table = Table(box=box.ROUNDED, show_header=True, header_style="bold magenta")
        table.add_column("#", justify="right")
        table.add_column("Service")
        table.add_column("Operation")
        table.add_column("Duration", justify="right")
        table.add_column("% of Total", justify="right")
        for i, span in enumerate(path, 1):
            dur = span.get("duration_ms", 0)
            pct = (dur / duration_ms * 100) if duration_ms > 0 else 0
            color = self._get_latency_color(dur)
            table.add_row(
                str(i),
                span.get("service_name", "-"),
                span.get("operation_name", "-"),
                Text(TimeUtils.format_duration_ms(dur), style=color),
                f"{pct:.1f}%",
            )
        self.console.print(table)

    def print_trace_tree(self, tree: dict):
        self.console.rule("[bold blue]Trace Tree[/bold blue]")
        if not tree:
            self.console.print("[yellow]No trace tree available[/yellow]")
            return
        root_label = self._format_span_label(tree)
        rich_tree = Tree(root_label)
        self._build_rich_tree(tree, rich_tree)
        self.console.print(rich_tree)

    def _build_rich_tree(self, node: dict, parent: Tree):
        for child in node.get("children", []):
            label = self._format_span_label(child)
            child_tree = parent.add(label)
            self._build_rich_tree(child, child_tree)

    def _format_span_label(self, node: dict) -> Text:
        span = node.get("span")
        if not span:
            return Text("(virtual root)")
        service = span.get("service_name", "unknown")
        operation = span.get("operation_name", "unknown")
        duration = span.get("duration_ms", 0)
        color = self._get_latency_color(duration)
        is_error = span.get("error", False)
        label = Text()
        label.append(f"[{service}] ", style="bold cyan")
        label.append(operation)
        label.append(f" ({TimeUtils.format_duration_ms(duration)})", style=color)
        if is_error:
            label.append(" [ERROR]", style="bold red")
        return label

    def _get_latency_color(self, duration_ms: float) -> str:
        thresholds = self.config["thresholds"]
        if duration_ms < thresholds["latency_green_ms"]:
            return "green"
        if duration_ms < thresholds["latency_yellow_ms"]:
            return "yellow"
        if duration_ms < thresholds["latency_orange_ms"]:
            return "dark_orange"
        return "bold red"

    def _get_error_rate_style(self, error_rate: float) -> str:
        thresholds = self.config["thresholds"]
        if error_rate >= thresholds["error_rate_high"]:
            return "bold red"
        if error_rate >= thresholds["error_rate_medium"]:
            return "yellow"
        return "green"
