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
    chunks.extend(_effort_section(effort_rows))
    chunks.extend(["</body>", "</html>", ""])
    return "\n".join(chunks)


def write(path, bench, lanes_doc, effort_rows=None):
    """Write the rendered page to path and return path."""
    text = render(bench, lanes_doc, effort_rows)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path
