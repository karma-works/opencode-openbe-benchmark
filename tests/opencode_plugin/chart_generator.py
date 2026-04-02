"""SVG chart generator for OpenCode plugin test outcomes.

Primary focus: Plugin ON vs Plugin OFF comparison.
Secondary detail: per-model breakdown within each plugin state.

Charts:
1. Summary dashboard  — plugin-state pass rates + per-model table
2. Plugin comparison  — pass/fail matrix grouped by plugin state
3. Tool calls         — plugin ON vs OFF, models as bars within each group
4. Files generated    — same structure
5. Duration           — same structure
"""

import csv
from pathlib import Path


RESULTS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "test_results" / "opencode_plugin"
)
DEFAULT_CSV = RESULTS_DIR / "test_outcomes.csv"
SVG_DIR = RESULTS_DIR / "charts"

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------

COLORS = {
    "pass": "#22c55e",
    "fail": "#ef4444",
    "error": "#f97316",
    "skip": "#334155",
    "plugin_on": "#3b82f6",
    "plugin_on_dim": "#1d4ed8",
    "plugin_off": "#8b5cf6",
    "plugin_off_dim": "#6d28d9",
    "bg": "#0f172a",
    "surface": "#1e293b",
    "surface2": "#253347",
    "border": "#334155",
    "text_primary": "#f1f5f9",
    "text_secondary": "#94a3b8",
    "grid": "#1e293b",
    "divider": "#475569",
}

# Model display shorthands
MODEL_SHORT = {
    "openrouter/openai/gpt-oss-120b:free": "gpt-oss-120b",
    "openrouter/qwen/qwen3-6b-plus-preview:free": "qwen3-6b-plus",
    "openrouter/qwen/qwen3.5-flash-02-23": "qwen3.5-flash",
    "openrouter/z-ai/glm-5v-turbo": "glm-5v-turbo",
    "openrouter/google/gemini-3.1-flash-lite-preview": "gemini-3.1-flash-lite",
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_outcomes(csv_path: Path = DEFAULT_CSV) -> list[dict]:
    if not csv_path.exists():
        return []
    with open(csv_path, newline="") as f:
        return list(csv.DictReader(f))


def get_models(outcomes: list[dict]) -> list[str]:
    seen: list[str] = []
    for o in outcomes:
        m = o.get("model", "unknown")
        if m not in seen:
            seen.append(m)
    return seen


def get_test_names(outcomes: list[dict]) -> list[str]:
    seen: list[str] = []
    for o in outcomes:
        n = o.get("test_name", "unknown")
        if n not in seen:
            seen.append(n)
    return seen


def short_model(model: str) -> str:
    if model in MODEL_SHORT:
        return MODEL_SHORT[model]
    parts = model.split("/")
    return parts[-1] if parts else model


# ---------------------------------------------------------------------------
# SVG helpers
# ---------------------------------------------------------------------------


def svg_rect(
    x: float, y: float, w: float, h: float, fill: str, rx: float = 4, opacity: float = 1.0
) -> str:
    op = f' opacity="{opacity}"' if opacity < 1.0 else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}"{op}/>'


def svg_text(
    x: float,
    y: float,
    text: str,
    size: int = 12,
    fill: str = COLORS["text_primary"],
    anchor: str = "start",
    weight: str = "normal",
    opacity: float = 1.0,
) -> str:
    op = f' opacity="{opacity}"' if opacity < 1.0 else ""
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}"'
        f' font-family="system-ui, -apple-system, sans-serif"'
        f' text-anchor="{anchor}" font-weight="{weight}"{op}>{_esc(text)}</text>'
    )


def svg_line(
    x1: float, y1: float, x2: float, y2: float,
    stroke: str = COLORS["border"], width: float = 1, dash: str = ""
) -> str:
    da = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{width}"{da}/>'


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _empty_svg(message: str) -> str:
    w, h = 400, 100
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">'
        f'<rect width="{w}" height="{h}" fill="{COLORS["bg"]}"/>'
        f'{svg_text(w/2, h/2+4, message, size=14, fill=COLORS["text_secondary"], anchor="middle")}'
        f"</svg>"
    )


