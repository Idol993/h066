from collections import defaultdict
from typing import Dict, List, Optional, Tuple
import html
import plotly.graph_objects as go
import plotly.colors as pc
import networkx as nx

from ..utils.config_loader import ConfigLoader


def _e(s: str) -> str:
    if s is None:
        return ""
    return html.escape(str(s))


class TopologyGraph:
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or ConfigLoader.DEFAULT_CONFIG
        self._service_color_map: Dict[str, str] = {}
        self.edges: Dict[Tuple[str, str], Dict] = {}
        self.nodes: Dict[str, Dict] = {}
        self.edge_traces: Dict[Tuple[str, str], List[str]] = defaultdict(list)
        self.edge_slow_ops: Dict[Tuple[str, str], List[Dict]] = defaultdict(list)
        self.node_traces: Dict[str, List[str]] = defaultdict(list)
        self.node_slow_ops: Dict[str, List[Dict]] = defaultdict(list)

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

    def build(self, spans: List[dict], trace_builder=None) -> Dict:
        span_map = {s.get("span_id"): s for s in spans}
        all_services = {s.get("service_name", "unknown") for s in spans}
        self._init_service_colors(list(all_services))
        for span in spans:
            sid = span.get("span_id")
            pid = span.get("parent_span_id")
            svc = span.get("service_name", "unknown")
            parent_span = span_map.get(pid) if pid else None
            parent_svc = parent_span.get("service_name", "unknown") if parent_span else None
            dur = span.get("duration_ms", 0)
            is_error = span.get("error", False)
            trace_id = span.get("trace_id", "")
            if svc not in self.nodes:
                self.nodes[svc] = {
                    "service": svc,
                    "total_spans": 0,
                    "total_duration_ms": 0.0,
                    "error_count": 0,
                }
            self.nodes[svc]["total_spans"] += 1
            self.nodes[svc]["total_duration_ms"] += dur
            if is_error:
                self.nodes[svc]["error_count"] += 1
            self.node_traces[svc].append(trace_id)
            if dur > 500:
                self.node_slow_ops[svc].append({
                    "trace_id": trace_id,
                    "operation_name": span.get("operation_name", "unknown"),
                    "duration_ms": dur,
                    "error": is_error,
                })
            if parent_svc and parent_svc != svc:
                edge_key = (parent_svc, svc)
                if edge_key not in self.edges:
                    self.edges[edge_key] = {
                        "source": parent_svc,
                        "target": svc,
                        "call_count": 0,
                        "total_duration_ms": 0.0,
                        "error_count": 0,
                    }
                self.edges[edge_key]["call_count"] += 1
                self.edges[edge_key]["total_duration_ms"] += dur
                if is_error:
                    self.edges[edge_key]["error_count"] += 1
                self.edge_traces[edge_key].append(trace_id)
                if dur > 500:
                    self.edge_slow_ops[edge_key].append({
                        "trace_id": trace_id,
                        "operation_name": span.get("operation_name", "unknown"),
                        "duration_ms": dur,
                        "error": is_error,
                    })
        for node in self.nodes.values():
            tc = node["total_spans"]
            node["avg_duration_ms"] = node["total_duration_ms"] / tc if tc > 0 else 0
            node["error_rate"] = node["error_count"] / tc if tc > 0 else 0
        for edge in self.edges.values():
            cc = edge["call_count"]
            edge["avg_duration_ms"] = edge["total_duration_ms"] / cc if cc > 0 else 0
        return {
            "nodes": list(self.nodes.values()),
            "edges": list(self.edges.values()),
        }

    def generate_figure(self) -> Tuple[go.Figure, Dict]:
        G = nx.DiGraph()
        for svc, node in self.nodes.items():
            G.add_node(svc, **node)
        for (src, tgt), edge in self.edges.items():
            G.add_edge(src, tgt, **edge)
        if len(G.nodes) == 0:
            return go.Figure(), {"node_data": {}, "edge_data": {}}
        try:
            pos = nx.spring_layout(G, k=2.0, iterations=100, seed=42)
        except Exception:
            pos = nx.circular_layout(G)
        node_x = []
        node_y = []
        node_colors = []
        node_sizes = []
        node_hover_texts = []
        node_labels = []
        node_customdata = []
        for node in G.nodes(data=True):
            svc = node[0]
            data = node[1]
            x, y = pos[svc]
            node_x.append(x)
            node_y.append(y)
            tc = data.get("total_spans", 0)
            er = data.get("error_rate", 0)
            node_sizes.append(max(20, min(60, 15 + tc * 2)))
            if er >= 0.05:
                node_colors.append("#ff0000")
            elif er >= 0.01:
                node_colors.append("#ffa500")
            else:
                node_colors.append(self._service_color_map.get(svc, "#888888"))
            node_labels.append(svc)
            node_customdata.append([svc])
            avg = data.get("avg_duration_ms", 0)
            total_dur = data.get("total_duration_ms", 0)
            ec = data.get("error_count", 0)
            node_hover_texts.append(
                f"<b>{_e(svc)}</b><br>"
                f"Spans: {tc}<br>"
                f"Total: {total_dur:.2f} ms<br>"
                f"Avg: {avg:.2f} ms<br>"
                f"Errors: {ec} ({er*100:.1f}%)"
            )
        edge_x = []
        edge_y = []
        edge_hover_x = []
        edge_hover_y = []
        edge_hover_texts = []
        edge_hover_customdata = []
        edge_widths = []
        edge_colors = []
        for edge in G.edges(data=True):
            src, tgt, data = edge
            x0, y0 = pos[src]
            x1, y1 = pos[tgt]
            edge_x.append(x0)
            edge_x.append(x1)
            edge_x.append(None)
            edge_y.append(y0)
            edge_y.append(y1)
            edge_y.append(None)
            mx = (x0 + x1) / 2
            my = (y0 + y1) / 2
            edge_hover_x.append(mx)
            edge_hover_y.append(my)
            cc = data.get("call_count", 0)
            avg = data.get("avg_duration_ms", 0)
            total_dur = data.get("total_duration_ms", 0)
            ec = data.get("error_count", 0)
            er = ec / cc if cc > 0 else 0
            edge_widths.append(max(1, min(10, cc * 0.5)))
            if er >= 0.05:
                edge_colors.append("#ff0000")
            elif er >= 0.01:
                edge_colors.append("#ffa500")
            else:
                edge_colors.append("#666666")
            edge_hover_customdata.append([src, tgt])
            edge_hover_texts.append(
                f"<b>{_e(src)} \u2192 {_e(tgt)}</b><br>"
                f"Calls: {cc}<br>"
                f"Total: {total_dur:.2f} ms<br>"
                f"Avg: {avg:.2f} ms<br>"
                f"Errors: {ec} ({er*100:.1f}%)"
            )
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=edge_x, y=edge_y,
            mode="lines",
            line=dict(width=1, color="#cccccc"),
            hoverinfo="none",
            showlegend=False,
        ))
        fig.add_trace(go.Scatter(
            x=edge_hover_x, y=edge_hover_y,
            mode="markers",
            marker=dict(
                size=edge_widths,
                color=edge_colors,
                line=dict(width=1, color="#ffffff"),
                symbol="circle",
            ),
            customdata=edge_hover_customdata,
            hovertext=edge_hover_texts,
            hoverinfo="text",
            name="Calls",
            showlegend=False,
        ))
        fig.add_trace(go.Scatter(
            x=node_x, y=node_y,
            mode="markers+text",
            text=node_labels,
            textposition="top center",
            customdata=node_customdata,
            marker=dict(
                size=node_sizes,
                color=node_colors,
                line=dict(width=2, color="#ffffff"),
            ),
            hovertext=node_hover_texts,
            hoverinfo="text",
            name="Services",
            showlegend=False,
        ))
        for svc in sorted(self._service_color_map.keys()):
            if svc in self.nodes:
                fig.add_trace(go.Scatter(
                    x=[None], y=[None],
                    mode="markers",
                    marker=dict(
                        size=12,
                        color=self._service_color_map[svc],
                        line=dict(width=2, color="#ffffff"),
                    ),
                    name=svc,
                ))
        fig.update_layout(
            title="Service Dependency Topology",
            showlegend=True,
            legend_title="Services",
            height=700,
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            margin=dict(l=0, r=0, t=50, b=0),
            plot_bgcolor="#f9f9f9",
        )
        node_data = {}
        for svc, data in self.nodes.items():
            unique_traces = sorted(set(self.node_traces[svc]))
            slow_ops = sorted(self.node_slow_ops[svc], key=lambda x: x["duration_ms"], reverse=True)[:20]
            node_data[svc] = {
                "service": svc,
                "traces": unique_traces[:50],
                "trace_count": len(unique_traces),
                "slow_operations": slow_ops,
            }
        edge_data = {}
        for (src, tgt), data in self.edges.items():
            key = f"{src} → {tgt}"
            unique_traces = sorted(set(self.edge_traces[(src, tgt)]))
            slow_ops = sorted(self.edge_slow_ops[(src, tgt)], key=lambda x: x["duration_ms"], reverse=True)[:20]
            edge_data[key] = {
                "source": src,
                "target": tgt,
                "traces": unique_traces[:50],
                "trace_count": len(unique_traces),
                "slow_operations": slow_ops,
            }
        return fig, {"node_data": node_data, "edge_data": edge_data}
