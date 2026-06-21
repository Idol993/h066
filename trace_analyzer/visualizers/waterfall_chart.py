from typing import Dict, List, Optional
import plotly.graph_objects as go
import plotly.colors as pc

from ..utils.config_loader import ConfigLoader


class WaterfallChart:
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or ConfigLoader.DEFAULT_CONFIG
        self._service_color_map: Dict[str, str] = {}

    def _get_service_color(self, service_name: str, idx: int) -> str:
        if service_name in self._service_color_map:
            return self._service_color_map[service_name]
        colors = pc.qualitative.Plotly
        color = colors[idx % len(colors)]
        self._service_color_map[service_name] = color
        return color

    def _init_service_colors(self, services: List[str]) -> None:
        for i, svc in enumerate(sorted(services)):
            if svc not in self._service_color_map:
                self._get_service_color(svc, i)

    def generate_for_trace(
        self,
        trace_id: str,
        trace_tree: dict,
        spans: List[dict],
    ) -> go.Figure:
        all_services = {s.get("service_name", "unknown") for s in spans}
        self._init_service_colors(list(all_services))
        flat_nodes: List[dict] = []
        self._flatten_tree(trace_tree, flat_nodes)
        if not flat_nodes:
            flat_nodes = [
                {
                    "span": s,
                    "depth": 0,
                    "span_id": s.get("span_id"),
                }
                for s in sorted(spans, key=lambda x: x.get("timestamp_ms", 0))
            ]
        min_start = min((n["span"].get("timestamp_ms", 0) for n in flat_nodes if n.get("span")), default=0)
        y_labels = []
        x_starts = []
        x_durations = []
        colors = []
        hover_texts = []
        for node in flat_nodes:
            span = node.get("span")
            if not span:
                continue
            depth = node.get("depth", 0)
            indent = "  " * depth
            service = span.get("service_name", "unknown")
            operation = span.get("operation_name", "unknown")
            y_labels.append(f"{indent}{service}: {operation}")
            start = span.get("timestamp_ms", 0) - min_start
            duration = span.get("duration_ms", 0)
            x_starts.append(start)
            x_durations.append(duration)
            if span.get("error", False):
                colors.append(self.config["colors"]["latency_red"])
            else:
                colors.append(self._service_color_map.get(service, "#888888"))
            status = span.get("status_code", "-")
            hover_texts.append(
                f"<b>{service}</b>: {operation}<br>"
                f"Duration: {duration:.2f} ms<br>"
                f"Start: +{start:.2f} ms<br>"
                f"Status: {status}<br>"
                f"Trace: {trace_id}<br>"
                f"Span: {span.get('span_id', '')}"
            )
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                y=list(range(len(y_labels))),
                x=x_durations,
                base=x_starts,
                orientation="h",
                marker_color=colors,
                text=y_labels,
                hovertext=hover_texts,
                hoverinfo="text",
                showlegend=False,
            )
        )
        legend_traces = []
        for svc, color in sorted(self._service_color_map.items()):
            if svc in all_services:
                legend_traces.append(
                    go.Scatter(
                        x=[None],
                        y=[None],
                        mode="markers",
                        marker=dict(size=12, color=color),
                        name=svc,
                    )
                )
        for t in legend_traces:
            fig.add_trace(t)
        fig.update_layout(
            title=f"Waterfall Chart - Trace {trace_id}",
            xaxis_title="Time (ms from trace start)",
            yaxis=dict(
                tickmode="array",
                tickvals=list(range(len(y_labels))),
                ticktext=y_labels,
                autorange="reversed",
            ),
            height=max(400, len(y_labels) * 25),
            barmode="overlay",
            legend_title="Services",
            showlegend=True,
        )
        return fig

    def _flatten_tree(self, node: dict, result: List[dict]) -> None:
        if node.get("span"):
            result.append(node)
        for child in node.get("children", []):
            self._flatten_tree(child, result)

    def generate_for_traces(
        self,
        trace_builder,
        trace_ids: Optional[List[str]] = None,
    ) -> go.Figure:
        if trace_ids is None:
            trace_ids = trace_builder.get_all_trace_ids()
        all_spans = []
        for tid in trace_ids:
            all_spans.extend(trace_builder.get_trace_spans_flat(tid))
        all_services = {s.get("service_name", "unknown") for s in all_spans}
        self._init_service_colors(list(all_services))
        if trace_ids:
            first_tree = trace_builder.get_trace_tree(trace_ids[0])
            first_spans = trace_builder.get_trace_spans_flat(trace_ids[0])
            return self.generate_for_trace(trace_ids[0], first_tree or {}, first_spans)
        return go.Figure()
