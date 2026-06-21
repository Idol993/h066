from typing import Dict, List, Optional
import plotly.graph_objects as go
import plotly.colors as pc

from ..utils.config_loader import ConfigLoader


class FlameGraph:
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

    def generate(self, spans: List[dict]) -> go.Figure:
        if not spans:
            return go.Figure()
        all_services = {s.get("service_name", "unknown") for s in spans}
        self._init_service_colors(list(all_services))
        from collections import defaultdict
        agg = defaultdict(lambda: {"total_ms": 0.0, "count": 0, "service": "", "children": defaultdict(lambda: {"total_ms": 0.0, "count": 0, "service": ""})})
        for span in spans:
            svc = span.get("service_name", "unknown")
            op = span.get("operation_name", "unknown")
            dur = span.get("duration_ms", 0)
            agg[(svc, op)]["total_ms"] += dur
            agg[(svc, op)]["count"] += 1
            agg[(svc, op)]["service"] = svc
        items = []
        for (svc, op), data in sorted(agg.items(), key=lambda x: x[1]["total_ms"], reverse=True):
            items.append({
                "service": svc,
                "operation": op,
                "total_ms": data["total_ms"],
                "count": data["count"],
                "avg_ms": data["total_ms"] / data["count"] if data["count"] > 0 else 0,
            })
        labels = []
        parents = []
        values = []
        colors = []
        hover_texts = []
        service_total: Dict[str, float] = defaultdict(float)
        for it in items:
            service_total[it["service"]] += it["total_ms"]
        for svc in sorted(service_total.keys()):
            labels.append(svc)
            parents.append("")
            values.append(service_total[svc])
            colors.append(self._service_color_map.get(svc, "#888888"))
            hover_texts.append(
                f"<b>{svc}</b><br>"
                f"Total: {service_total[svc]:.2f} ms<br>"
            )
        for it in items:
            label = f"{it['service']}: {it['operation']}"
            labels.append(label)
            parents.append(it["service"])
            values.append(it["total_ms"])
            colors.append(self._service_color_map.get(it["service"], "#888888"))
            hover_texts.append(
                f"<b>{it['service']}</b>: {it['operation']}<br>"
                f"Total: {it['total_ms']:.2f} ms<br>"
                f"Count: {it['count']}<br>"
                f"Avg: {it['avg_ms']:.2f} ms"
            )
        fig = go.Figure(go.Treemap(
            labels=labels,
            parents=parents,
            values=values,
            marker_colors=colors,
            hovertext=hover_texts,
            hoverinfo="text",
            root_color="#eeeeee",
            branchvalues="total",
        ))
        fig.update_layout(
            title="Flame Graph - Service & Operation Latency Overview",
            height=700,
            margin=dict(t=50, l=0, r=0, b=0),
        )
        return fig

    def generate_timeline(self, spans: List[dict]) -> go.Figure:
        if not spans:
            return go.Figure()
        all_services = {s.get("service_name", "unknown") for s in spans}
        self._init_service_colors(list(all_services))
        service_list = sorted(all_services)
        service_to_y = {svc: i for i, svc in enumerate(service_list)}
        sorted_spans = sorted(spans, key=lambda s: s.get("timestamp_ms", 0))
        min_time = sorted_spans[0].get("timestamp_ms", 0) if sorted_spans else 0
        fig = go.Figure()
        for span in sorted_spans:
            svc = span.get("service_name", "unknown")
            op = span.get("operation_name", "unknown")
            y = service_to_y[svc]
            start = span.get("timestamp_ms", 0) - min_time
            dur = span.get("duration_ms", 0)
            color = self.config["colors"]["latency_red"] if span.get("error", False) else self._service_color_map.get(svc, "#888888")
            status = span.get("status_code", "-")
            fig.add_trace(go.Scatter(
                x=[start, start + dur, start + dur, start, start],
                y=[y - 0.35, y - 0.35, y + 0.35, y + 0.35, y - 0.35],
                mode="lines",
                fill="toself",
                fillcolor=color,
                line=dict(color=color, width=1),
                opacity=0.7,
                hoveron="fills",
                hoverinfo="text",
                text=(
                    f"<b>{svc}</b>: {op}<br>"
                    f"Duration: {dur:.2f} ms<br>"
                    f"Start: +{start:.2f} ms<br>"
                    f"Status: {status}"
                ),
                showlegend=False,
            ))
        for svc in service_list:
            fig.add_trace(go.Scatter(
                x=[None],
                y=[None],
                mode="markers",
                marker=dict(size=12, color=self._service_color_map.get(svc, "#888888")),
                name=svc,
            ))
        fig.update_layout(
            title="Flame Timeline - All Spans by Service",
            xaxis_title="Time (ms from first span)",
            yaxis=dict(
                tickmode="array",
                tickvals=list(range(len(service_list))),
                ticktext=service_list,
            ),
            height=max(400, len(service_list) * 60),
            showlegend=True,
            legend_title="Services",
        )
        return fig