# ---------------------------------------------------------------------------
# Chart 1: Summary Dashboard
# Primary: Plugin ON vs OFF pass rates
# Secondary: per-model breakdown table
# ---------------------------------------------------------------------------


def render_summary_dashboard(outcomes: list[dict]) -> str:
    models = get_models(outcomes)
    if not models:
        return _empty_svg("No test data available")

    on_outcomes = [o for o in outcomes if o.get("plugin_enabled") == "True"]
    off_outcomes = [o for o in outcomes if o.get("plugin_enabled") == "False"]

    def pass_rate(rows: list[dict]) -> tuple[int, int, float]:
        total = len(rows)
        passed = sum(1 for o in rows if o.get("status") == "pass")
        return passed, total, (passed / total * 100) if total > 0 else 0.0

    on_passed, on_total, on_rate = pass_rate(on_outcomes)
    off_passed, off_total, off_rate = pass_rate(off_outcomes)
    all_passed, all_total, all_rate = pass_rate(outcomes)

    margin = 40
    title_h = 70
    section_w = 340
    section_h = 130
    section_gap = 24
    table_row_h = 22
    table_header_h = 30
    table_h = table_header_h + len(models) * table_row_h + 20

    width = margin + section_w + section_gap + section_w + margin
    height = margin + title_h + section_h + 40 + table_h + margin

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="{COLORS["bg"]}"/>',
        # Title
        svg_text(margin, margin + 22, "Plugin Benchmark — Summary", size=20, weight="bold"),
        svg_text(
            margin, margin + 44,
            f"{len(models)} model(s)  •  {all_passed}/{all_total} tests passed  •  overall {all_rate:.0f}%",
            size=13, fill=COLORS["text_secondary"],
        ),
    ]

    # Two big section cards: Plugin ON | Plugin OFF
    for si, (label, color, passed, total, rate, sub_outcomes) in enumerate([
        ("Plugin ON", COLORS["plugin_on"], on_passed, on_total, on_rate, on_outcomes),
        ("Plugin OFF", COLORS["plugin_off"], off_passed, off_total, off_rate, off_outcomes),
    ]):
        sx = margin + si * (section_w + section_gap)
        sy = margin + title_h

        lines.append(svg_rect(sx, sy, section_w, section_h, COLORS["surface"], rx=10))
        lines.append(svg_rect(sx, sy, section_w, 4, color, rx=2))

        # Big pass rate
        rate_color = COLORS["pass"] if rate >= 80 else COLORS["fail"]
        lines.append(svg_text(sx + section_w / 2, sy + 52, f"{rate:.0f}%",
                               size=36, fill=rate_color, anchor="middle", weight="bold"))
        lines.append(svg_text(sx + section_w / 2, sy + 74, "pass rate",
                               size=12, fill=COLORS["text_secondary"], anchor="middle"))
        lines.append(svg_text(sx + section_w / 2, sy + 96, f"{passed}/{total} tests passed",
                               size=12, fill=COLORS["text_primary"], anchor="middle"))

        # Label badge
        lines.append(svg_rect(sx + 12, sy + 12, 90, 22, color, rx=4, opacity=0.2))
        lines.append(svg_text(sx + 57, sy + 27, label, size=12, fill=color,
                               anchor="middle", weight="bold"))

    # Model breakdown table
    ty = margin + title_h + section_h + 36
    lines.append(svg_text(margin, ty, "Per-model breakdown", size=14, weight="bold"))

    # Table header
    thy = ty + table_header_h
    col_model = margin
    col_on = margin + 200
    col_off = margin + 340
    col_tool = margin + 480
    col_dur = margin + 590

    for cx, label in [
        (col_model, "Model"),
        (col_on, "Plugin ON"),
        (col_off, "Plugin OFF"),
        (col_tool, "autobe calls"),
        (col_dur, "avg dur"),
    ]:
        lines.append(svg_text(cx, thy, label, size=11,
                               fill=COLORS["text_secondary"], weight="bold"))

    lines.append(svg_line(margin, thy + 6, width - margin, thy + 6,
                           stroke=COLORS["border"]))

    for mi, model in enumerate(models):
        ry = thy + table_row_h + mi * table_row_h
        m_on = [o for o in outcomes if o.get("model") == model and o.get("plugin_enabled") == "True"]
        m_off = [o for o in outcomes if o.get("model") == model and o.get("plugin_enabled") == "False"]
        on_p, on_t, on_r = pass_rate(m_on)
        off_p, off_t, off_r = pass_rate(m_off)
        autobe_calls = sum(int(o.get("autobe_calls_count", 0)) for o in m_on + m_off)
        avg_dur = (
            sum(float(o.get("duration_s", 0)) for o in m_on + m_off) / len(m_on + m_off)
            if m_on + m_off else 0
        )

        # Alternating row bg
        if mi % 2 == 0:
            lines.append(svg_rect(margin - 4, ry - 14, width - 2 * margin + 8, table_row_h,
                                   COLORS["surface2"], rx=3))

        lines.append(svg_text(col_model, ry, short_model(model), size=11,
                               fill=COLORS["text_primary"]))
        on_col = COLORS["pass"] if on_r >= 80 else COLORS["fail"]
        off_col = COLORS["pass"] if off_r >= 80 else COLORS["fail"]
        lines.append(svg_text(col_on, ry, f"{on_p}/{on_t} ({on_r:.0f}%)",
                               size=11, fill=on_col))
        lines.append(svg_text(col_off, ry, f"{off_p}/{off_t} ({off_r:.0f}%)",
                               size=11, fill=off_col))
        lines.append(svg_text(col_tool, ry, str(autobe_calls), size=11,
                               fill=COLORS["text_secondary"]))
        lines.append(svg_text(col_dur, ry, f"{avg_dur:.1f}s", size=11,
                               fill=COLORS["text_secondary"]))

    lines.append("</svg>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Chart 2: Plugin Comparison Matrix
# Rows = tests, Columns grouped: [Plugin ON: m1 m2 ...] | [Plugin OFF: m1 m2 ...]
# ---------------------------------------------------------------------------


def render_pass_fail_matrix(outcomes: list[dict]) -> str:
    models = get_models(outcomes)
    tests = get_test_names(outcomes)

    if not models or not tests:
        return _empty_svg("No test data available")

    cell_w = 100
    cell_h = 38
    label_w = 240
    header_h = 90
    margin = 30
    divider_gap = 20  # gap between the two plugin groups

    # Width: label + [ON: n models] + divider_gap + [OFF: n models]
    group_w = len(models) * cell_w
    width = margin + label_w + group_w + divider_gap + group_w + margin
    height = margin + header_h + len(tests) * cell_h + margin + 20

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="{COLORS["bg"]}"/>',
        svg_text(margin, margin + 22, "Pass / Fail Matrix", size=18, weight="bold"),
        svg_text(margin, margin + 42, "Primary: Plugin ON vs OFF  •  Secondary: per model",
                 size=12, fill=COLORS["text_secondary"]),
    ]

    # Group header backgrounds
    on_x = margin + label_w
    off_x = margin + label_w + group_w + divider_gap
    group_header_y = margin + 54

    lines.append(svg_rect(on_x, group_header_y, group_w, 32,
                           COLORS["plugin_on"], rx=6, opacity=0.15))
    lines.append(svg_text(on_x + group_w / 2, group_header_y + 20, "Plugin ON",
                           size=13, fill=COLORS["plugin_on"], anchor="middle", weight="bold"))

    lines.append(svg_rect(off_x, group_header_y, group_w, 32,
                           COLORS["plugin_off"], rx=6, opacity=0.15))
    lines.append(svg_text(off_x + group_w / 2, group_header_y + 20, "Plugin OFF",
                           size=13, fill=COLORS["plugin_off"], anchor="middle", weight="bold"))

    # Model sub-headers
    sub_y = margin + header_h - 8
    for group_x, ps_label in [(on_x, "True"), (off_x, "False")]:
        for mi, model in enumerate(models):
            cx = group_x + mi * cell_w + cell_w / 2
            lines.append(svg_text(cx, sub_y, short_model(model),
                                   size=9, fill=COLORS["text_secondary"], anchor="middle"))

    # Divider line
    div_x = margin + label_w + group_w + divider_gap / 2
    lines.append(svg_line(div_x, margin + 54, div_x,
                           margin + header_h + len(tests) * cell_h,
                           stroke=COLORS["divider"], width=1, dash="4 3"))

    # Rows
    for ti, test in enumerate(tests):
        ry = margin + header_h + ti * cell_h
        # Alternating row bg
        if ti % 2 == 0:
            lines.append(svg_rect(margin, ry, width - 2 * margin,
                                   cell_h, COLORS["surface"], rx=0, opacity=0.5))

        # Shorten test name
        short_test = test.replace("test_autobe_", "").replace("_", " ")
        lines.append(svg_text(margin + 8, ry + cell_h / 2 + 4, short_test, size=11))

        for group_x, ps in [(on_x, "True"), (off_x, "False")]:
            for mi, model in enumerate(models):
                cx = group_x + mi * cell_w
                status = "skip"
                for o in outcomes:
                    if (o.get("model") == model
                            and o.get("plugin_enabled") == ps
                            and o.get("test_name") == test):
                        status = o.get("status", "skip")
                        break

                fill = COLORS.get(status, COLORS["skip"])
                lines.append(svg_rect(cx + 3, ry + 4, cell_w - 6, cell_h - 8, fill, rx=5))
                label = "✓" if status == "pass" else ("✗" if status == "fail" else status.upper())
                lines.append(svg_text(cx + cell_w / 2, ry + cell_h / 2 + 4,
                                       label, size=11, fill="#fff", anchor="middle", weight="bold"))

    lines.append("</svg>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Shared: grouped bar chart (plugin state = primary group, models = bars)
# ---------------------------------------------------------------------------


def _render_grouped_bar_chart(
    outcomes: list[dict],
    title: str,
    value_fn,
    y_label_fn,
) -> str:
    models = get_models(outcomes)
    if not models:
        return _empty_svg("No test data available")

    bar_w = 36
    bar_gap = 8
    group_gap = 50
    margin_l = 70
    margin_r = 30
    margin_top = 80
    margin_bot = 70
    chart_h = 220

    # Two groups: ON / OFF
    group_w = len(models) * (bar_w + bar_gap) - bar_gap
    width = margin_l + group_w + group_gap + group_w + margin_r
    height = margin_top + chart_h + margin_bot

    # Values
    vals: dict[tuple[str, str], float] = {}
    max_val = 1.0
    for ps in ["True", "False"]:
        for model in models:
            v = value_fn(outcomes, model, ps)
            vals[(model, ps)] = v
            if v > max_val:
                max_val = v

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="{COLORS["bg"]}"/>',
        svg_text(margin_l, 26, title, size=16, weight="bold"),
        svg_text(margin_l, 46, "Primary grouping: Plugin ON vs OFF  •  bars = models",
                 size=11, fill=COLORS["text_secondary"]),
    ]

    # Y-axis grid + labels
    for i in range(5):
        gy = margin_top + chart_h - (i / 4) * chart_h
        gv = max_val * i / 4
        lines.append(svg_line(margin_l - 4, gy, width - margin_r, gy,
                               stroke=COLORS["border"], dash="3 3"))
        lines.append(svg_text(margin_l - 8, gy + 4, y_label_fn(gv),
                               size=10, fill=COLORS["text_secondary"], anchor="end"))

    # Baseline
    baseline_y = margin_top + chart_h
    lines.append(svg_line(margin_l, baseline_y, width - margin_r, baseline_y,
                           stroke=COLORS["border"]))

    for gi, (ps, group_color, group_label) in enumerate([
        ("True", COLORS["plugin_on"], "Plugin ON"),
        ("False", COLORS["plugin_off"], "Plugin OFF"),
    ]):
        gx = margin_l + gi * (group_w + group_gap)

        # Group background band
        lines.append(svg_rect(gx - 8, margin_top - 10, group_w + 16,
                               chart_h + 10, group_color, rx=6, opacity=0.06))

        # Group label
        lines.append(svg_text(gx + group_w / 2, margin_top - 16, group_label,
                               size=12, fill=group_color, anchor="middle", weight="bold"))

        for mi, model in enumerate(models):
            v = vals[(model, ps)]
            bh = (v / max_val) * chart_h if max_val > 0 else 0
            bx = gx + mi * (bar_w + bar_gap)
            by = baseline_y - bh

            lines.append(svg_rect(bx, by, bar_w, bh, group_color, rx=4))

            # Value label above bar
            if v > 0:
                lines.append(svg_text(bx + bar_w / 2, by - 5,
                                       y_label_fn(v), size=9,
                                       fill=COLORS["text_primary"], anchor="middle"))

            # Model label below
            lines.append(svg_text(bx + bar_w / 2, baseline_y + 16,
                                   short_model(model), size=8,
                                   fill=COLORS["text_secondary"], anchor="middle"))

    lines.append("</svg>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Chart 3: Tool Calls
# ---------------------------------------------------------------------------


def render_tool_calls_chart(outcomes: list[dict]) -> str:
    def value_fn(outcomes, model, ps):
        return sum(
            int(o.get("tool_calls_count", 0))
            for o in outcomes
            if o.get("model") == model and o.get("plugin_enabled") == ps
        )

    return _render_grouped_bar_chart(
        outcomes,
        "Total Tool Calls",
        value_fn,
        lambda v: str(int(v)),
    )


# ---------------------------------------------------------------------------
# Chart 4: Files Generated
# ---------------------------------------------------------------------------


def render_files_generated_chart(outcomes: list[dict]) -> str:
    def value_fn(outcomes, model, ps):
        return sum(
            int(o.get("files_generated", 0))
            for o in outcomes
            if o.get("model") == model and o.get("plugin_enabled") == ps
        )

    return _render_grouped_bar_chart(
        outcomes,
        "Files Generated",
        value_fn,
        lambda v: str(int(v)),
    )


# ---------------------------------------------------------------------------
# Chart 5: Duration
# ---------------------------------------------------------------------------


def render_duration_chart(outcomes: list[dict]) -> str:
    def value_fn(outcomes, model, ps):
        rows = [o for o in outcomes if o.get("model") == model and o.get("plugin_enabled") == ps]
        if not rows:
            return 0.0
        return sum(float(o.get("duration_s", 0)) for o in rows) / len(rows)

    return _render_grouped_bar_chart(
        outcomes,
        "Avg Test Duration (seconds)",
        value_fn,
        lambda v: f"{v:.1f}s",
    )


# ---------------------------------------------------------------------------
# Main: generate all charts
# ---------------------------------------------------------------------------


def generate_all_charts(csv_path: Path = DEFAULT_CSV) -> dict[str, Path]:
    outcomes = load_outcomes(csv_path)
    SVG_DIR.mkdir(parents=True, exist_ok=True)

    charts = {
        "summary": render_summary_dashboard(outcomes),
        "pass_fail_matrix": render_pass_fail_matrix(outcomes),
        "tool_calls": render_tool_calls_chart(outcomes),
        "files_generated": render_files_generated_chart(outcomes),
        "duration": render_duration_chart(outcomes),
    }

    paths = {}
    for name, svg_content in charts.items():
        path = SVG_DIR / f"{name}.svg"
        path.write_text(svg_content)
        paths[name] = path

    return paths


if __name__ == "__main__":
    paths = generate_all_charts()
    for name, path in paths.items():
        print(f"Generated {name}: {path}")
