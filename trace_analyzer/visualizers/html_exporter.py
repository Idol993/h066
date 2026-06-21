import json
import os
import html
import re
from typing import Dict, List, Optional
import plotly.graph_objects as go
import plotly.io as pio

from ..utils.time_utils import TimeUtils


def _e(s: str) -> str:
    if s is None:
        return ""
    return html.escape(str(s))


def _safe_id(s: str) -> str:
    if s is None:
        return ""
    return re.sub(r'[^a-zA-Z0-9_-]', '_', str(s))


def _pct_color(pct: float) -> str:
    if pct >= 0.05:
        return "error-high"
    if pct >= 0.01:
        return "error-medium"
    return "error-low"


class HTMLExporter:
    TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")

    def __init__(self):
        self._load_templates()

    def _load_templates(self):
        waterfall_path = os.path.join(self.TEMPLATE_DIR, "waterfall.html")
        flamegraph_path = os.path.join(self.TEMPLATE_DIR, "flamegraph.html")
        self.waterfall_template = ""
        self.flamegraph_template = ""
        if os.path.exists(waterfall_path):
            with open(waterfall_path, "r", encoding="utf-8") as f:
                self.waterfall_template = f.read()
        if os.path.exists(flamegraph_path):
            with open(flamegraph_path, "r", encoding="utf-8") as f:
                self.flamegraph_template = f.read()

    def export_multi_trace(
        self,
        output_path: str,
        trace_data: Dict[str, Dict],
        summary_overview_fig: Optional[go.Figure] = None,
        topology_fig: Optional[go.Figure] = None,
        topology_data: Optional[Dict] = None,
        summary: Optional[Dict] = None,
    ) -> str:
        timestamp = TimeUtils.now_timestamp()
        if not output_path.endswith(".html"):
            output_path = f"{output_path}_{timestamp}.html"
        sorted_trace_ids = sorted(
            trace_data.keys(),
            key=lambda tid: trace_data[tid].get("critical_duration_ms", 0),
            reverse=True,
        )
        overview_html = ""
        if summary_overview_fig is not None:
            overview_html = pio.to_html(
                summary_overview_fig,
                full_html=False,
                include_plotlyjs="cdn",
                div_id="overview-chart",
            )
        topology_html = ""
        if topology_fig is not None:
            topology_html = pio.to_html(
                topology_fig,
                full_html=False,
                include_plotlyjs=False,
                div_id="topology-chart",
            )
        trace_json_data = {}
        for tid in sorted_trace_ids:
            td = trace_data[tid]
            trace_json_data[tid] = {
                "critical_duration_ms": td.get("critical_duration_ms", 0),
                "total_duration_ms": td.get("total_duration_ms", 0),
                "critical_path": td.get("critical_path", []),
                "span_count": td.get("span_count", 0),
                "error_count": td.get("error_count", 0),
                "service_breakdown": td.get("service_breakdown", {}),
            }
        per_trace_html_parts = []
        for tid in sorted_trace_ids:
            td = trace_data[tid]
            waterfall_fig = td.get("waterfall_fig")
            flame_fig = td.get("flame_fig")
            cp = td.get("critical_path", [])
            cp_dur = td.get("critical_duration_ms", 0)
            safe_tid = _safe_id(tid)
            wf_html = ""
            if waterfall_fig is not None:
                wf_html = pio.to_html(
                    waterfall_fig,
                    full_html=False,
                    include_plotlyjs=False,
                    div_id=f"wf-{safe_tid}",
                )
            fl_html = ""
            if flame_fig is not None:
                fl_html = pio.to_html(
                    flame_fig,
                    full_html=False,
                    include_plotlyjs=False,
                    div_id=f"fl-{safe_tid}",
                )
            cp_rows = ""
            cumulative = 0.0
            for i, span in enumerate(cp, 1):
                dur = span.get("duration_ms", 0)
                cumulative += dur
                pct = span.get("pct_of_critical_path", round(dur / cp_dur * 100, 1) if cp_dur > 0 else 0)
                cum_pct = round(cumulative / cp_dur * 100, 1) if cp_dur > 0 else 0
                cp_rows += f"""<tr>
                    <td>{i}</td>
                    <td>{_e(span.get('service_name', '-'))}</td>
                    <td>{_e(span.get('operation_name', '-'))}</td>
                    <td>{dur:.2f} ms</td>
                    <td>{pct:.1f}%</td>
                    <td>{cum_pct:.1f}%</td>
                </tr>"""
            cp_table = ""
            if cp_rows:
                cp_table = f"""<table>
                    <tr><th>#</th><th>Service</th><th>Operation</th><th>Duration</th><th>% of Critical</th><th>Cumulative</th></tr>
                    {cp_rows}
                </table>"""
            per_trace_html_parts.append(f"""
            <div class="trace-panel" id="panel-{safe_tid}" style="display:none;">
                <div class="chart-section">
                    <h3>Waterfall Chart</h3>
                    <div class="chart-container">{wf_html}</div>
                </div>
                <div class="chart-section">
                    <h3>Flame Graph (Depth View)</h3>
                    <div class="chart-container">{fl_html}</div>
                </div>
                <div class="chart-section">
                    <h3>Critical Path (Total: {cp_dur:.2f} ms)</h3>
                    <div class="summary-card">{cp_table}</div>
                </div>
            </div>""")
        per_trace_html = "\n".join(per_trace_html_parts)
        trace_selector_options = ""
        for i, tid in enumerate(sorted_trace_ids):
            td = trace_data[tid]
            total_dur = td.get("total_duration_ms", 0)
            cp_dur = td.get("critical_duration_ms", 0)
            sc = td.get("span_count", 0)
            display_tid = tid if len(tid) <= 16 else tid[:16] + "..."
            safe_tid = _safe_id(tid)
            label = f"{_e(display_tid)} ({total_dur:.0f}ms total, {cp_dur:.0f}ms CP, {sc} spans)"
            selected = " selected" if i == 0 else ""
            trace_selector_options += f'<option value="{safe_tid}"{selected}>{label}</option>\n'
        topology_node_data = topology_data.get("node_data", {}) if topology_data else {}
        topology_edge_data = topology_data.get("edge_data", {}) if topology_data else {}
        summary_html = self._render_summary(summary or {})
        trace_json_data_safe = {_safe_id(k): v for k, v in trace_json_data.items()}
        sorted_safe_ids = [_safe_id(tid) for tid in sorted_trace_ids]
        safe_to_orig = {_safe_id(tid): tid for tid in sorted_trace_ids}

        def _safe_json(obj) -> str:
            return json.dumps(obj, default=str, ensure_ascii=False).replace('</script>', '<\\/script>')

        trace_json_str = _safe_json(trace_json_data_safe)
        safe_to_orig_str = _safe_json(safe_to_orig)
        compare_select_a = trace_selector_options
        compare_select_b = ""
        for i, tid in enumerate(sorted_trace_ids):
            td = trace_data[tid]
            total_dur = td.get("total_duration_ms", 0)
            cp_dur = td.get("critical_duration_ms", 0)
            sc = td.get("span_count", 0)
            display_tid = tid if len(tid) <= 16 else tid[:16] + "..."
            safe_tid = _safe_id(tid)
            label = f"{_e(display_tid)} ({total_dur:.0f}ms total, {cp_dur:.0f}ms CP, {sc} spans)"
            selected = " selected" if i == 1 else ""
            compare_select_b += f'<option value="{safe_tid}"{selected}>{label}</option>\n'
        css = self._render_css()
        js = self._render_js(
            trace_json_str=trace_json_str,
            sorted_trace_ids_json=_safe_json(sorted_safe_ids),
            safe_to_orig_str=safe_to_orig_str,
            topology_node_json=_safe_json(topology_data.get("node_data", {}) if topology_data else {}),
            topology_edge_json=_safe_json(topology_data.get("edge_data", {}) if topology_data else {}),
        )
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Trace Analysis Report</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
{css}
</head>
<body>
<div class="container">
    <h1>🔍 Distributed Trace Analysis Report</h1>
    {summary_html}

    <div class="tabs">
        <button class="tab active" onclick="switchMainTab(event, 'per-trace')">Per-Trace Analysis</button>
        <button class="tab" onclick="switchMainTab(event, 'compare')">Trace Comparison</button>
        <button class="tab" onclick="switchMainTab(event, 'topology')">Service Topology</button>
        <button class="tab" onclick="switchMainTab(event, 'overview')">Service Overview</button>
    </div>

    <div id="per-trace" class="tab-content active">
        <div class="trace-selector-bar">
            <label for="trace-select">Trace:</label>
            <select id="trace-select" onchange="switchTrace(this.value)">
                {trace_selector_options}
            </select>
            <span id="trace-meta" class="trace-meta"></span>
        </div>
        <div id="trace-panels">
            {per_trace_html}
        </div>
    </div>

    <div id="compare" class="tab-content">
        <div class="compare-selector-bar">
            <div class="compare-select-group">
                <label for="compare-a">Trace A (Baseline):</label>
                <select id="compare-a" onchange="updateComparison()">
                    {compare_select_a}
                </select>
            </div>
            <div class="compare-select-group">
                <label for="compare-b">Trace B (Compare):</label>
                <select id="compare-b" onchange="updateComparison()">
                    {compare_select_b}
                </select>
            </div>
        </div>
        <div id="compare-results"></div>
    </div>

    <div id="topology" class="tab-content">
        <div class="chart-section">
            <h3>Service Dependency Topology</h3>
            <div class="chart-container">{topology_html}</div>
        </div>
        <div class="summary-card">
            <h3>Topology Details</h3>
            <p class="hint">Click on a service node or call edge in the graph to see related traces and slow operations.</p>
            <div id="topology-details">
                <div class="hint-text">Select a service or edge from the topology graph above.</div>
            </div>
        </div>
        <div class="topology-legend">
            <span class="legend-item"><span class="legend-dot" style="background:#00aa00;"></span> Error rate &lt; 1%</span>
            <span class="legend-item"><span class="legend-dot" style="background:#ffa500;"></span> Error rate 1-5%</span>
            <span class="legend-item"><span class="legend-dot" style="background:#ff0000;"></span> Error rate ≥ 5%</span>
            <span class="legend-item"><span class="legend-line" style="background:#666666;"></span> Edge width = call count</span>
        </div>
    </div>

    <div id="overview" class="tab-content">
        <div class="chart-section">
            <h3>Service Overview - Latency by Service & Operation</h3>
            <div class="chart-container">{overview_html}</div>
        </div>
    </div>
