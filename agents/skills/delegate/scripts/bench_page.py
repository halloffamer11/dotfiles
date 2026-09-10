#!/usr/bin/env python3
"""Read-only HTML view of gathered benchmark data for the setup wizard."""
import html
from collections import defaultdict

from catalog import EFFORTS, resolve_published_model
from setup_tui import certain_effort_rows, dominating_row

# A published sweep runs the API's own enum, which starts below the lowest
# effort a lane can be set to. `none` is therefore a real row and the lowest
# one, and it belongs at that end rather than after `max` — where it landed
# while this file kept its own effort order and that order had no `max` in it.
EFFORT_ORDER = ("none",) + EFFORTS

NO_LANE = "no lane"


def _esc(value):
    if value is None:
        return "—"
    return html.escape(str(value), quote=True)


def _td(value, numeric=False):
    return f'<td class="num">{_esc(value)}</td>' if numeric else f"<td>{_esc(value)}</td>"


def _th(value, numeric=False):
    return f'<th class="num">{_esc(value)}</th>' if numeric else f"<th>{_esc(value)}</th>"


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


def _fmt_money(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return _esc(value)
    return f"{value:,.2f}"


def _tick(value):
    """An axis tick a person reads. `:.3g` turned $1557 into 1.56e+03."""
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if abs(value) >= 100:
        return f"{value:.0f}"
    return f"{value:.3g}"


def _table(headers, rows, caption=None, row_classes=None, numeric=()):
    parts = ['<div class="scroll"><table>']
    if caption:
        parts.append(f"<caption>{_esc(caption)}</caption>")
    parts.append("<thead><tr>"
                 + "".join(_th(h, i in numeric) for i, h in enumerate(headers))
                 + "</tr></thead>")
    parts.append("<tbody>")
    for i, row in enumerate(rows):
        cls = ""
        if row_classes and i < len(row_classes) and row_classes[i]:
            cls = f' class="{html.escape(row_classes[i], quote=True)}"'
        parts.append("<tr" + cls + ">"
                     + "".join(_td(c, j in numeric) for j, c in enumerate(row))
                     + "</tr>")
    parts.append("</tbody></table></div>")
    return "\n".join(parts)


def _missing(kind):
    return f'<p class="missing">{_esc(kind)} data is missing.</p>'


def _lane_efforts(lanes_doc, model):
    """Every effort the catalog runs this model at, lowest first.

    `bench.collect` reports one representative effort per model, which read as
    the whole truth in a column headed `Effort`: five astra lanes at five
    efforts all showed `xhigh`.
    """
    efforts = {lane.get("effort") for lane in ((lanes_doc or {}).get("lanes") or {}).values()
               if isinstance(lane, dict) and lane.get("model") == model}
    ordered = [e for e in EFFORT_ORDER if e in efforts]
    return ", ".join(ordered) or "—"


def _epoch_section(bench, lanes_doc):
    epoch_names = bench.get("epoch_benchmarks") or []
    models = bench.get("models") or {}
    if not models:
        return [_missing("Epoch benchmark")]
    headers = ["Lane(s)", "Model", "Lane effort(s)", *epoch_names, "Epoch mean rank"]
    numeric = set(range(3, 3 + len(epoch_names) + 1))
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
            _lane_efforts(lanes_doc, model) if lanes_doc else (rec.get("lane_effort") or "—"),
            *values,
            epoch.get("mean_s") or "—",
        ])
    return ["<h2>Epoch benchmarks</h2>", _table(headers, rows, numeric=numeric)]


def _aa_section(bench):
    skipped = bench.get("aa_skipped")
    if skipped is not None:
        return [f'<p class="missing">Artificial Analysis data is missing ({_esc(skipped)}).</p>']
    aa_names = bench.get("aa_columns") or []
    models = bench.get("models") or {}
    if not models:
        return [_missing("Artificial Analysis")]
    headers = ["Lane(s)", "Model", *aa_names, "AA mean rank"]
    numeric = set(range(2, 2 + len(aa_names) + 1))
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
    return ["<h2>Artificial Analysis</h2>", _table(headers, rows, numeric=numeric)]


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


