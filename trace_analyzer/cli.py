import os
import sys
import json
from typing import Optional, List
import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn, TimeRemainingColumn

from trace_analyzer.parsers.jaeger_parser import JaegerParser
from trace_analyzer.parsers.zipkin_parser import ZipkinParser
from trace_analyzer.parsers.otel_parser import OTelParser
from trace_analyzer.parsers.jsonl_parser import JSONLParser
from trace_analyzer.analyzers.trace_builder import TraceBuilder
from trace_analyzer.analyzers.latency_analyzer import LatencyAnalyzer
from trace_analyzer.analyzers.error_aggregator import ErrorAggregator
from trace_analyzer.analyzers.critical_path import CriticalPathFinder
from trace_analyzer.visualizers.waterfall_chart import WaterfallChart
from trace_analyzer.visualizers.flame_graph import FlameGraph
from trace_analyzer.visualizers.html_exporter import HTMLExporter
from trace_analyzer.reporters.terminal_reporter import TerminalReporter
from trace_analyzer.reporters.json_exporter import JSONExporter
from trace_analyzer.reporters.summary_generator import SummaryGenerator
from trace_analyzer.utils.config_loader import ConfigLoader
from trace_analyzer.utils.span_filters import SpanFilters
from trace_analyzer.utils.time_utils import TimeUtils

console = Console()
PARSERS = [JaegerParser, ZipkinParser, OTelParser, JSONLParser]


def auto_detect_format(file_path: str) -> Optional[type]:
    try:
        file_size = os.path.getsize(file_path)
        read_size = min(file_size, 64 * 1024)
        with open(file_path, "r", encoding="utf-8") as f:
            sample = f.read(read_size)
        if not sample.strip():
            return None
        lower_path = file_path.lower()
        if lower_path.endswith(".jsonl") or "jsonl" in lower_path:
            return JSONLParser
        if "zipkin" in lower_path:
            return ZipkinParser
        if "jaeger" in lower_path:
            return JaegerParser
        if "otel" in lower_path or "otlp" in lower_path:
            return OTelParser
        for parser_cls in PARSERS:
            try:
                if parser_cls.detect_format(sample):
                    return parser_cls
            except Exception:
                continue
        try:
            data = json.loads(sample)
            if isinstance(data, list) and len(data) > 0:
                first = data[0]
                if "traceId" in first and "id" in first:
                    return ZipkinParser
                if "traceID" in first and "spans" in first:
                    return JaegerParser
            if isinstance(data, dict) and "resourceSpans" in data:
                return OTelParser
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            first_line = sample.strip().split("\n")[0]
            obj = json.loads(first_line)
            if isinstance(obj, dict):
                if any(k in obj for k in ("trace_id", "traceId", "span_id", "spanId")):
                    return JSONLParser
        except (json.JSONDecodeError, IndexError):
            pass
    except Exception:
        pass
    return None


def parse_file(file_path: str, format_name: Optional[str] = None) -> List[dict]:
    parser_cls = None
    if format_name:
        format_map = {
            "jaeger": JaegerParser,
            "zipkin": ZipkinParser,
            "otel": OTelParser,
            "jsonl": JSONLParser,
        }
        parser_cls = format_map.get(format_name.lower())
        if not parser_cls:
            raise click.BadParameter(f"Unknown format: {format_name}")
    else:
        parser_cls = auto_detect_format(file_path)
        if not parser_cls:
            raise click.BadParameter(f"Cannot auto-detect format for: {file_path}. Use --format to specify.")
    console.print(f"[cyan]Using parser:[/cyan] {parser_cls.FORMAT_NAME}")
    spans = []
    file_size = os.path.getsize(file_path)
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(f"Parsing {os.path.basename(file_path)}", total=None)
        def on_progress(current, total):
            if total:
                progress.update(task, total=total, completed=current)
            else:
                progress.update(task, completed=current)
        spans = parser_cls.parse_file(file_path, progress_callback=on_progress)
        progress.update(task, completed=len(spans), total=len(spans))
    console.print(f"[green]Parsed {len(spans)} spans from {file_path}[/green]")
    return spans


@click.group()
@click.version_option(version="1.0.0", prog_name="trace-analyzer")
@click.option("--config", "config_path", type=click.Path(exists=True), help="Path to YAML config file")
@click.pass_context
def cli(ctx, config_path):
    ctx.ensure_object(dict)
    ctx.obj["config"] = ConfigLoader.load(config_path)


@cli.command()
@click.argument("input_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--format", "format_name", type=click.Choice(["jaeger", "zipkin", "otel", "jsonl"]), help="Trace format (auto-detect if not specified)")
@click.option("--output", "-o", type=click.Path(), help="Output JSON file for parsed spans")
@click.option("--service", help="Filter by service name")
@click.option("--min-duration", type=float, help="Minimum duration in ms")
@click.pass_context
def parse(ctx, input_file, format_name, output, service, min_duration):
    config = ctx.obj["config"]
    spans = parse_file(input_file, format_name)
    if service:
        spans = SpanFilters.filter_by_service(spans, service)
        console.print(f"Filtered to {len(spans)} spans for service: {service}")
    if min_duration:
        spans = SpanFilters.filter_min_duration(spans, min_duration)
        console.print(f"Filtered to {len(spans)} spans >= {min_duration}ms")
    if output:
        with open(output, "w", encoding="utf-8") as f:
            json.dump(spans, f, indent=2, default=str)
        console.print(f"[green]Parsed spans saved to: {output}[/green]")
    else:
        console.print(f"[blue]Summary:[/blue] {len(spans)} spans, {len(SpanFilters.get_unique_services(spans))} services")


