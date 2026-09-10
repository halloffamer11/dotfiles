#!/usr/bin/env python3
"""Read-only HTML view of gathered benchmark data for the setup wizard."""
import html
from collections import defaultdict

EFFORT_ORDER = ("xhigh", "high", "medium", "low", "none")


def _esc(value):
    if value is None:
        return "—"
    return html.escape(str(value), quote=True)


def _td(value):
    return f"<td>{_esc(value)}</td>"


def _th(value):
    return f"<th>{_esc(value)}</th>"


def _fmt_pct(score):
    if score is None:
        return "—"
    return f"{score * 100:.1f}"


def _fmt_aa(score):
    if score is None:
        return "—"
    if abs(score - round(score)) < 1e-9:
        return str(int(round(score)))
    return f"{score:.1f}"


def _table(headers, rows, caption=None, row_classes=None):
    parts = ["<table>"]
    if caption:
        parts.append(f"<caption>{_esc(caption)}</caption>")
    parts.append("<thead><tr>" + "".join(_th(h) for h in headers) + "</tr></thead>")
    parts.append("<tbody>")
    for i, row in enumerate(rows):
        cls = ""
        if row_classes and i < len(row_classes) and row_classes[i]:
            cls = f' class="{html.escape(row_classes[i], quote=True)}"'
        parts.append("<tr" + cls + ">" + "".join(_td(c) for c in row) + "</tr>")
    parts.append("</tbody></table>")
    return "\n".join(parts)


def _missing(kind):
    return f'<p class="missing">{_esc(kind)} data is missing.</p>'


def _epoch_section(bench):
    epoch_names = bench.get("epoch_benchmarks") or []
    models = bench.get("models") or {}
    if not models:
        return [_missing("Epoch benchmark")]
    headers = ["Lane(s)", "Model", "Effort", *epoch_names, "Epoch mean rank"]
    items = []
    for model, rec in models.items():
        epoch = rec.get("epoch") or {}
        items.append((epoch.get("mean"), model, rec))
    items.sort(key=lambda item: (item[0] is None, item[0] if item[0] is not None else 0, item[1]))
    rows = []
    for _mean, model, rec in items:
        epoch = rec.get("epoch") or {}
        cells = epoch.get("cells") or {}
        values = []
        for name in epoch_names:
            cell = cells.get(name)
            values.append("—" if not cell else _fmt_pct(cell.get("performance")))
        rows.append([
            ", ".join(rec.get("lanes") or []),
            model,
            rec.get("lane_effort") or "—",
            *values,
            epoch.get("mean_s") or "—",
        ])
    return ["<h2>Epoch benchmarks</h2>", _table(headers, rows)]


def _aa_section(bench):
    skipped = bench.get("aa_skipped")
    if skipped is not None:
        return [f'<p class="missing">Artificial Analysis data is missing ({_esc(skipped)}).</p>']
    aa_names = bench.get("aa_columns") or []
    models = bench.get("models") or {}
    if not models:
        return [_missing("Artificial Analysis")]
    headers = ["Lane(s)", "Model", *aa_names, "AA mean rank"]
    items = []
    for model, rec in models.items():
        aa = rec.get("aa") or {}
        items.append((aa.get("mean"), model, rec))
    items.sort(key=lambda item: (item[0] is None, item[0] if item[0] is not None else 0, item[1]))
    rows = []
    for _mean, model, rec in items:
        aa = rec.get("aa")
        cols = (aa or {}).get("cols") or {}
        values = [_fmt_aa(cols.get(name)) for name in aa_names]
        rows.append([
            ", ".join(rec.get("lanes") or []),
            model,
            *values,
            (aa or {}).get("mean_s") or "—",
        ])
    return ["<h2>Artificial Analysis</h2>", _table(headers, rows)]


def _notes_section(bench):
    notes = bench.get("notes") or []
    if not notes:
        return []
    items = "".join(f"<li>{_esc(note)}</li>" for note in notes)
    return ["<h2>Notes</h2>", f"<ul>{items}</ul>"]


def _lanes_section(lanes_doc):
    lanes = (lanes_doc or {}).get("lanes") or {}
    if not lanes:
        return []
    headers = ["Lane", "Model", "Effort", "Meter"]
    rows = []
    for name in lanes:
        lane = lanes[name]
        rows.append([name, lane.get("model"), lane.get("effort"), lane.get("meter")])
    return ["<h2>Catalog lanes</h2>", _table(headers, rows, caption="Incoming catalog (read-only)")]


def _effort_key(effort):
    try:
        return (EFFORT_ORDER.index(effort), effort)
    except ValueError:
        return (len(EFFORT_ORDER), effort)