def _annotate(effort_rows, lanes_doc):
    """Each row with the lane model its printed name denotes, and whether the
    pre-screen counts it as dominated.

    The page is the evidence for the pre-screen's proposal, and a reader cannot
    join the two by eye while one says `GPT-6 Astra` and the other
    `gpt-6-astra`. So every row carries both names, and the rows naming no lane
    are marked rather than dropped: they are the leaderboard's context, and one
    of them naming no lane is how a missing `published_as` shows itself.
    """
    annotated = []
    for row in effort_rows or []:
        if not isinstance(row, dict):
            continue
        lane_model = resolve_published_model(row.get("model"), lanes_doc)
        item = dict(row)
        item["_lane_model"] = lane_model
        item["_lanes"] = sorted(
            name for name, lane in ((lanes_doc or {}).get("lanes") or {}).items()
            if isinstance(lane, dict) and lane.get("model") == lane_model
        ) if lane_model else []
        annotated.append(item)
    # Domination is judged on the lane model, exactly as the pre-screen judges
    # it, so two printed names for one lane model compare against each other.
    keyed = []
    for item in annotated:
        row = dict(item)
        row["model"] = item["_lane_model"] or item.get("model")
        keyed.append(row)
    certain = certain_effort_rows(keyed)
    comparable = {id(row) for row in certain}
    for item, row in zip(annotated, keyed):
        other = dominating_row(row, certain) if id(row) in comparable else None
        item["_dominated_by"] = other["effort"] if other else None
    return annotated


def _effort_section(effort_rows, lanes_doc):
    if effort_rows is None:
        return [_missing("Per-effort")]
    rows_in = _annotate(effort_rows, lanes_doc)
    if not rows_in:
        return ["<h2>Per-effort scores and cost</h2>", "<p>No per-effort rows.</p>"]
    headers = ["published as", "lane model", "effort", "score", "cost ($)",
               "dominated by", "benchmark", "source", "measured", "provenance", "note"]
    numeric = {3, 4}
    # a lane's own sweep reads as a sweep only if its rows are together and in
    # effort order; grouping by the printed name scattered them by vendor
    rows_in.sort(key=lambda r: (
        r["_lane_model"] is None,
        r["_lane_model"] or "",
        r.get("model") or "",
        _effort_key(r.get("effort")),
        r.get("benchmark") or "",
    ))
    rows, classes = [], []
    for row in rows_in:
        uncertain = bool(row.get("uncertain"))
        classes.append(" ".join(filter(None, [
            "uncertain" if uncertain else "",
            "nolane" if row["_lane_model"] is None else "",
        ])))
        rows.append([
            row.get("model"),
            row["_lane_model"] or NO_LANE,
            row.get("effort"),
            row.get("score"),
            _fmt_money(row.get("cost_usd")),
            row["_dominated_by"] or "",
            row.get("benchmark"),
            row.get("source"),
            row.get("observed"),
            row.get("provenance"),
            "uncertain" if uncertain else "",
        ])
    return ["<h2>Per-effort scores and cost</h2>",
            f'<p class="aside">Rows marked <code>{NO_LANE}</code> are the leaderboard\'s '
            "context: no lane in the catalog runs that model, so the pre-screen ignores "
            "them. A published name that ought to be one of ours needs a "
            "<code>published_as</code> entry on its lane.</p>",
            _table(headers, rows, row_classes=classes, numeric=numeric)]


# Score against cost, one panel per model, one point per effort. This is the
# picture the pre-screen reasons over: a point up and to the LEFT of another
# dominates it — at least the score for no more money. Inline SVG, because the
# page may load no remote script and a table of numbers does not show
# domination at a glance.
#
# One model per panel, not one colour per model. Fourteen models against six
# recycled colours put `Fable 5`, `GPT-6 Astra` and `Opus 5` on the same hue,
# and drew the astra high/xhigh pair — the domination the pre-screen acts on —
# five pixels apart on an axis spanning every model's cost. Domination is only
# ever judged inside one model and one benchmark, so that is the panel, and each
# panel needs no colour to tell anything apart.
PLOT_W, PLOT_H = 620, 260
PLOT_PAD = {"l": 58, "r": 16, "t": 14, "b": 42}
MARK = "#2a78d6"          # categorical slot 1; contrast 4.3:1 on white
# The panel's ground, and therefore the interior of a hollow marker and the ring
# that keeps two solid markers apart: one value used three times, so a hollow
# point is the ground showing through rather than a pale disc drawn on it. It is
# painted inside the SVG and not left to the CSS `background`, which is not part
# of the document — it goes when the plot is saved out on its own, and browsers
# drop it when printing with background graphics off. Either way the encoding
# would come apart exactly where nobody would be watching.
SURFACE = "#ffffff"
GRID = "#e6e6e3"
AXIS_INK = "#52514e"
PAD_FRACTION = 0.08       # so no point is drawn on the frame, nor its label off it