</div>
{js}
</body>
</html>"""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        return output_path

    def _render_css(self) -> str:
        return """<style>
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    margin: 0; padding: 20px; background: #f5f5f5;
}
.container { max-width: 1600px; margin: 0 auto; }
h1 { color: #333; border-bottom: 2px solid #0077cc; padding-bottom: 10px; }
h2 { color: #444; margin-top: 30px; }
h3 { color: #555; margin-top: 20px; margin-bottom: 10px; }
.summary-card {
    background: white; border-radius: 8px; padding: 20px;
    margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}
.summary-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;
}
.summary-item {
    background: #f8f9fa; padding: 15px; border-radius: 6px; border-left: 4px solid #0077cc;
}
.summary-label { font-size: 12px; color: #666; text-transform: uppercase; margin-bottom: 5px; }
.summary-value { font-size: 24px; font-weight: bold; color: #333; }
.chart-container {
    background: white; border-radius: 8px; padding: 15px; margin-bottom: 15px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1); overflow-x: auto;
}
.chart-section { margin-bottom: 25px; }
.error-high { color: #ff0000; font-weight: bold; }
.error-medium { color: #ffa500; font-weight: bold; }
.error-low { color: #00aa00; }
.trace-selector-bar, .compare-selector-bar {
    background: white; border-radius: 8px; padding: 15px 20px;
    margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    display: flex; align-items: center; gap: 15px; flex-wrap: wrap;
}
.compare-selector-bar { justify-content: flex-start; gap: 30px; }
.compare-select-group { display: flex; flex-direction: column; gap: 5px; flex: 1; min-width: 250px; }
.compare-select-group label { font-weight: 600; color: #333; font-size: 13px; }
.trace-selector-bar label { font-weight: 600; color: #333; white-space: nowrap; }
.trace-selector-bar select, .compare-select-group select {
    flex: 1; min-width: 300px; padding: 8px 12px; border-radius: 6px;
    border: 1px solid #ccc; font-size: 14px;
}
.trace-selector-bar .trace-meta { font-size: 13px; color: #666; }
.tabs {
    display: flex; gap: 0; margin-bottom: 0; border-bottom: 2px solid #ddd; flex-wrap: wrap;
}
.tab {
    padding: 10px 20px; cursor: pointer; background: #e9ecef; border: none;
    border-bottom: 2px solid transparent; margin-bottom: -2px; font-size: 14px;
}
.tab.active { background: white; border-bottom: 2px solid #0077cc; font-weight: bold; }
.tab-content { display: none; }
.tab-content.active { display: block; }
table { width: 100%; border-collapse: collapse; margin-top: 10px; }
th, td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }
th { background: #f0f0f0; font-weight: 600; }
tr:hover { background: #f8f9fa; }
.compare-grid {
    display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 20px;
}
.compare-col { background: white; border-radius: 8px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.compare-col h3 { margin-top: 0; }
.compare-col.a { border-top: 4px solid #0077cc; }
.compare-col.b { border-top: 4px solid #ff7700; }
.compare-metrics { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 20px; }
.metric-box { background: #f8f9fa; padding: 12px; border-radius: 6px; }
.metric-box .label { font-size: 11px; color: #666; text-transform: uppercase; }
.metric-box .value { font-size: 20px; font-weight: bold; color: #333; }
.metric-box .delta { font-size: 12px; margin-left: 8px; }
.delta-up { color: #ff0000; }
.delta-down { color: #00aa00; }
.diff-highlight { background: #fff3cd; }
.diff-add { background: #d4edda; }
.diff-remove { background: #f8d7da; }
.topology-legend {
    background: white; border-radius: 8px; padding: 15px 20px;
    margin-top: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    display: flex; gap: 20px; flex-wrap: wrap; font-size: 13px;
}
.legend-item { display: flex; align-items: center; gap: 6px; }
.legend-dot { display: inline-block; width: 12px; height: 12px; border-radius: 50%; }
.legend-line { display: inline-block; width: 20px; height: 3px; }
.hint { color: #666; font-size: 13px; margin-bottom: 10px; }
.hint-text { color: #999; font-style: italic; text-align: center; padding: 30px; }
.trace-link {
    color: #0077cc; cursor: pointer; text-decoration: underline;
}
.trace-link:hover { color: #005599; }
</style>"""

    def _render_js(
        self,
        trace_json_str: str,
        sorted_trace_ids_json: str,
        safe_to_orig_str: str,
        topology_node_json: str,
        topology_edge_json: str,
    ) -> str:
        return r"""<script>
var traceData = """ + trace_json_str + r""";
var sortedTraceIds = """ + sorted_trace_ids_json + r""";
var safeToOrig = """ + safe_to_orig_str + r""";
var origToSafe = {};
for (var origId in safeToOrig) {
    var safeId = origId;
    var realOrig = safeToOrig[origId];
    origToSafe[realOrig] = safeId;
}
var topologyNodeData = """ + topology_node_json + r""";
var topologyEdgeData = """ + topology_edge_json + r""";

function switchMainTab(evt, tabName) {
    var tabcontent = document.getElementsByClassName("tab-content");
    for (var i = 0; i < tabcontent.length; i++) {
        tabcontent[i].className = tabcontent[i].className.replace(" active", "");
    }
    var tablinks = document.getElementsByClassName("tab");
    for (var i = 0; i < tablinks.length; i++) {
        tablinks[i].className = tablinks[i].className.replace(" active", "");
    }
    document.getElementById(tabName).className += " active";
    evt.currentTarget.className += " active";
    if (tabName === 'topology') {
        setupTopologyClick();
    } else if (tabName === 'compare') {
        updateComparison();
    }
}

function switchTrace(safeId) {
    var panels = document.querySelectorAll('.trace-panel');
    panels.forEach(function(p) { p.style.display = 'none'; });
    var target = document.getElementById('panel-' + safeId);
    if (target) {
        target.style.display = 'block';
    }
    var meta = traceData[safeId];
    var metaEl = document.getElementById('trace-meta');
    if (meta && metaEl) {
        var origId = safeToOrig[safeId] || safeId;
        metaEl.textContent = 'Trace: ' + origId +
            ' | Total: ' + (meta.total_duration_ms || 0).toFixed(1) + ' ms' +
            ' | Critical path: ' + (meta.critical_duration_ms || 0).toFixed(1) +
            ' ms | Spans: ' + meta.span_count;
    }
}

function jumpToTrace(origTraceId) {
    var safeId = origToSafe[origTraceId];
    if (!safeId) {
        safeId = String(origTraceId).replace(/[^a-zA-Z0-9_-]/g, '_');
    }
    var perTraceTab = document.querySelectorAll('.tab')[0];
    if (perTraceTab) {
        perTraceTab.click();
    }
    var select = document.getElementById('trace-select');
    if (select) {
        select.value = safeId;
        switchTrace(safeId);
    }
}

document.addEventListener('click', function(e) {
    var target = e.target;
    if (target && target.classList && target.classList.contains('trace-link')) {
        var tid = target.getAttribute('data-trace-id');
        if (tid !== null && tid !== undefined) {
            jumpToTrace(tid);
        }
    }
});

function updateComparison() {
    var safeA = document.getElementById('compare-a').value;
    var safeB = document.getElementById('compare-b').value;
    var a = traceData[safeA];
    var b = traceData[safeB];
    if (!a || !b) {
        document.getElementById('compare-results').innerHTML =
            '<div class="summary-card"><p class="hint-text">Please select two valid traces to compare.</p></div>';
        return;
    }
    var origA = safeToOrig[safeA] || safeA;
    var origB = safeToOrig[safeB] || safeB;

    var totalA = a.total_duration_ms || 0;
    var totalB = b.total_duration_ms || 0;
    var cpA = a.critical_duration_ms || 0;
    var cpB = b.critical_duration_ms || 0;

    var totalDelta = totalB - totalA;
    var totalDeltaPct = totalA > 0 ? (totalDelta / totalA) * 100 : 0;
    var totalDeltaClass = totalDelta > 0 ? 'delta-up' : (totalDelta < 0 ? 'delta-down' : '');
    var totalDeltaSign = totalDelta > 0 ? '+' : '';

    var cpDelta = cpB - cpA;
    var cpDeltaPct = cpA > 0 ? (cpDelta / cpA) * 100 : 0;
    var cpDeltaClass = cpDelta > 0 ? 'delta-up' : (cpDelta < 0 ? 'delta-down' : '');
    var cpDeltaSign = cpDelta > 0 ? '+' : '';

    var errA = a.error_count || 0;
    var errB = b.error_count || 0;
    var errDelta = errB - errA;
    var errDeltaClass = errDelta > 0 ? 'delta-up' : (errDelta < 0 ? 'delta-down' : '');
    var errDeltaSign = errDelta > 0 ? '+' : '';

    var sbA = a.service_breakdown || {};
    var sbB = b.service_breakdown || {};
    var allServices = new Set(Object.keys(sbA).concat(Object.keys(sbB)));
    var diffRows = '';
    allServices.forEach(function(svc) {
        var aDur = sbA[svc] || 0;
        var bDur = sbB[svc] || 0;
        var aPct = totalA > 0 ? (aDur / totalA) * 100 : 0;
        var bPct = totalB > 0 ? (bDur / totalB) * 100 : 0;
        var diff = bDur - aDur;
        var pctDiff = bPct - aPct;
        var rowClass = '';
        if (Math.abs(diff) > 50) {
            rowClass = diff > 0 ? 'diff-highlight' : 'diff-remove';
        }
        var diffSign = diff > 0 ? '+' : '';
        var pctDiffSign = pctDiff > 0 ? '+' : '';
        var pctDiffClass = pctDiff > 0 ? 'delta-up' : (pctDiff < 0 ? 'delta-down' : '');
        diffRows += '<tr class="' + rowClass + '">' +
            '<td>' + escapeHtml(svc) + '</td>' +
            '<td>' + aDur.toFixed(2) + ' ms<br><span style="color:#666;font-size:12px;">' + aPct.toFixed(1) + '%</span></td>' +
            '<td>' + bDur.toFixed(2) + ' ms<br><span style="color:#666;font-size:12px;">' + bPct.toFixed(1) + '%</span></td>' +
            '<td class="' + (diff > 0 ? 'delta-up' : (diff < 0 ? 'delta-down' : '')) + '">' +
            diffSign + diff.toFixed(2) + ' ms<br><span class="' + pctDiffClass + '" style="font-size:12px;">' +
            pctDiffSign + pctDiff.toFixed(1) + '%</span></td>' +
            '</tr>';
    });

    var cpPathA = a.critical_path || [];
    var cpPathB = b.critical_path || [];
    var cpARows = renderCriticalPathTable(cpPathA, cpA);
    var cpBRows = renderCriticalPathTable(cpPathB, cpB);
    var diffOps = findDiffOperations(cpPathA, cpPathB);
    var diffOpsHtml = '';
    if (diffOps.added.length > 0 || diffOps.removed.length > 0 || diffOps.slower.length > 0) {
        diffOpsHtml = '<div class="summary-card"><h3>Key Differences</h3>';
        if (diffOps.slower.length > 0) {
            diffOpsHtml += '<h4>Slower in B:</h4><ul>';
            diffOps.slower.forEach(function(op) {
                diffOpsHtml += '<li><b>' + escapeHtml(op.service) + '</b> / ' + escapeHtml(op.operation) +
                    ': ' + op.durA.toFixed(2) + ' \u2192 ' + op.durB.toFixed(2) + ' ms ' +
                    '<span class="delta-up">(+' + (op.durB - op.durA).toFixed(2) + ' ms)</span></li>';
            });
            diffOpsHtml += '</ul>';
        }
        if (diffOps.added.length > 0) {
            diffOpsHtml += '<h4>Only in B:</h4><ul>';
            diffOps.added.forEach(function(op) {
                diffOpsHtml += '<li class="diff-add"><b>' + escapeHtml(op.service) + '</b> / ' + escapeHtml(op.operation) +
                    ': ' + op.durB.toFixed(2) + ' ms</li>';
            });
            diffOpsHtml += '</ul>';
        }
        if (diffOps.removed.length > 0) {
            diffOpsHtml += '<h4>Only in A:</h4><ul>';
            diffOps.removed.forEach(function(op) {
                diffOpsHtml += '<li class="diff-remove"><b>' + escapeHtml(op.service) + '</b> / ' + escapeHtml(op.operation) +
                    ': ' + op.durA.toFixed(2) + ' ms</li>';
            });
            diffOpsHtml += '</ul>';
        }
        diffOpsHtml += '</div>';
    }
    var html = '<div class="compare-grid">' +
        '<div class="compare-col a">' +
        '<h3>Trace A: ' + escapeHtml(origA) + '</h3>' +
        '<div class="compare-metrics">' +
        '<div class="metric-box"><div class="label">Total Duration</div><div class="value">' + totalA.toFixed(2) + ' ms</div></div>' +
        '<div class="metric-box"><div class="label">Critical Path</div><div class="value">' + cpA.toFixed(2) + ' ms</div></div>' +
        '<div class="metric-box"><div class="label">Spans</div><div class="value">' + a.span_count + '</div></div>' +
        '<div class="metric-box"><div class="label">Errors</div><div class="value">' + errA + '</div></div>' +
        '<div class="metric-box"><div class="label">Services</div><div class="value">' + Object.keys(sbA).length + '</div></div>' +
        '</div>' +
        '<h4>Critical Path</h4>' +
        '<table><tr><th>#</th><th>Service</th><th>Operation</th><th>Duration</th><th>%</th></tr>' + cpARows + '</table>' +
        '</div>' +
        '<div class="compare-col b">' +
        '<h3>Trace B: ' + escapeHtml(origB) + '</h3>' +
        '<div class="compare-metrics">' +
        '<div class="metric-box"><div class="label">Total Duration</div><div class="value">' + totalB.toFixed(2) + ' ms <span class="' + totalDeltaClass + '">(' + totalDeltaSign + totalDelta.toFixed(2) + ' ms, ' + totalDeltaSign + totalDeltaPct.toFixed(1) + '%)</span></div></div>' +
        '<div class="metric-box"><div class="label">Critical Path</div><div class="value">' + cpB.toFixed(2) + ' ms <span class="' + cpDeltaClass + '">(' + cpDeltaSign + cpDelta.toFixed(2) + ' ms, ' + cpDeltaSign + cpDeltaPct.toFixed(1) + '%)</span></div></div>' +
        '<div class="metric-box"><div class="label">Spans</div><div class="value">' + b.span_count + '</div></div>' +
        '<div class="metric-box"><div class="label">Errors</div><div class="value">' + errB + ' <span class="' + errDeltaClass + '">(' + errDeltaSign + errDelta + ')</span></div></div>' +
        '<div class="metric-box"><div class="label">Services</div><div class="value">' + Object.keys(sbB).length + '</div></div>' +
        '</div>' +
        '<h4>Critical Path</h4>' +
        '<table><tr><th>#</th><th>Service</th><th>Operation</th><th>Duration</th><th>%</th></tr>' + cpBRows + '</table>' +
        '</div>' +
        '</div>' +
        diffOpsHtml +
        '<div class="summary-card">' +
        '<h3>Service Duration Breakdown</h3>' +
        '<table><tr><th>Service</th><th>Trace A</th><th>Trace B</th><th>Difference</th></tr>' + diffRows + '</table>' +
        '</div>';
    document.getElementById('compare-results').innerHTML = html;
}

function renderCriticalPathTable(cp, totalDur) {
    var rows = '';
    for (var i = 0; i < cp.length; i++) {
        var s = cp[i];
        var pct = s.pct_of_critical_path;
        if (pct === undefined || pct === null) {
            pct = totalDur > 0 ? (s.duration_ms / totalDur) * 100 : 0;
        }
        rows += '<tr>' +
            '<td>' + (i + 1) + '</td>' +
            '<td>' + escapeHtml(s.service_name || '-') + '</td>' +
            '<td>' + escapeHtml(s.operation_name || '-') + '</td>' +
            '<td>' + s.duration_ms.toFixed(2) + '</td>' +
            '<td>' + pct.toFixed(1) + '%</td>' +
            '</tr>';
    }
    return rows;
}

function findDiffOperations(cpA, cpB) {
    var result = { added: [], removed: [], slower: [] };
    var aKeys = {};
    cpA.forEach(function(s) {
        var key = (s.service_name || '') + '::' + (s.operation_name || '');
        aKeys[key] = s;
    });
    cpB.forEach(function(s) {
        var key = (s.service_name || '') + '::' + (s.operation_name || '');
        if (aKeys[key]) {
            var diff = s.duration_ms - aKeys[key].duration_ms;
            if (diff > 50) {
                result.slower.push({
                    service: s.service_name,
                    operation: s.operation_name,
                    durA: aKeys[key].duration_ms,
                    durB: s.duration_ms,
                });
            }
            delete aKeys[key];
        } else {
            result.added.push({
                service: s.service_name,
                operation: s.operation_name,
                durB: s.duration_ms,
            });
        }
    });
    for (var key in aKeys) {
        result.removed.push({
            service: aKeys[key].service_name,
            operation: aKeys[key].operation_name,
            durA: aKeys[key].duration_ms,
        });
    }
    return result;
}

function setupTopologyClick() {
    var chart = document.getElementById('topology-chart');
    if (!chart || chart._topologySetup) return;
    chart._topologySetup = true;
    chart.on('plotly_click', function(data) {
        if (!data.points || data.points.length === 0) return;
        var pt = data.points[0];
        var text = pt.text;
        if (!text) return;
        var detailsEl = document.getElementById('topology-details');
        if (!detailsEl) return;
        if (pt.curveNumber === 2) {
            var svc = text;
            showTopologyNodeDetails(svc, detailsEl);
        } else if (pt.curveNumber === 1) {
            var ht = pt.hovertext || '';
            var m = ht.match(/<b>([^<]+) \u2192 ([^<]+)<\/b>/);
            if (m) {
                showTopologyEdgeDetails(m[1], m[2], detailsEl);
            }
        }
    });
}

function renderTraceLinks(traceIds) {
    var links = '';
    (traceIds || []).slice(0, 10).forEach(function(tid) {
        links += '<span class="trace-link" data-trace-id="' + escapeAttr(tid) + '">' + escapeHtml(tid) + '</span>, ';
    });
    if (links) links = links.slice(0, -2);
    return links;
}

function showTopologyNodeDetails(serviceName, el) {
    var data = topologyNodeData[serviceName];
    if (!data) {
        el.innerHTML = '<p>No data for service: ' + escapeHtml(serviceName) + '</p>';
        return;
    }
    var traceLinks = renderTraceLinks(data.traces || []);
    var slowRows = '';
    (data.slow_operations || []).slice(0, 10).forEach(function(op, i) {
        var errClass = op.error ? 'error-high' : '';
        slowRows += '<tr>' +
            '<td>' + (i + 1) + '</td>' +
            '<td>' + escapeHtml(op.operation_name || '-') + '</td>' +
            '<td>' + op.duration_ms.toFixed(2) + ' ms</td>' +
            '<td class="' + errClass + '">' + (op.error ? 'Yes' : 'No') + '</td>' +
            '<td><span class="trace-link" data-trace-id="' + escapeAttr(op.trace_id) + '">' + escapeHtml(op.trace_id) + '</span></td>' +
            '</tr>';
    });
    var html = '<h4>Service: ' + escapeHtml(serviceName) + '</h4>' +
        '<p><b>Related traces (' + (data.trace_count || 0) + '):</b> ' + traceLinks + '</p>';
    if (slowRows) {
        html += '<h5>Slow Operations (Top 10, > 500ms):</h5>' +
            '<table><tr><th>#</th><th>Operation</th><th>Duration</th><th>Error</th><th>Trace</th></tr>' + slowRows + '</table>';
    }
    el.innerHTML = html;
}

function showTopologyEdgeDetails(src, tgt, el) {
    var key = src + ' \u2192 ' + tgt;
    var data = topologyEdgeData[key];
    if (!data) {
        el.innerHTML = '<p>No data for edge: ' + escapeHtml(src) + ' \u2192 ' + escapeHtml(tgt) + '</p>';
        return;
    }
    var traceLinks = renderTraceLinks(data.traces || []);
    var slowRows = '';
    (data.slow_operations || []).slice(0, 10).forEach(function(op, i) {
        var errClass = op.error ? 'error-high' : '';
        slowRows += '<tr>' +
            '<td>' + (i + 1) + '</td>' +
            '<td>' + escapeHtml(op.operation_name || '-') + '</td>' +
            '<td>' + op.duration_ms.toFixed(2) + ' ms</td>' +
            '<td class="' + errClass + '">' + (op.error ? 'Yes' : 'No') + '</td>' +
            '<td><span class="trace-link" data-trace-id="' + escapeAttr(op.trace_id) + '">' + escapeHtml(op.trace_id) + '</span></td>' +
            '</tr>';
    });
    var html = '<h4>Call Edge: ' + escapeHtml(src) + ' \u2192 ' + escapeHtml(tgt) + '</h4>' +
        '<p><b>Related traces (' + (data.trace_count || 0) + '):</b> ' + traceLinks + '</p>';
    if (slowRows) {
        html += '<h5>Slow Operations (Top 10, > 500ms):</h5>' +
            '<table><tr><th>#</th><th>Operation</th><th>Duration</th><th>Error</th><th>Trace</th></tr>' + slowRows + '</table>';
    }
    el.innerHTML = html;
}

function escapeHtml(s) {
    if (s === null || s === undefined) return '';
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function escapeAttr(s) {
    return escapeHtml(s);
}

window.addEventListener('DOMContentLoaded', function() {
    if (sortedTraceIds && sortedTraceIds.length > 0) {
        switchTrace(sortedTraceIds[0]);
    }
    var selects = document.querySelectorAll('.trace-selector-bar select');
    selects.forEach(function(s) {
        if (s && s.closest) {
            var c = s.closest('.container');
            if (c) Plotly.Plots.resize(c);
        }
    });
});
</script>"""

    def export_combined(
        self,
        output_path: str,
        waterfall_fig: Optional[go.Figure] = None,
        flame_fig: Optional[go.Figure] = None,
        timeline_fig: Optional[go.Figure] = None,
        summary: Optional[Dict] = None,
    ) -> str:
        trace_data = {"default": {
            "waterfall_fig": waterfall_fig,
            "flame_fig": flame_fig,
            "critical_path": [],
            "critical_duration_ms": 0,
            "span_count": summary.get("total_spans", 0) if summary else 0,
            "error_count": summary.get("total_errors", 0) if summary else 0,
            "service_breakdown": {},
        }}
        return self.export_multi_trace(
            output_path=output_path,
            trace_data=trace_data,
            summary_overview_fig=timeline_fig,
            summary=summary,
        )

    def _render_summary(self, summary: Dict) -> str:
        total_spans = summary.get("total_spans", 0)
        total_traces = summary.get("total_traces", 0)
        total_errors = summary.get("total_errors", 0)
        error_rate = summary.get("overall_error_rate", 0.0)
        top_slow = summary.get("slowest_spans", [])[:5]
        error_services = summary.get("error_services", [])[:5]
        error_class = _pct_color(error_rate)
        slow_spans_rows = ""
        for s in top_slow:
            slow_spans_rows += f"""<tr>
                <td>{_e(s.get('service_name', '-'))}</td>
                <td>{_e(s.get('operation_name', '-'))}</td>
                <td>{s.get('count', 0)}</td>
                <td>{s.get('p99_ms', 0):.2f} ms</td>
                <td>{s.get('avg_ms', 0):.2f} ms</td>
            </tr>"""
        error_rows = ""
        for s in error_services:
            rate = s.get("error_rate", 0)
            cls = _pct_color(rate)
            error_rows += f"""<tr>
                <td>{_e(s.get('service_name', '-'))}</td>
                <td>{s.get('total_count', 0)}</td>
                <td>{s.get('error_count', 0)}</td>
                <td class="{cls}">{rate * 100:.2f}%</td>
            </tr>"""
        return f"""
    <div class="summary-card">
        <h2>📊 Analysis Summary</h2>
        <div class="summary-grid">
            <div class="summary-item">
                <div class="summary-label">Total Spans</div>
                <div class="summary-value">{total_spans:,}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Total Traces</div>
                <div class="summary-value">{total_traces:,}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Total Errors</div>
                <div class="summary-value" style="color: {'#ff0000' if total_errors > 0 else '#00aa00'}">{total_errors:,}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Overall Error Rate</div>
                <div class="summary-value {error_class}">{error_rate * 100:.2f}%</div>
            </div>
        </div>
        <h3>Slowest Operations (Top 5 by P99)</h3>
        <table>
            <tr><th>Service</th><th>Operation</th><th>Count</th><th>P99 Latency</th><th>Avg Latency</th></tr>
            {slow_spans_rows}
        </table>
        <h3>High Error Services</h3>
        <table>
            <tr><th>Service</th><th>Total Spans</th><th>Error Count</th><th>Error Rate</th></tr>
            {error_rows}
        </table>
    </div>"""
