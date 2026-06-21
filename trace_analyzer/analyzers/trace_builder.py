from collections import defaultdict
from typing import Dict, List, Optional
import networkx as nx


class TraceBuilder:
    def __init__(self):
        self.traces: Dict[str, List[dict]] = defaultdict(list)
        self.trace_trees: Dict[str, dict] = {}
        self.graphs: Dict[str, nx.DiGraph] = {}

    def build(self, spans: List[dict]) -> Dict[str, List[dict]]:
        for span in spans:
            trace_id = span.get("trace_id", "")
            if trace_id:
                self.traces[trace_id].append(span)
        for trace_id, trace_spans in self.traces.items():
            self._build_tree(trace_id, trace_spans)
            self._build_graph(trace_id, trace_spans)
        return self.traces

    def _build_tree(self, trace_id: str, spans: List[dict]) -> None:
        span_map: Dict[str, dict] = {}
        children_map: Dict[str, List[str]] = defaultdict(list)
        root_ids: List[str] = []
        for span in spans:
            sid = span.get("span_id", "")
            span_map[sid] = span
            pid = span.get("parent_span_id")
            if pid and pid in [s.get("span_id") for s in spans]:
                children_map[pid].append(sid)
            else:
                root_ids.append(sid)
        def build_node(span_id: str, depth: int = 0) -> dict:
            span = span_map[span_id]
            node = {
                "span": span,
                "span_id": span_id,
                "depth": depth,
                "children": [],
                "absolute_start_ms": span.get("timestamp_ms", 0),
                "absolute_end_ms": span.get("timestamp_ms", 0) + span.get("duration_ms", 0),
            }
            for child_id in sorted(
                children_map.get(span_id, []),
                key=lambda cid: span_map.get(cid, {}).get("timestamp_ms", 0),
            ):
                child_node = build_node(child_id, depth + 1)
                node["children"].append(child_node)
            return node
        roots = [build_node(rid) for rid in sorted(root_ids, key=lambda rid: span_map.get(rid, {}).get("timestamp_ms", 0))]
        if len(roots) == 1:
            self.trace_trees[trace_id] = roots[0]
        else:
            self.trace_trees[trace_id] = {
                "span": None,
                "span_id": "__root__",
                "depth": -1,
                "children": roots,
                "absolute_start_ms": min((r["absolute_start_ms"] for r in roots), default=0),
                "absolute_end_ms": max((r["absolute_end_ms"] for r in roots), default=0),
            }

    def _build_graph(self, trace_id: str, spans: List[dict]) -> None:
        G = nx.DiGraph()
        span_map = {s.get("span_id"): s for s in spans}
        for span in spans:
            sid = span.get("span_id")
            G.add_node(
                sid,
                service=span.get("service_name", "unknown"),
                operation=span.get("operation_name", "unknown"),
                duration=span.get("duration_ms", 0),
                start=span.get("timestamp_ms", 0),
            )
        for span in spans:
            pid = span.get("parent_span_id")
            sid = span.get("span_id")
            if pid and pid in span_map:
                G.add_edge(pid, sid)
        self.graphs[trace_id] = G

    def get_trace_tree(self, trace_id: str) -> Optional[dict]:
        return self.trace_trees.get(trace_id)

    def get_trace_graph(self, trace_id: str) -> Optional[nx.DiGraph]:
        return self.graphs.get(trace_id)

    def get_all_trace_ids(self) -> List[str]:
        return list(self.traces.keys())

    def get_trace_spans_flat(self, trace_id: str) -> List[dict]:
        return self.traces.get(trace_id, [])