def _plot_section(effort_rows, lanes_doc):
    rows = [r for r in _annotate(effort_rows, lanes_doc) if not r.get("uncertain")]
    points = []
    for row in rows:
        score, cost = row.get("score"), row.get("cost_usd")
        if isinstance(score, bool) or isinstance(cost, bool):
            continue
        if not isinstance(score, (int, float)) or not isinstance(cost, (int, float)):
            continue
        if cost <= 0:
            continue
        points.append(row)
    if not points:
        return ["<h2>Score against cost</h2>",
                "<p>No row carries both a score and a cost, so there is nothing to plot.</p>"]

    panels = defaultdict(list)
    for row in points:
        panels[(row.get("benchmark") or "", row.get("model") or "?")].append(row)
    drawn = {key: rows_ for key, rows_ in panels.items()
             if len({r.get("effort") for r in rows_}) > 1}
    # Two different reasons for having no panel, and one line for both read as
    # if a model nobody runs were merely short of rows.
    plotted = {key[1] for key in drawn}
    lane_of = {row.get("model"): row["_lane_model"] for row in points}
    single = sorted(name for name in {key[1] for key in panels} - plotted if lane_of.get(name))
    no_lane = sorted(name for name in {key[1] for key in panels} - plotted if not lane_of.get(name))

    out = ["<h2>Score against cost</h2>",
           "<p>A point up and to the left of another dominates it: at least the score "
           "for no more money, which is what the pre-screen switches a lane off for. A "
           "hollow point is one the pre-screen counts as dominated. One panel per model "
           "and benchmark, because cost is not comparable across sources and domination "
           "is only ever judged within one model.</p>"]
    for benchmark, model in sorted(drawn):
        out.extend(_svg_plot(benchmark, model, drawn[(benchmark, model)]))
    if single:
        out.append('<p class="aside">A lane runs these, but on one effort only, so there '
                   "is nothing to compare and no panel: "
                   + ", ".join(_esc(name) for name in single)
                   + ". Their rows are in the table below.</p>")
    if no_lane:
        out.append('<p class="aside">No lane runs these, so the pre-screen ignores them '
                   "and no panel is drawn: "
                   + ", ".join(_esc(name) for name in no_lane)
                   + ". Their rows are in the table below, marked "
                   f"<code>{NO_LANE}</code>.</p>")
    return out


def _label_boxes(placed, box):
    x0, y0, x1, y1 = box
    for px0, py0, px1, py1 in placed:
        if x0 < px1 and px0 < x1 and y0 < py1 and py0 < y1:
            return False
    return True


def _place_label(text, cx, cy, placed, frame):
    """Put an effort label beside its point without landing on another one.

    Astra's high and xhigh score the same, so their labels sit at one height a
    few places apart and overprinted each other — on the one pair the whole
    panel exists to show.
    """
    width, height = len(text) * 6.0 + 2, 11
    fx0, fy0, fx1, fy1 = frame
    for dx, dy, anchor in ((8, -7, "start"), (8, 12, "start"),
                           (-8, -7, "end"), (-8, 12, "end")):
        x = cx + dx
        y = cy + dy
        x0 = x if anchor == "start" else x - width
        box = (x0, y - height, x0 + width, y)
        if box[0] < fx0 or box[2] > fx1 or box[1] < fy0 or box[3] > fy1:
            continue
        if _label_boxes(placed, box):
            placed.append(box)
            return x, y, anchor
    placed.append((cx + 8, cy - 18, cx + 8 + width, cy - 7))
    return cx + 8, cy - 7, "start"


