from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import networkx as nx


class CriticalPathFinder:
    def __init__(self):
        self.critical_paths: Dict[str, List[dict]] = {}
        self.critical_path_durations: Dict[str, float] = {}

    def find_all(self, trace_builder) -> Dict[str, List[dict]]:
        for trace_id in trace_builder.get_all_trace_ids():
            self._find_for_trace(trace_id, trace_builder)
        return self.critical_paths

    def _find_for_trace(self, trace_id: str, trace_builder) -> List[dict]:
        tree = trace_builder.get_trace_tree(trace_id)
        if not tree:
            return []
        spans_flat = trace_builder.get_trace_spans_flat(trace_id)
        span_map = {s.get("span_id"): s for s in spans_flat}
        graph = trace_builder.get_trace_graph(trace_id)
        if graph is None:
            return []
        critical_path_ids = self._longest_path(graph)
        if not critical_path_ids:
            critical_path_ids = self._fallback_path(tree)
        critical_path_spans = [span_map[sid] for sid in critical_path_ids if sid in span_map]
        self.critical_paths[trace_id] = critical_path_spans
        self.critical_path_durations[trace_id] = sum(s.get("duration_ms", 0) for s in critical_path_spans)
        return critical_path_spans

    def _longest_path(self, G: nx.DiGraph) -> List[str]:
        try:
            if not nx.is_directed_acyclic_graph(G):
                return []
            topo_order = list(nx.topological_sort(G))
            if not topo_order:
                return []
            dist: Dict[str, float] = {n: 0.0 for n in G.nodes}
            parent: Dict[str, Optional[str]] = {n: None for n in G.nodes}
            for u in topo_order:
                u_dur = G.nodes[u].get("duration", 0)
                for v in G.successors(u):
                    if dist[v] < dist[u] + u_dur:
                        dist[v] = dist[u] + u_dur
                        parent[v] = u
            end_node = max(dist, key=dist.get)
            path = []
            current = end_node
            while current is not None:
                path.append(current)
                current = parent[current]
            path.reverse()
            return path
        except Exception:
            return []

    def _fallback_path(self, tree: dict) -> List[str]:
        path: List[str] = []
        node = tree
        while node and node.get("span"):
            path.append(node["span_id"])
            if node["children"]:
                node = max(
                    node["children"],
                    key=lambda c: c["span"].get("duration_ms", 0) if c.get("span") else 0,
                )
            else:
                break
        return path

    def get_critical_path(self, trace_id: str) -> List[dict]:
        return self.critical_paths.get(trace_id, [])

    def get_slowest_traces(self, n: int = 10) -> List[Tuple[str, List[dict], float]]:
        sorted_items = sorted(
            self.critical_path_durations.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:n]
        return [
            (tid, self.critical_paths.get(tid, []), dur)
            for tid, dur in sorted_items
        ]

    def get_bottleneck_services(self, n: int = 10) -> List[Dict]:
        service_total: Dict[str, float] = defaultdict(float)
        service_count: Dict[str, int] = defaultdict(int)
        for path in self.critical_paths.values():
            for span in path:
                service = span.get("service_name", "unknown")
                service_total[service] += span.get("duration_ms", 0)
                service_count[service] += 1
        result = [
            {
                "service_name": service,
                "critical_count": count,
                "total_critical_duration_ms": service_total[service],
            }
            for service, count in service_count.items()
        ]
        result.sort(key=lambda x: x["total_critical_duration_ms"], reverse=True)
        return result[:n]