def _effort_section(effort_rows):
    if effort_rows is None:
        return [_missing("Per-effort")]
    grouped = defaultdict(lambda: defaultdict(list))
    for row in effort_rows:
        if not isinstance(row, dict):
            continue
        model = row.get("model") or ""
        effort = row.get("effort") or ""
        grouped[model][effort].append(row)
    if not grouped:
        return ["<h2>Per-effort scores and cost</h2>", "<p>No per-effort rows.</p>"]
    parts = ["<h2>Per-effort scores and cost</h2>"]
    headers = ["model", "effort", "score", "cost_usd", "benchmark", "source", "observed", "provenance", "flag"]
    rows = []
    classes = []
    for model in sorted(grouped):
        for effort in sorted(grouped[model], key=_effort_key):
            for row in grouped[model][effort]:
                uncertain = bool(row.get("uncertain"))
                rows.append([
                    model,
                    effort,
                    row.get("score"),
                    row.get("cost_usd"),
                    row.get("benchmark"),
                    row.get("source"),
                    row.get("observed"),
                    row.get("provenance"),
                    "uncertain" if uncertain else "",
                ])
                classes.append("uncertain" if uncertain else "")
    parts.append(_table(headers, rows, row_classes=classes))
    return parts



# Score against cost, per model, one point per effort. This is the picture the
# pre-screen reasons over: a point up and to the LEFT of another dominates it —
# at least the score for no more money. Inline SVG, because the page may load no
# remote script and a table of numbers does not show domination at a glance.
PLOT_W, PLOT_H = 640, 300
PLOT_PAD = {"l": 54, "r": 12, "t": 12, "b": 38}
SERIES_COLOURS = ("#1f4e79", "#a6410d", "#2f6b2f", "#6b2f6b", "#7a6a12", "#155e63")


def _plot_section(effort_rows):
    points = []
    for row in effort_rows or []:
        if not isinstance(row, dict) or row.get("uncertain"):
            continue
        score, cost = row.get("score"), row.get("cost_usd")
        if isinstance(score, bool) or isinstance(cost, bool):
            continue
        if not isinstance(score, (int, float)) or not isinstance(cost, (int, float)):
            continue
        if cost <= 0:
            continue
        points.append((row.get("model") or "?", row.get("effort") or "?",
                       float(cost), float(score), row.get("benchmark") or ""))
    if not points:
        return ["<h2>Score against cost</h2>",
                "<p>No row carries both a score and a cost, so there is nothing to plot.</p>"]

    # one plot per benchmark: cost means different things across sources
    by_bench = defaultdict(list)
    for model, effort, cost, score, bench_name in points:
        by_bench[bench_name].append((model, effort, cost, score))

    out = ["<h2>Score against cost</h2>",
           "<p>A point up and to the left of another dominates it: at least the score "
           "for no more money. One plot per benchmark, because cost is not comparable "
           "across sources.</p>"]
    for bench_name in sorted(by_bench):
        series = defaultdict(list)
        for model, effort, cost, score in by_bench[bench_name]:
            series[model].append((cost, score, effort))
        out.extend(_svg_plot(bench_name, series))
    return out