def _svg_plot(benchmark, model, rows):
    costs = [float(r["cost_usd"]) for r in rows]
    scores = [float(r["score"]) for r in rows]
    cmin, cmax = min(costs), max(costs)
    smin, smax = min(scores), max(scores)
    cpad = (cmax - cmin) * PAD_FRACTION or max(abs(cmax) * 0.1, 1.0)
    spad = (smax - smin) * PAD_FRACTION or max(abs(smax) * 0.1, 1.0)
    cmin, cmax = cmin - cpad, cmax + cpad
    smin, smax = smin - spad, smax + spad
    iw = PLOT_W - PLOT_PAD["l"] - PLOT_PAD["r"]
    ih = PLOT_H - PLOT_PAD["t"] - PLOT_PAD["b"]

    def x(c):
        return PLOT_PAD["l"] + (c - cmin) / (cmax - cmin) * iw

    def y(sc):
        return PLOT_PAD["t"] + ih - (sc - smin) / (smax - smin) * ih

    lane_model = rows[0].get("_lane_model")
    lanes = rows[0].get("_lanes") or []
    named = f"{_esc(model)} — {_esc(lane_model)}" if lane_model else f"{_esc(model)} — {NO_LANE}"
    # One labelled image, not a maze of thirty announced tick and point labels:
    # every number is in the table below, with a `dominated by` column, so the
    # label's job is to carry the finding a sighted reader takes from the shape.
    beaten = sorted({r.get("effort") for r in rows if r.get("_dominated_by")},
                    key=_effort_key)
    finding = (f", of which {', '.join(_esc(e) for e in beaten)} "
               f"{'is' if len(beaten) == 1 else 'are'} dominated" if beaten
               else ", none of them dominated")
    parts = ["<figure>",
             f'<figcaption><span class="mono">{named}</span> · {_esc(benchmark)}</figcaption>',
             f'<svg viewBox="0 0 {PLOT_W} {PLOT_H}" width="100%" role="img" '
             f'aria-label="score against cost for {_esc(model)} on {_esc(benchmark)}: '
             f'{len(rows)} efforts{finding}. The numbers are in the table below.">',
             f'<rect x="0" y="0" width="{PLOT_W}" height="{PLOT_H}" fill="{SURFACE}" />']
    for i in range(5):
        gy = PLOT_PAD["t"] + ih * i / 4
        value = smax - (smax - smin) * i / 4
        parts.append(f'<line x1="{PLOT_PAD["l"]}" y1="{gy:.1f}" x2="{PLOT_W - PLOT_PAD["r"]}" '
                     f'y2="{gy:.1f}" stroke="{GRID}" stroke-width="1" />')
        parts.append(f'<text x="{PLOT_PAD["l"] - 8}" y="{gy + 3.5:.1f}" class="tick" '
                     f'text-anchor="end">{_tick(value)}</text>')
        gx = PLOT_PAD["l"] + iw * i / 4
        cvalue = cmin + (cmax - cmin) * i / 4
        parts.append(f'<text x="{gx:.1f}" y="{PLOT_H - PLOT_PAD["b"] + 18}" class="tick" '
                     f'text-anchor="middle">{_tick(cvalue)}</text>')
    parts.append(f'<text x="{PLOT_PAD["l"] + iw / 2:.1f}" y="{PLOT_H - 8}" class="axis" '
                 f'text-anchor="middle">cost in dollars, less is better</text>')
    parts.append(f'<text x="14" y="{PLOT_PAD["t"] + ih / 2:.1f}" class="axis" '
                 f'transform="rotate(-90 14 {PLOT_PAD["t"] + ih / 2:.1f})" '
                 f'text-anchor="middle">score</text>')

    ordered = sorted(rows, key=lambda r: float(r["cost_usd"]))
    if len(ordered) > 1:
        path = " ".join(f"{x(float(r['cost_usd'])):.1f},{y(float(r['score'])):.1f}"
                        for r in ordered)
        parts.append(f'<polyline points="{path}" fill="none" stroke="{MARK}" '
                     f'stroke-width="2" opacity="0.35" />')
    placed = []
    frame = (2, 2, PLOT_W - 2, PLOT_H - PLOT_PAD["b"] + 4)
    for row in ordered:
        cx, cy = x(float(row["cost_usd"])), y(float(row["score"]))
        effort = row.get("effort") or "?"
        beaten = row.get("_dominated_by")
        fill, stroke = (SURFACE, MARK) if beaten else (MARK, SURFACE)
        note = (f", dominated by {beaten}" if beaten else "")
        parts.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="2"><title>{_esc(model)} {_esc(effort)}: score '
            f'{float(row["score"]):g}, cost ${_fmt_money(row["cost_usd"])}{note}</title></circle>')
        lx, ly, anchor = _place_label(effort, cx, cy, placed, frame)
        parts.append(f'<text x="{lx:.1f}" y="{ly:.1f}" class="point" '
                     f'text-anchor="{anchor}">{_esc(effort)}</text>')
    parts.append("</svg>")
    if lanes:
        parts.append('<p class="aside">lanes: <span class="mono">'
                     + ", ".join(_esc(name) for name in lanes) + "</span></p>")
    parts.append("</figure>")
    return parts