@cli.command()
@click.argument("input_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--format", "format_name", type=click.Choice(["jaeger", "zipkin", "otel", "jsonl"]), help="Trace format")
@click.option("--output", "-o", type=click.Path(), help="Output JSON report path")
@click.option("--top-n", type=int, default=20, help="Number of top slow spans to show")
@click.option("--service", help="Filter by service name")
@click.pass_context
def analyze(ctx, input_file, format_name, output, top_n, service):
    config = ctx.obj["config"]
    spans = parse_file(input_file, format_name)
    if service:
        spans = SpanFilters.filter_by_service(spans, service)
    reporter = TerminalReporter(config)
    summary_gen = SummaryGenerator()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Building trace trees...", total=None)
        builder = TraceBuilder()
        traces = builder.build(spans)
        progress.add_task("Analyzing latency...", total=None)
        latency = LatencyAnalyzer()
        latency_result = latency.analyze(spans)
        progress.add_task("Aggregating errors...", total=None)
        error_agg = ErrorAggregator()
        error_result = error_agg.aggregate(spans)
        progress.add_task("Finding critical paths...", total=None)
        cp_finder = CriticalPathFinder()
        cp_finder.find_all(builder)
    reporter.print_summary(
        total_spans=len(spans),
        total_traces=len(traces),
        error_summary=error_result,
    )
    slowest = latency.get_slowest_spans(top_n)
    reporter.print_slowest_spans(slowest, top_n)
    reporter.print_error_summary(error_result.get("services", []))
    slowest_traces = cp_finder.get_slowest_traces(n=3)
    for trace_id, path, dur in slowest_traces:
        reporter.print_critical_path(trace_id, path, dur)
    bottlenecks = cp_finder.get_bottleneck_services()
    if bottlenecks:
        console.rule("[bold blue]Bottleneck Services")
        for i, b in enumerate(bottlenecks[:10], 1):
            console.print(f"  {i}. {b['service_name']}: {TimeUtils.format_duration_ms(b['total_critical_duration_ms'])} across {b['critical_count']} occurrences")
    hint = summary_gen.generate_brief_hint(slowest, error_result)
    console.rule("[bold]Quick Hint")
    console.print(hint)
    if output:
        exporter = JSONExporter()
        out_path = exporter.export(
            output_path=output,
            critical_paths=cp_finder.critical_paths,
            slow_spans=latency_result.get("slow_spans", []),
            error_summary=error_result,
            latency_stats={"span_stats": latency_result.get("span_stats", []), "service_stats": latency_result.get("service_stats", [])},
            bottlenecks=bottlenecks,
            extra={
                "total_spans": len(spans),
                "total_traces": len(traces),
                "slowest_spans": slowest,
            },
        )
        console.print(f"[green]JSON report saved to: {out_path}[/green]")


@cli.command()
@click.argument("input_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--format", "format_name", type=click.Choice(["jaeger", "zipkin", "otel", "jsonl"]), help="Trace format")
@click.option("--output", "-o", type=click.Path(), help="Output HTML path")
@click.option("--trace-id", help="Specific trace ID for waterfall chart")
@click.option("--service", help="Filter by service name")
@click.pass_context
def visualize(ctx, input_file, format_name, output, trace_id, service):
    config = ctx.obj["config"]
    spans = parse_file(input_file, format_name)
    if service:
        spans = SpanFilters.filter_by_service(spans, service)
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Building trace trees...", total=None)
        builder = TraceBuilder()
        traces = builder.build(spans)
        progress.add_task("Analyzing latency...", total=None)
        latency = LatencyAnalyzer()
        latency_result = latency.analyze(spans)
        progress.add_task("Aggregating errors...", total=None)
        error_agg = ErrorAggregator()
        error_result = error_agg.aggregate(spans)
        progress.add_task("Finding critical paths...", total=None)
        cp_finder = CriticalPathFinder()
        cp_finder.find_all(builder)
        progress.add_task("Generating charts...", total=None)
        waterfall = WaterfallChart(config)
        flame = FlameGraph(config)
        exporter = HTMLExporter()
        target_trace_id = trace_id
        if not target_trace_id:
            slowest = cp_finder.get_slowest_traces(n=1)
            if slowest:
                target_trace_id = slowest[0][0]
        waterfall_fig = None
        if target_trace_id:
            tree = builder.get_trace_tree(target_trace_id) or {}
            trace_spans = builder.get_trace_spans_flat(target_trace_id)
            waterfall_fig = waterfall.generate_for_trace(target_trace_id, tree, trace_spans)
        else:
            waterfall_fig = waterfall.generate_for_traces(builder)
        flame_fig = flame.generate(spans)
        timeline_fig = flame.generate_timeline(spans)
        summary = {
            "total_spans": len(spans),
            "total_traces": len(traces),
            "total_errors": error_result.get("total_errors", 0),
            "overall_error_rate": error_result.get("overall_error_rate", 0.0),
            "slowest_spans": latency.get_slowest_spans(20),
            "error_services": error_result.get("services", []),
        }
    ts = TimeUtils.now_timestamp()
    if not output:
        output = f"trace_analysis_{ts}.html"
    out_path = exporter.export_combined(
        output_path=output,
        waterfall_fig=waterfall_fig,
        flame_fig=flame_fig,
        timeline_fig=timeline_fig,
        summary=summary,
    )
    console.print(f"[green]HTML report saved to: {out_path}[/green]")
    console.print("[cyan]Open this file in your browser to view interactive charts[/cyan]")


def main():
    try:
        cli(obj={})
    except click.BadParameter as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(2)
    except Exception as e:
        console.print(f"[bold red]Unexpected error:[/bold red] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