def _svg_plot(bench_name, series):
    costs = [c for pts in series.values() for c, _, _ in pts]
    scores = [s for pts in series.values() for _, s, _ in pts]
    cmin, cmax = min(costs), max(costs)
    smin, smax = min(scores), max(scores)
    if cmax == cmin:
        cmin, cmax = cmin * 0.9, cmax * 1.1 or 1.0
    if smax == smin:
        smin, smax = smin - 1, smax + 1
    iw = PLOT_W - PLOT_PAD["l"] - PLOT_PAD["r"]
    ih = PLOT_H - PLOT_PAD["t"] - PLOT_PAD["b"]

    def x(c):
        return PLOT_PAD["l"] + (c - cmin) / (cmax - cmin) * iw

    def y(sc):
        return PLOT_PAD["t"] + ih - (sc - smin) / (smax - smin) * ih

    parts = [f'<figure><figcaption>{_esc(bench_name)}</figcaption>',
             f'<svg viewBox="0 0 {PLOT_W} {PLOT_H}" width="100%" '
             f'role="img" aria-label="score against cost for {_esc(bench_name)}">']
    # axes and gridlines, four steps each way
    for i in range(5):
        gy = PLOT_PAD["t"] + ih * i / 4
        value = smax - (smax - smin) * i / 4
        parts.append(f'<line x1="{PLOT_PAD["l"]}" y1="{gy:.1f}" x2="{PLOT_W - PLOT_PAD["r"]}" '
                     f'y2="{gy:.1f}" stroke="#ddd" />')
        parts.append(f'<text x="{PLOT_PAD["l"] - 6}" y="{gy + 4:.1f}" font-size="10" '
                     f'text-anchor="end" fill="#555">{value:.3g}</text>')
        gx = PLOT_PAD["l"] + iw * i / 4
        cvalue = cmin + (cmax - cmin) * i / 4
        parts.append(f'<text x="{gx:.1f}" y="{PLOT_H - PLOT_PAD["b"] + 16}" font-size="10" '
                     f'text-anchor="middle" fill="#555">{cvalue:.3g}</text>')
    parts.append(f'<text x="{PLOT_PAD["l"] + iw / 2:.1f}" y="{PLOT_H - 6}" font-size="11" '
                 f'text-anchor="middle" fill="#333">cost ($, lower is better)</text>')
    parts.append(f'<text x="12" y="{PLOT_PAD["t"] + ih / 2:.1f}" font-size="11" fill="#333" '
                 f'transform="rotate(-90 12 {PLOT_PAD["t"] + ih / 2:.1f})" '
                 f'text-anchor="middle">score</text>')

    for index, model in enumerate(sorted(series)):
        colour = SERIES_COLOURS[index % len(SERIES_COLOURS)]
        pts = sorted(series[model])
        if len(pts) > 1:
            path = " ".join(f"{x(c):.1f},{y(sc):.1f}" for c, sc, _ in pts)
            parts.append(f'<polyline points="{path}" fill="none" stroke="{colour}" '
                         f'stroke-width="1" opacity="0.5" />')
        for c, sc, effort in pts:
            parts.append(f'<circle cx="{x(c):.1f}" cy="{y(sc):.1f}" r="3.5" fill="{colour}">'
                         f'<title>{_esc(model)} {_esc(effort)}: score {sc:g}, cost {c:g}</title>'
                         f'</circle>')
            parts.append(f'<text x="{x(c) + 6:.1f}" y="{y(sc) - 5:.1f}" font-size="9" '
                         f'fill="{colour}">{_esc(effort)}</text>')
    parts.append("</svg>")
    legend = " ".join(
        f'<span class="key"><i style="background:{SERIES_COLOURS[i % len(SERIES_COLOURS)]}"></i>'
        f'{_esc(m)}</span>' for i, m in enumerate(sorted(series)))
    parts.append(f'<div class="legend">{legend}</div></figure>')
    return parts

def render(bench, lanes_doc, effort_rows=None):
    """Return a self-contained HTML document. No network resources."""
    chunks = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        "<title>Delegate benchmark data</title>",
        "<style>",
        "body { font-family: Menlo, Consolas, monospace; font-size: 13px;",
        "  max-width: 46rem; margin: 1rem auto; padding: 0 0.8rem;",
        "  color: #111; background: #f7f7f5; }",
        "h1 { font-size: 1.15rem; margin: 0 0 0.4rem; }",
        "h2 { font-size: 1rem; margin: 1.2rem 0 0.4rem; }",
        "p { margin: 0.4rem 0; }",
        "table { border-collapse: collapse; width: 100%; margin: 0.4rem 0 0.8rem; }",
        "th, td { border: 1px solid #bbb; padding: 0.2rem 0.35rem; text-align: left;",
        "  vertical-align: top; word-break: break-word; }",
        "th { background: #ecece8; }",
        "caption { text-align: left; font-weight: bold; margin: 0 0 0.25rem; }",
        "tr.uncertain { background: #f3e6c2; }",
        ".missing { border: 1px dashed #888; padding: 0.5rem; background: #fff; }",
        "ul { padding-left: 1.2rem; }",
        "figure { margin: 0.4rem 0 1rem; }",
        "figcaption { font-weight: bold; margin: 0 0 0.2rem; }",
        "svg { background: #fff; border: 1px solid #ddd; }",
        ".legend { margin-top: 0.3rem; font-size: 11px; }",
        ".legend .key { margin-right: 0.8rem; white-space: nowrap; }",
        ".legend i { display: inline-block; width: 9px; height: 9px;",
        "  margin-right: 0.25rem; vertical-align: baseline; }",
        "</style>",
        "</head>",
        "<body>",
        "<h1>Delegate benchmark data</h1>",
        "<p>Read-only view of data already gathered. Tiers are set in the TUI; nothing is entered here.</p>",
    ]
    chunks.extend(_lanes_section(lanes_doc))
    if bench is None:
        chunks.append(_missing("Benchmark collection"))
    else:
        chunks.extend(_epoch_section(bench))
        chunks.extend(_aa_section(bench))
        chunks.extend(_notes_section(bench))
    chunks.extend(_plot_section(effort_rows))
    chunks.extend(_effort_section(effort_rows))
    chunks.extend(["</body>", "</html>", ""])
    return "\n".join(chunks)


def write(path, bench, lanes_doc, effort_rows=None):
    """Write the rendered page to path and return path."""
    text = render(bench, lanes_doc, effort_rows)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path