STYLE = """
:root { color-scheme: light;
  --ink: #1c1c1a; --ink-2: #52514e; --rule: #d8d8d3;
  --surface: #ffffff; --page: #f7f7f5; --head: #ecece8;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  --mono: Menlo, Consolas, "DejaVu Sans Mono", monospace; }
body { font-family: var(--sans); font-size: 14px; line-height: 1.5;
  max-width: 58rem; margin: 1.5rem auto; padding: 0 1rem;
  color: var(--ink); background: var(--page); }
h1 { font-size: 1.3rem; margin: 0 0 0.3rem; letter-spacing: -0.01em; }
h2 { font-size: 1.05rem; margin: 1.6rem 0 0.4rem; letter-spacing: -0.01em; }
p { margin: 0.4rem 0; max-width: 44rem; }
.aside { color: var(--ink-2); font-size: 13px; }
code, .mono { font-family: var(--mono); }
.scroll { overflow-x: auto; margin: 0.5rem 0 1rem; }
table { border-collapse: collapse; width: 100%; font-family: var(--mono);
  font-size: 12.5px; font-variant-numeric: tabular-nums;
  background: var(--surface); }
th, td { border: 1px solid var(--rule); padding: 0.25rem 0.4rem; text-align: left;
  vertical-align: top; word-break: break-word; }
th { background: var(--head); font-weight: 600; }
td.num, th.num { text-align: right; }
caption { text-align: left; font-family: var(--sans); font-weight: 600;
  margin: 0 0 0.3rem; }
tr.uncertain { background: #fbf3dd; }
tr.nolane td { color: var(--ink-2); }
.missing { border: 1px dashed #8a8a84; padding: 0.5rem; background: var(--surface); }
ul { padding-left: 1.2rem; max-width: 44rem; }
li { font-family: var(--mono); font-size: 12.5px; }
figure { margin: 0.8rem 0 1.4rem; }
figcaption { font-weight: 600; margin: 0 0 0.3rem; }
svg { border: 1px solid var(--rule); display: block; }
svg text { font-family: var(--mono); fill: var(--ink-2); }
svg text.tick { font-size: 10px; }
svg text.axis { font-size: 11px; }
svg text.point { font-size: 10px; fill: var(--ink); }
""".strip()


def render(bench, lanes_doc, effort_rows=None):
    """Return a self-contained HTML document. No network resources."""
    chunks = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Delegate benchmark data</title>",
        "<style>",
        STYLE,
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
        chunks.extend(_epoch_section(bench, lanes_doc))
        chunks.extend(_aa_section(bench))
        chunks.extend(_notes_section(bench))
    chunks.extend(_plot_section(effort_rows, lanes_doc))
    chunks.extend(_effort_section(effort_rows, lanes_doc))
    chunks.extend(["</body>", "</html>", ""])
    return "\n".join(chunks)


def write(path, bench, lanes_doc, effort_rows=None):
    """Write the rendered page to path and return path."""
    text = render(bench, lanes_doc, effort_rows)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path
