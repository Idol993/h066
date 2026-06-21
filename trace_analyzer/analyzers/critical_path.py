from typing import Dict, List, Optional, Tuple
from collections import defaultdict


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
        path_ids, total_dur = self._longest_path_tree(tree)
        if not path_ids:
            path_ids, total_dur = self._fallback_path(tree)
        critical_path_spans = []
        for sid in path_ids:
            if sid in span_map:
                span = dict(span_map[sid])
                span["pct_of_critical_path"] = (
                    round(span.get("duration_ms", 0) / total_dur * 100, 1)
                    if total_dur > 0 else 0.0
                )
                critical_path_spans.append(span)
        self.critical_paths[trace_id] = critical_path_spans
        self.critical_path_durations[trace_id] = total_dur
        return critical_path_spans

    def _longest_path_tree(self, tree: dict) -> Tuple[List[str], float]:
        if not tree:
            return [], 0.0
        roots = tree.get("children", [])
        if not roots and tree.get("span"):
            roots = [tree]
        if not roots:
            return [], 0.0
        best_path: List[str] = []
        best_dur: float = 0.0
        for root in roots:
            path, dur = self._dfs_longest(root)
            if dur > best_dur:
                best_dur = dur
                best_path = path
        return best_path, best_dur

    def _dfs_longest(self, node: dict) -> Tuple[List[str], float]:
        span = node.get("span")
        node_id = node.get("span_id", "")
        own_dur = span.get("duration_ms", 0) if span else 0
        children = node.get("children", [])
        if not children:
            return [node_id], own_dur
        best_child_path: List[str] = []
        best_child_cum: float = 0.0
        for child in children:
            c_path, c_cum = self._dfs_longest(child)
            if c_cum > best_child_cum:
                best_child_cum = c_cum
                best_child_path = c_path
        return [node_id] + best_child_path, own_dur + best_child_cum

    def _fallback_path(self, tree: dict) -> Tuple[List[str], float]:
        path: List[str] = []
        dur: float = 0.0
        node = tree
        while node and node.get("span"):
            sid = node.get("span_id", "")
            path.append(sid)
            dur += node["span"].get("duration_ms", 0)
            if node["children"]:
                node = max(
                    node["children"],
                    key=lambda c: c["span"].get("duration_ms", 0) if c.get("span") else 0,
                )
            else:
                break
        return path, dur

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
