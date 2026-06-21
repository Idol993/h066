import json
import os
from typing import Dict, List, Optional
import plotly.graph_objects as go
import plotly.io as pio

from ..utils.time_utils import TimeUtils


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
        trace_json_data = {}
        for tid in sorted_trace_ids:
            td = trace_data[tid]
            trace_json_data[tid] = {
                "critical_duration_ms": td.get("critical_duration_ms", 0),
                "critical_path": td.get("critical_path", []),
                "span_count": td.get("span_count", 0),
            }
        per_trace_html_parts = []
        for tid in sorted_trace_ids:
            td = trace_data[tid]
            waterfall_fig = td.get("waterfall_fig")
            flame_fig = td.get("flame_fig")
            cp = td.get("critical_path", [])
            cp_dur = td.get("critical_duration_ms", 0)
            wf_html = ""
            if waterfall_fig is not None:
                wf_html = pio.to_html(
                    waterfall_fig,
                    full_html=False,
                    include_plotlyjs=False,
                    div_id=f"wf-{tid}",
                )
            fl_html = ""
            if flame_fig is not None:
                fl_html = pio.to_html(
                    flame_fig,
                    full_html=False,
                    include_plotlyjs=False,
                    div_id=f"fl-{tid}",
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
                    <td>{span.get('service_name', '-')}</td>
                    <td>{span.get('operation_name', '-')}</td>
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
            <div class="trace-panel" id="panel-{tid}" style="display:none;">
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
            dur = td.get("critical_duration_ms", 0)
            sc = td.get("span_count", 0)
            label = f"{tid[:16]}... ({dur:.0f}ms, {sc} spans)"
            selected = " selected" if i == 0 else ""
            trace_selector_options += f'<option value="{tid}"{selected}>{label}</option>\n'
        summary_html = self._render_summary(summary or {})
        trace_json_str = json.dumps(trace_json_data, default=str)
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Trace Analysis Report</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    margin: 0; padding: 20px; background: #f5f5f5;
}}
.container {{ max-width: 1500px; margin: 0 auto; }}
h1 {{ color: #333; border-bottom: 2px solid #0077cc; padding-bottom: 10px; }}
h2 {{ color: #444; margin-top: 30px; }}
h3 {{ color: #555; margin-top: 20px; margin-bottom: 10px; }}
.summary-card {{
    background: white; border-radius: 8px; padding: 20px;
    margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}}
.summary-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;
}}
.summary-item {{
    background: #f8f9fa; padding: 15px; border-radius: 6px; border-left: 4px solid #0077cc;
}}
.summary-label {{ font-size: 12px; color: #666; text-transform: uppercase; margin-bottom: 5px; }}
.summary-value {{ font-size: 24px; font-weight: bold; color: #333; }}
.chart-container {{
    background: white; border-radius: 8px; padding: 15px; margin-bottom: 15px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1); overflow-x: auto;
}}
.chart-section {{ margin-bottom: 25px; }}
.error-high {{ color: #ff0000; font-weight: bold; }}
.error-medium {{ color: #ffa500; font-weight: bold; }}
.error-low {{ color: #00aa00; }}
.trace-selector-bar {{
    background: white; border-radius: 8px; padding: 15px 20px;
    margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    display: flex; align-items: center; gap: 15px; flex-wrap: wrap;
}}
.trace-selector-bar label {{ font-weight: 600; color: #333; white-space: nowrap; }}
.trace-selector-bar select {{
    flex: 1; min-width: 300px; padding: 8px 12px; border-radius: 6px;
    border: 1px solid #ccc; font-size: 14px;
}}
.trace-selector-bar .trace-meta {{
    font-size: 13px; color: #666;
}}
.tabs {{
    display: flex; gap: 0; margin-bottom: 0; border-bottom: 2px solid #ddd;
}}
.tab {{
    padding: 10px 20px; cursor: pointer; background: #e9ecef; border: none;
    border-bottom: 2px solid transparent; margin-bottom: -2px; font-size: 14px;
}}
.tab.active {{ background: white; border-bottom: 2px solid #0077cc; font-weight: bold; }}
.tab-content {{ display: none; }}
.tab-content.active {{ display: block; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
th {{ background: #f0f0f0; font-weight: 600; }}
tr:hover {{ background: #f8f9fa; }}
</style>
</head>
<body>
<div class="container">
    <h1>🔍 Distributed Trace Analysis Report</h1>
    {summary_html}

    <div class="tabs">
        <button class="tab active" onclick="switchMainTab(event, 'per-trace')">Per-Trace Analysis</button>
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

    <div id="overview" class="tab-content">
        <div class="chart-section">
            <h3>Service Overview - Latency by Service & Operation</h3>
            <div class="chart-container">{overview_html}</div>
        </div>
    </div>
</div>
<script>
var traceData = {trace_json_str};
var sortedTraceIds = {json.dumps(sorted_trace_ids)};

function switchMainTab(evt, tabName) {{
    var tabcontent = document.getElementsByClassName("tab-content");
    for (var i = 0; i < tabcontent.length; i++) {{
        tabcontent[i].className = tabcontent[i].className.replace(" active", "");
    }}
    var tablinks = document.getElementsByClassName("tab");
    for (var i = 0; i < tablinks.length; i++) {{
        tablinks[i].className = tablinks[i].className.replace(" active", "");
    }}
    document.getElementById(tabName).className += " active";
    evt.currentTarget.className += " active";
}}

function switchTrace(traceId) {{
    var panels = document.querySelectorAll('.trace-panel');
    panels.forEach(function(p) {{ p.style.display = 'none'; }});
    var target = document.getElementById('panel-' + traceId);
    if (target) {{
        target.style.display = 'block';
    }}
    var meta = traceData[traceId];
    var metaEl = document.getElementById('trace-meta');
    if (meta && metaEl) {{
        metaEl.textContent = 'Critical path: ' + meta.critical_duration_ms.toFixed(1) +
            ' ms | Spans: ' + meta.span_count;
    }}
}}

switchTrace(sortedTraceIds[0]);

window.addEventListener('DOMContentLoaded', function() {{
    var selects = document.querySelectorAll('.trace-selector-bar select');
    selects.forEach(function(s) {{
        Plotly.Plots.resize(s.closest('.container'));
    }});
}});
</script>
</body>
</html>"""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        return output_path

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
        error_class = "error-low"
        if error_rate >= 0.05:
            error_class = "error-high"
        elif error_rate >= 0.01:
            error_class = "error-medium"
        slow_spans_rows = ""
        for s in top_slow:
            slow_spans_rows += f"""<tr>
                <td>{s.get('service_name', '-')}</td>
                <td>{s.get('operation_name', '-')}</td>
                <td>{s.get('count', 0)}</td>
                <td>{s.get('p99_ms', 0):.2f} ms</td>
                <td>{s.get('avg_ms', 0):.2f} ms</td>
            </tr>"""
        error_rows = ""
        for s in error_services:
            rate = s.get("error_rate", 0)
            cls = "error-low"
            if rate >= 0.05:
                cls = "error-high"
            elif rate >= 0.01:
                cls = "error-medium"
            error_rows += f"""<tr>
                <td>{s.get('service_name', '-')}</td>
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
