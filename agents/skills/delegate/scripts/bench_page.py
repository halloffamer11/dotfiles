#!/usr/bin/env python3
"""Read-only HTML view of gathered benchmark data for the setup wizard.

One person opens this from the tier screens, once every few months, to decide
which paid lanes to carry and what tier each deserves. The page has to answer
at a glance: which model is better, whether a dearer effort level is buying
anything, and what the pre-screen is about to switch off. So the chart comes
first and everything else is the evidence behind it.

Self-contained: inline CSS and inline SVG, no script, no remote resource. It
is opened as a file:// URL and may be read with the network off.
"""
import html
import json
import math
import os
from collections import defaultdict

from catalog import EFFORTS, resolve_published_model
from setup_tui import certain_effort_rows, dominating_row, propose_enabled

# A published sweep runs the API's own enum, which starts below the lowest
# effort a lane can be set to. `none` is a real row and the cheapest one, so a
# model's sweep is drawn from it; the pre-screen still never lets it dominate.
EFFORT_ORDER = ("none",) + EFFORTS

NO_LANE = "no lane"

# Provenance the page must not let look like a verified figure. `uncertain`
# rows are excluded from the pre-screen's rule; `self-reported` rows are not,
# which is why both are drawn the same way and the legend says so.
WEAK_PROVENANCE = ("self-reported",)

SOURCES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "assets", "sources.json")

# The four kinds of point on a chart. A lane is a thing the reader pays for
# and can dispatch to; the rest is context, and the distinction has to survive
# at a glance, so each kind has its own shape and fill, not just a colour.
LANE, LANE_OFF, OWN_OTHER, COMPARATOR = "lane", "lane_off", "own_other", "comparator"
KIND_WORDS = {
    LANE: "a lane you carry, at the effort it runs",
    LANE_OFF: "a lane you carry that the pre-screen proposes to switch off",
    OWN_OTHER: "a model you carry, at an effort no lane runs",
    COMPARATOR: "a model no lane runs, for comparison",
}


# --- small formatting helpers ------------------------------------------------

def _esc(value):
    if value is None:
        return "—"
    return html.escape(str(value), quote=True)


def _num(value):
    """A real number or None; bools are not numbers here."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return float(value)


def _fmt_score(score, unit=None):
    if score is None:
        return "—"
    text = f"{score:.1f}"
    return text + "%" if unit == "%" else text


def _fmt_delta(delta, unit=None):
    if delta is None:
        return "—"
    if abs(delta) < 0.05:
        return "0.0" + ("%" if unit == "%" else "")
    sign = "+" if delta > 0 else "−"
    return f"{sign}{abs(delta):.1f}" + ("%" if unit == "%" else "")


def _fmt_money(value):
    """$2,269 above a hundred, $19.1 above ten, $2.9 below: the precision a
    reader can use at each size, and never `1.56e+03`."""
    value = _num(value)
    if value is None:
        return "—"
    if abs(value) >= 100:
        return f"${value:,.0f}"
    if abs(value) >= 10:
        return f"${value:.1f}"
    return f"${value:.2f}".rstrip("0").rstrip(".")


def _fmt_money_delta(delta):
    if delta is None:
        return "—"
    if abs(delta) < 0.005:
        return "$0"
    sign = "+" if delta > 0 else "−"
    return sign + _fmt_money(abs(delta))


def _fmt_pct_change(old, new):
    if not old:
        return ""
    change = (new - old) / old * 100
    if abs(change) < 0.5:
        return "(same)"
    sign = "+" if change > 0 else "−"
    return f"({sign}{abs(change):.0f}%)"


def _effort_key(effort):
    try:
        return (EFFORT_ORDER.index(effort), effort)
    except ValueError:
        return (len(EFFORT_ORDER), str(effort))


def _short_model(published, lane_model):
    """The name a point wears. Our models wear the slug the wizard shows;
    a comparator wears the name the source printed."""
    return lane_model or published or "?"


# --- reading the catalog -----------------------------------------------------

def _lanes(lanes_doc):
    lanes = (lanes_doc or {}).get("lanes") or {}
    return {name: lane for name, lane in lanes.items() if isinstance(lane, dict)}


def _lane_at(lanes_doc, model, effort):
    """The lane names running this model at this effort, sorted."""
    return sorted(name for name, lane in _lanes(lanes_doc).items()
                  if lane.get("model") == model and lane.get("effort") == effort)


def _lanes_of_model(lanes_doc, model):
    return sorted(name for name, lane in _lanes(lanes_doc).items()
                  if lane.get("model") == model)


def _proposals(lanes_doc, effort_rows):
    """The wizard's own pre-screen verdicts, so the page marks exactly what
    the wizard marks. Two implementations of one rule would eventually
    disagree in front of the person checking the arithmetic."""
    if not _lanes(lanes_doc) or effort_rows is None:
        return {}
    try:
        return propose_enabled(lanes_doc, effort_rows)
    except Exception:
        return {}


def _proposed_off(proposals):
    """{lane name: reason} for lanes the pre-screen would switch off on the
    strength of the data, not lanes already recorded off or never carried."""
    return {name: why for name, (on, why) in proposals.items()
            if not on and isinstance(why, str) and why.startswith("dominated by")}


def _load_sources():
    try:
        with open(SOURCES_PATH, encoding="utf-8") as f:
            doc = json.load(f)
        return doc.get("sources") or {}
    except (OSError, ValueError):
        return {}


def _cost_basis(source_meta):
    """What a dollar on this source's axis is. Costs are not comparable
    across sources, so every chart says what its own cost is."""
    cost = (source_meta or {}).get("cost") or ""
    if cost == "usd_per_task":
        return "cost per task"
    if cost:
        return "cost of the whole run"
    return "cost as published"


# --- annotating rows ---------------------------------------------------------

def _annotate(effort_rows, lanes_doc, proposals):
    """Every row, with the lane model its printed name denotes, the kind of
    point it makes, the lane it belongs to (if one runs that model at that
    effort), whether its provenance is weak, and which effort dominates it."""
    off = _proposed_off(proposals)
    annotated = []
    for row in effort_rows or []:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        published = row.get("model")
        lane_model = resolve_published_model(published, lanes_doc) if lanes_doc else None
        item["_lane_model"] = lane_model
        item["_model_lanes"] = _lanes_of_model(lanes_doc, lane_model) if lane_model else []
        item["_lanes"] = _lane_at(lanes_doc, lane_model, row.get("effort")) if lane_model else []
        item["_weak"] = bool(row.get("uncertain")) or row.get("provenance") in WEAK_PROVENANCE
        item["_score"] = _num(row.get("score"))
        item["_cost"] = _num(row.get("cost_usd"))
        if item["_lanes"]:
            item["_kind"] = LANE_OFF if any(name in off for name in item["_lanes"]) else LANE
        elif lane_model:
            item["_kind"] = OWN_OTHER
        else:
            item["_kind"] = COMPARATOR
        item["_off_reason"] = next((off[n] for n in item["_lanes"] if n in off), None)
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


def _model_key(item):
    return item["_lane_model"] or item.get("model") or "?"


def _group_by_model(items):
    groups = defaultdict(list)
    for item in items:
        groups[_model_key(item)].append(item)
    for rows in groups.values():
        rows.sort(key=lambda r: _effort_key(r.get("effort")))
    return groups


def _ordered_models(groups):
    """Our models first, then comparators, each by best score, high first."""
    def key(model):
        rows = groups[model]
        ours = any(r["_lane_model"] for r in rows)
        best = max((r["_score"] for r in rows if r["_score"] is not None), default=-1.0)
        return (0 if ours else 1, -best, model)
    return sorted(groups, key=key)


# --- the chart ---------------------------------------------------------------

CHART_W, CHART_H = 760, 400
PAD = {"l": 56, "r": 24, "t": 22, "b": 52}
R_LANE, R_OTHER = 6.0, 5.0
LABEL_PX = 6.3            # width of one character at the label size, roughly
LABEL_H = 12
# The panel ground, painted inside the SVG rather than left to the CSS
# `background`, which is not part of the document: it goes when the plot is
# saved out on its own or printed with background graphics off, and a hollow
# marker's interior is that ground showing through. A CSS variable keeps it
# theme-aware in the page; the fallback keeps it legible out of it.
GROUND = "var(--surface, #ffffff)"
ACCENT = "var(--accent, #2a78d6)"
OFF = "var(--off, #d03b3b)"
MUTED = "var(--muted, #898781)"


def _log_ticks(lo, hi):
    """Every 1-2-5 value inside [lo, hi], the ticks a person reads on a
    dollar axis spanning a hundredfold."""
    ticks = []
    e = math.floor(math.log10(lo)) - 1
    while 10 ** e <= hi:
        for m in (1, 2, 5):
            v = m * 10 ** e
            if lo <= v <= hi:
                ticks.append(v)
        e += 1
    return ticks


def _log_domain(values):
    """A round bound just outside the data on each side. The bounds use finer
    mantissas than the ticks so a board ending at $9,604 is not drawn to
    $20,000 with a third of the axis empty."""
    lo, hi = min(values), max(values)
    lo_bound = hi_bound = None
    e = math.floor(math.log10(lo)) - 1
    while 10 ** e <= hi * 10:
        for m in (1, 1.5, 2, 3, 4, 5, 6, 8):
            v = m * 10 ** e
            if v <= lo * 0.92:
                lo_bound = v
            if v >= hi * 1.08 and hi_bound is None:
                hi_bound = v
        e += 1
    return lo_bound or lo * 0.8, hi_bound or hi * 1.25


def _lin_domain(values):
    top = max(values)
    if top <= 0:
        return 0.0, 1.0, 0.2
    step = 10.0 if top > 40 else (5.0 if top > 20 else 2.0)
    hi = math.ceil(top * 1.06 / step) * step
    return 0.0, hi, step


def _tick_money(value):
    if value >= 1000:
        return f"${value:,.0f}"
    if value >= 1:
        return f"${value:g}"
    return f"${value:.2f}".rstrip("0").rstrip(".")


def _boxes_clear(placed, box):
    x0, y0, x1, y1 = box
    return not any(x0 < px1 and px0 < x1 and y0 < py1 and py0 < y1
                   for px0, py0, px1, py1 in placed)


def _place(text, cx, cy, placed, frame, width_px=LABEL_PX, prefer=None):
    """A label beside its point that lands on no other label and no point.
    Returns (x, y, anchor, fitted): fitted is False when no slot was clear and
    the label took the first one anyway; the tests measure the geometry."""
    width, height = len(text) * width_px + 3, LABEL_H
    fx0, fy0, fx1, fy1 = frame
    slots = [(9, 4, "start"), (-9, 4, "end"), (9, -8, "start"), (-9, -8, "end"),
             (9, 15, "start"), (-9, 15, "end"), (0, -11, "middle"), (0, 19, "middle")]
    if prefer:
        slots = [s for s in slots if s[2] == prefer] + [s for s in slots if s[2] != prefer]
    for dx, dy, anchor in slots:
        x, y = cx + dx, cy + dy
        x0 = x if anchor == "start" else (x - width if anchor == "end" else x - width / 2)
        box = (x0, y - height + 3, x0 + width, y + 3)
        if box[0] < fx0 or box[2] > fx1 or box[1] < fy0 or box[3] > fy1:
            continue
        if _boxes_clear(placed, box):
            placed.append(box)
            return x, y, anchor, True
    x0 = cx + 9
    placed.append((x0, cy - height + 7, x0 + width, cy + 7))
    return x0, cy + 4, "start", False


def _marker(kind, weak, cx, cy):
    """The mark for one point. Shape and fill carry the kind; a dashed
    outline carries weak provenance; hue is the third cue, never the only one."""
    dash = ' stroke-dasharray="2.5 2"' if weak else ""
    if kind == COMPARATOR:
        r = R_OTHER + 1
        d = f"M{cx:.1f},{cy - r:.1f} L{cx + r:.1f},{cy:.1f} L{cx:.1f},{cy + r:.1f} L{cx - r:.1f},{cy:.1f} Z"
        return (f'<path d="{d}" fill="{GROUND}" stroke="{MUTED}" stroke-width="2"{dash} />')
    if kind == OWN_OTHER or weak:
        return (f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{R_OTHER}" fill="{GROUND}" '
                f'stroke="{ACCENT if kind != LANE_OFF else OFF}" stroke-width="2"{dash} />')
    if kind == LANE_OFF:
        k = 3.2
        return (f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{R_LANE + 0.5}" fill="{OFF}" '
                f'stroke="{GROUND}" stroke-width="2" />'
                f'<path d="M{cx - k:.1f},{cy - k:.1f} L{cx + k:.1f},{cy + k:.1f} '
                f'M{cx - k:.1f},{cy + k:.1f} L{cx + k:.1f},{cy - k:.1f}" '
                f'stroke="{GROUND}" stroke-width="2" stroke-linecap="round" />')
    return (f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{R_LANE}" fill="{ACCENT}" '
            f'stroke="{GROUND}" stroke-width="2" />')


def _legend_glyph(kind, weak=False):
    """The same marker at legend size, in a 16x16 box."""
    return (f'<svg class="key" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">'
            f'{_marker(kind, weak, 8, 8)}</svg>')


def _chart(source, benchmark, items, source_meta):
    """One chart per source and benchmark: the only scope on which two costs
    are the same kind of dollar. Score up, cost right on a log axis, one
    model's efforts joined cheapest to dearest. A point up and to the left of
    another dominates it, and a segment that runs flat or down to the right
    is money buying nothing — the picture the pre-screen acts on."""
    plotted = [r for r in items if r["_score"] is not None and r["_cost"] is not None and r["_cost"] > 0]
    unplotted = [r for r in items if r not in plotted]
    groups = _group_by_model(plotted)
    order = _ordered_models(groups)
    unit = next((r.get("score_unit") for r in items if r.get("score_unit")), None)
    basis = _cost_basis(source_meta)
    observed = sorted({r.get("observed") for r in items if r.get("observed")})
    when = (observed[0] if len(observed) == 1 else f"{observed[0]} to {observed[-1]}") if observed else "date not stated"
    url = source_meta.get("url") if source_meta else None
    url = url or next((r.get("url") for r in items if r.get("url")), None)
    parts = ['<section class="board">',
             f'<h2>{_esc(benchmark)}</h2>',
             '<p class="meta">'
             + (f'<a href="{_esc(url)}">{_esc(source)}</a>' if url else _esc(source))
             + f", {_esc(basis)}, observed {_esc(when)}. "
             f"{len(items)} rows, {len(groups)} models.</p>"]

    if not plotted:
        parts.append('<p class="missing">No row on this board carries both a score and a '
                     "positive cost, so there is nothing to draw. The rows are in the table "
                     "below.</p>")
        parts.append(_sweep_table(items, unit))
        parts.append("</section>")
        return parts

    xs = [r["_cost"] for r in plotted]
    ys = [r["_score"] for r in plotted]
    xlo, xhi = _log_domain(xs)
    ylo, yhi, ystep = _lin_domain(ys)
    iw = CHART_W - PAD["l"] - PAD["r"]
    ih = CHART_H - PAD["t"] - PAD["b"]
    lxlo, lxhi = math.log10(xlo), math.log10(xhi)

    def x(c):
        return PAD["l"] + (math.log10(c) - lxlo) / (lxhi - lxlo) * iw

    def y(s):
        return PAD["t"] + ih - (s - ylo) / (yhi - ylo) * ih

    off_points = [r for r in plotted if r["_kind"] == LANE_OFF]
    finding = _finding(groups, order, off_points, unit)
    svg = [f'<svg viewBox="0 0 {CHART_W} {CHART_H}" width="100%" role="img" '
           f'aria-label="Score against {_esc(basis)} on {_esc(benchmark)} from {_esc(source)}: '
           f'{len(plotted)} points across {len(groups)} models. {_esc(finding)} '
           'The numbers are in the table that follows.">',
           f'<rect x="0" y="0" width="{CHART_W}" height="{CHART_H}" fill="{GROUND}" />']
    # gridlines and ticks: hairline, solid, recessive
    v = ylo
    while v <= yhi + 1e-9:
        gy = y(v)
        svg.append(f'<line x1="{PAD["l"]}" y1="{gy:.1f}" x2="{CHART_W - PAD["r"]}" y2="{gy:.1f}" class="grid" />')
        svg.append(f'<text x="{PAD["l"] - 8}" y="{gy + 3.5:.1f}" class="tick" text-anchor="end">'
                   f'{v:g}{"%" if unit == "%" else ""}</text>')
        v += ystep
    for t in _log_ticks(xlo, xhi):
        gx = x(t)
        svg.append(f'<line x1="{gx:.1f}" y1="{PAD["t"]}" x2="{gx:.1f}" y2="{CHART_H - PAD["b"]}" class="grid" />')
        svg.append(f'<text x="{gx:.1f}" y="{CHART_H - PAD["b"] + 16}" class="tick" '
                   f'text-anchor="middle">{_tick_money(t)}</text>')
    svg.append(f'<line x1="{PAD["l"]}" y1="{CHART_H - PAD["b"]}" x2="{CHART_W - PAD["r"]}" '
               f'y2="{CHART_H - PAD["b"]}" class="axis" />')
    svg.append(f'<text x="{PAD["l"] + iw / 2:.1f}" y="{CHART_H - 12}" class="axis-title" '
               f'text-anchor="middle">{_esc(basis)}, dollars, log scale. Left is cheaper.</text>')
    svg.append(f'<text x="14" y="{PAD["t"] + ih / 2:.1f}" class="axis-title" '
               f'transform="rotate(-90 14 {PAD["t"] + ih / 2:.1f})" text-anchor="middle">'
               f'score{", percent" if unit == "%" else ""}. Up is better.</text>')

    # sweeps first, so every marker sits on top of every line
    for model in order:
        rows = groups[model]
        if len(rows) < 2:
            continue
        ours = bool(rows[0]["_lane_model"])
        path = " ".join(f"{x(r['_cost']):.1f},{y(r['_score']):.1f}" for r in rows)
        svg.append(f'<polyline points="{path}" fill="none" '
                   f'stroke="{ACCENT if ours else MUTED}" stroke-width="1.5" '
                   f'stroke-linejoin="round" opacity="{0.55 if ours else 0.45}" />')

    placed = []
    frame = (2, 2, CHART_W - 2, CHART_H - PAD["b"] + 6)
    for r in plotted:
        cx, cy = x(r["_cost"]), y(r["_score"])
        placed.append((cx - 8, cy - 8, cx + 8, cy + 8))
    points_markup = []
    labels_markup = []
    for model in order:
        rows = groups[model]
        sweep = len(rows) > 1
        # the model's name goes once, beside its best point; the efforts go
        # beside each point. A single point wears both in one label.
        best = max(rows, key=lambda r: (r["_score"], -r["_cost"]))
        for r in rows:
            cx, cy = x(r["_cost"]), y(r["_score"])
            kind, weak = r["_kind"], r["_weak"]
            effort = r.get("effort") or "?"
            name = _short_model(r.get("model"), r["_lane_model"])
            tip = [f"{name} {effort}: {_fmt_score(r['_score'], unit)} for {_fmt_money(r['_cost'])}"]
            if r["_lanes"]:
                tip.append("lane " + ", ".join(r["_lanes"]))
            elif r["_lane_model"]:
                tip.append("no lane runs this effort")
            else:
                tip.append("no lane runs this model")
            if r["_dominated_by"]:
                tip.append(f"dominated by {r['_dominated_by']}")
            if r["_off_reason"]:
                tip.append("pre-screen proposes off: " + r["_off_reason"])
            if weak:
                tip.append("weak provenance: " + ("uncertain" if r.get("uncertain") else str(r.get("provenance"))))
            tip.append(f"{r.get('source')}, observed {r.get('observed') or 'date not stated'}")
            points_markup.append(
                f'<g class="pt {kind}{" weak" if weak else ""}">'
                f'<title>{_esc("; ".join(tip))}</title>'
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="12" fill="transparent" />'
                + _marker(kind, weak, cx, cy) + "</g>")
            if sweep and not (kind in (LANE, LANE_OFF) or r is rows[0] or r is rows[-1] or r is best):
                # label selectively: the lanes, the two ends and the best
                # point; the rest is in the tooltip and the table, and six
                # efforts a few dollars apart labelled in full read as noise
                continue
            if sweep:
                text = effort + ("?" if weak else "")
                lx, ly, anchor, _fitted = _place(text, cx, cy, placed, frame, prefer="start")
                cls = "effort" + (" off" if kind == LANE_OFF else "")
                labels_markup.append(f'<text x="{lx:.1f}" y="{ly:.1f}" class="{cls}" '
                                     f'text-anchor="{anchor}">{_esc(text)}</text>')
            else:
                text = f"{name} {effort}" + ("?" if weak else "")
                lx, ly, anchor, _fitted = _place(text, cx, cy, placed, frame, width_px=LABEL_PX + 0.2)
                cls = "name" + (" off" if kind == LANE_OFF else "") + ("" if r["_lane_model"] else " cmp")
                labels_markup.append(f'<text x="{lx:.1f}" y="{ly:.1f}" class="{cls}" '
                                     f'text-anchor="{anchor}">{_esc(text)}</text>')
        if sweep:
            cx, cy = x(best["_cost"]), y(best["_score"])
            text = _short_model(best.get("model"), best["_lane_model"])
            lx, ly, anchor, _fitted = _place(text, cx, cy - 14, placed, frame, width_px=LABEL_PX + 0.6)
            cls = "name" + ("" if best["_lane_model"] else " cmp")
            labels_markup.append(f'<text x="{lx:.1f}" y="{ly:.1f}" class="{cls}" '
                                 f'text-anchor="{anchor}">{_esc(text)}</text>')
    svg.extend(points_markup)
    svg.extend(labels_markup)
    svg.append("</svg>")

    parts.append("<figure>")
    parts.extend(svg)
    parts.append(f"<figcaption>{_esc(finding)}</figcaption>")
    parts.append("</figure>")
    if unplotted:
        names = ", ".join(sorted({f"{_short_model(r.get('model'), r['_lane_model'])} {r.get('effort')}"
                                  for r in unplotted}))
        parts.append(f'<p class="aside">Not drawn, no usable score or cost: {_esc(names)}. '
                     "Their rows are in the table.</p>")
    parts.append(_sweep_table(items, unit))
    parts.append("</section>")
    return parts


def _finding(groups, order, off_points, unit):
    """The sentence a sighted reader takes from the shape, for the caption
    and the image label: the board's top, the best lane you carry, and every
    lane the pre-screen would switch off, with its arithmetic."""
    every = [r for rows in groups.values() for r in rows]
    if not every:
        return "Nothing to compare."
    top = max(every, key=lambda r: (r["_score"], -r["_cost"]))
    sentences = [f"Top of the board: {_short_model(top.get('model'), top['_lane_model'])} "
                 f"{top.get('effort')} at {_fmt_score(top['_score'], unit)} for {_fmt_money(top['_cost'])}."]
    carried = [r for r in every if r["_kind"] in (LANE, LANE_OFF)]
    if carried:
        best = max(carried, key=lambda r: (r["_score"], -r["_cost"]))
        if best is not top:
            sentences.append(f"Best lane you carry: {', '.join(best['_lanes'])} at "
                             f"{_fmt_score(best['_score'], unit)} for {_fmt_money(best['_cost'])}.")
        else:
            sentences.append(f"That is your lane {', '.join(best['_lanes'])}.")
    else:
        sentences.append("No lane you carry is measured on this board at the effort it runs.")
    for r in off_points:
        model = _model_key(r)
        other = next((o for o in groups[model] if o.get("effort") == r["_dominated_by"]), None)
        if other is None:
            sentences.append(f"Proposed off: {', '.join(r['_lanes'])}, {r['_off_reason']}.")
            continue
        ds = r["_score"] - other["_score"]
        dc = r["_cost"] - other["_cost"]
        if abs(ds) < 0.05:
            scores = f"scores the same as {other.get('effort')}"
        else:
            scores = f"scores {_fmt_score(abs(ds), unit)} less than {other.get('effort')}"
        if abs(dc) < 0.005:
            costs = "costs the same"
        else:
            costs = f"costs {_fmt_money(abs(dc))} more {_fmt_pct_change(other['_cost'], r['_cost'])}"
        sentences.append(f"Proposed off: {', '.join(r['_lanes'])}. {r.get('effort')} {scores} and {costs}.")
    return " ".join(sentences)


def _sweep_table(items, unit):
    """The chart as a table: each model's efforts in order, with the step
    from the previous effort, so 'is xhigh worth 44 percent more' is a number."""
    groups = _group_by_model(items)
    order = _ordered_models(groups)
    head = ["model", "effort", "lane", "score", "Δ score", "cost", "Δ cost", "beaten by", "provenance"]
    out = ['<div class="scroll"><table class="sweep">',
           "<thead><tr>" + "".join(
               f'<th{" class=num" if h in ("score", "Δ score", "cost", "Δ cost") else ""}>{_esc(h)}</th>'
               for h in head) + "</tr></thead><tbody>"]
    for model in order:
        rows = groups[model]
        prev = None
        for i, r in enumerate(rows):
            kind, weak = r["_kind"], r["_weak"]
            classes = [kind] + (["weak"] if weak else []) + (["first"] if i == 0 else [])
            if i == 0:
                shown = _short_model(r.get("model"), r["_lane_model"])
                if r["_lane_model"] and r.get("model") != r["_lane_model"]:
                    shown_cell = (f'<td rowspan="{len(rows)}" class="model"><span class="mono">{_esc(shown)}</span>'
                                  f'<span class="sub">published as {_esc(r.get("model"))}</span></td>')
                elif r["_lane_model"]:
                    shown_cell = f'<td rowspan="{len(rows)}" class="model"><span class="mono">{_esc(shown)}</span></td>'
                else:
                    shown_cell = (f'<td rowspan="{len(rows)}" class="model">{_esc(shown)}'
                                  f'<span class="sub">{NO_LANE}</span></td>')
            else:
                shown_cell = ""
            if r["_lanes"]:
                lane_cell = ('<span class="mono">' + ", ".join(_esc(n) for n in r["_lanes"]) + "</span>"
                             + (f'<span class="sub off">off: {_esc(r["_off_reason"])}</span>' if r["_off_reason"] else ""))
            elif r["_lane_model"]:
                lane_cell = '<span class="quiet">not carried</span>'
            else:
                lane_cell = '<span class="quiet">—</span>'
            score, cost = r["_score"], r["_cost"]
            if prev is not None and score is not None and prev["_score"] is not None:
                dscore = _fmt_delta(score - prev["_score"], unit)
            else:
                dscore = "—"
            if prev is not None and cost is not None and prev["_cost"] is not None:
                dcost = _fmt_money_delta(cost - prev["_cost"]) + " " + _fmt_pct_change(prev["_cost"], cost)
            else:
                dcost = "—"
            prov = []
            if r.get("uncertain"):
                prov.append("uncertain")
            if r.get("provenance") and r.get("provenance") != "unlabelled":
                prov.append(str(r.get("provenance")))
            if not prov:
                prov.append("unlabelled")
            out.append(f'<tr class="{" ".join(classes)}">'
                       + shown_cell
                       + f"<td>{_esc(r.get('effort'))}</td>"
                       + f"<td>{lane_cell}</td>"
                       + f'<td class="num">{_esc(_fmt_score(score, unit)) if score is not None else _esc(r.get("score"))}</td>'
                       + f'<td class="num step">{_esc(dscore)}</td>'
                       + f'<td class="num">{_esc(_fmt_money(cost)) if cost is not None else _esc(r.get("cost_usd"))}</td>'
                       + f'<td class="num step">{_esc(dcost)}</td>'
                       + f"<td>{_esc(r['_dominated_by']) if r['_dominated_by'] else ''}</td>"
                       + f'<td class="{"flag" if weak else "quiet"}">{_esc(", ".join(prov))}</td>'
                       + "</tr>")
            prev = r
    out.append("</tbody></table></div>")
    return "\n".join(out)


def _chart_legend():
    keys = [(LANE, False, KIND_WORDS[LANE]),
            (LANE_OFF, False, KIND_WORDS[LANE_OFF]),
            (OWN_OTHER, False, KIND_WORDS[OWN_OTHER]),
            (COMPARATOR, False, KIND_WORDS[COMPARATOR]),
            (OWN_OTHER, True, "dashed: uncertain or self-reported. Uncertain rows never decide "
                              "anything; self-reported rows still count in the pre-screen's rule.")]
    items = "".join(f'<li>{_legend_glyph(k, w)}<span>{_esc(t)}</span></li>' for k, w, t in keys)
    return (f'<ul class="legend">{items}</ul>'
            "<p>A line joins one model's efforts, cheapest to dearest. A point up and to "
            "the left of another beats it: at least the score for no more money. A segment "
            "that runs flat or down to the right is money buying nothing, and that is what "
            "the pre-screen switches a lane off for. Each board has its own cost axis; a "
            "dollar on one board is not a dollar on another.</p>")


def _charts_section(effort_rows, lanes_doc, proposals):
    if effort_rows is None:
        return ["<h2>Score against cost</h2>", _missing("Per-effort")]
    items = _annotate(effort_rows, lanes_doc, proposals)
    if not items:
        return ["<h2>Score against cost</h2>", "<p>No per-effort rows.</p>"]
    sources = _load_sources()
    boards = defaultdict(list)
    for r in items:
        boards[(r.get("source") or "?", r.get("benchmark") or "?")].append(r)

    def board_key(key):
        # the board with the most carried lanes measured at the effort they
        # run comes first: that is where a decision can be made
        rows = boards[key]
        return (-sum(1 for r in rows if r["_kind"] in (LANE, LANE_OFF)),
                -sum(1 for r in rows if r["_lane_model"]), key)

    out = ['<section class="charts">', _chart_legend()]
    for key in sorted(boards, key=board_key):
        source, benchmark = key
        out.extend(_chart(source, benchmark, boards[key], sources.get(source) or {}))
    out.append("</section>")
    return out


# --- the header ----------------------------------------------------------------

def _header(lanes_doc, effort_rows, proposals):
    lanes = _lanes(lanes_doc)
    off = _proposed_off(proposals)
    carried = sum(1 for name, lane in lanes.items() if lane.get("enabled", True) and lane.get("effort") != "ultra")
    out = ["<header>", "<h1>Benchmark evidence for the lane catalog</h1>",
           "<p>Read-only. Tiers are set in the wizard; nothing is entered here. "
           f"{len(lanes)} lanes in the catalog, {carried} carried."
           + (f" {len(effort_rows)} per-effort rows." if effort_rows else "")
           + "</p>"]
    if off:
        names = "; ".join(f'<span class="mono">{_esc(n)}</span>, {_esc(why)}' for n, why in sorted(off.items()))
        out.append(f'<p class="verdict">{_legend_glyph(LANE_OFF)} The pre-screen proposes to '
                   f"switch off {len(off)} lane{'s' if len(off) != 1 else ''}: {names}.</p>")
    elif effort_rows:
        out.append(f'<p class="verdict">{_legend_glyph(LANE)} The pre-screen proposes to switch '
                   "nothing off: no carried lane is beaten by a cheaper effort of its own model.</p>")
    out.append("</header>")
    return out


# --- per-model benchmark scores (bench.collect) -------------------------------

def _effort_of(effort):
    """A stated effort, or None for the source's `unknown` and for a blank."""
    if effort in (None, "", "unknown"):
        return None
    return str(effort)


def _cell_figures(cell):
    """[(effort or None, value)] from one bench cell, in either shape it has
    had: one dict carrying `performance` and `effort` (before the attribution
    fix), or a dict keyed by measured effort with `unknown` a literal key
    (after it, when a model can hold figures at several efforts on one
    benchmark). The effort is part of each figure, never a column."""
    if not isinstance(cell, dict):
        return []
    if "performance" in cell:
        return [(_effort_of(cell.get("effort")), _num(cell.get("performance")))]
    figures = [(_effort_of(effort), _num(fig.get("performance")))
               for effort, fig in cell.items() if isinstance(fig, dict)]
    return sorted(figures, key=lambda f: _effort_key(f[0]) if f[0] else (len(EFFORT_ORDER) + 1, ""))


def _figure_cell(entries, model_lanes, model, column_max):
    """One table cell holding every figure for a model on one column. Each
    figure carries its effort and, when a lane runs the model at that effort,
    that lane in the title and full ink; otherwise grey, with the reason read
    from the catalog. A bar under each number, scaled to the column's largest
    figure, is what lets two models be compared down a column without
    arithmetic now that the mean-rank columns are gone."""
    if not entries:
        return '<td class="num quiet">—</td>'
    parts = []
    for effort, value, shown in entries:
        owners = [n for n, e in model_lanes if e and e == effort]
        width = 0.0 if value is None or not column_max else max(0.0, min(1.0, value / column_max)) * 100
        bar = f'<span class="track"><span class="bar" style="width:{width:.0f}%"></span></span>'
        if owners:
            parts.append(f'<span class="fig attributed" title="{_esc(", ".join(owners))}">'
                         f'{shown}<span class="at">at {_esc(effort)}</span>{bar}</span>')
        elif effort:
            reason = "not carried" if model_lanes else "no lane"
            parts.append(f'<span class="fig unattributed" title="no lane runs {_esc(model)} at {_esc(effort)}">'
                         f'{shown}<span class="at">at {_esc(effort)}, {reason}</span>{bar}</span>')
        else:
            parts.append('<span class="fig unattributed" title="the source did not state the effort">'
                         f'{shown}<span class="at">effort not stated</span>{bar}</span>')
    attributed = any(c.startswith('<span class="fig attributed"') for c in parts)
    return f'<td class="num {"attributed" if attributed else "unattributed"}">' + "".join(parts) + "</td>"


def _scores_section(bench, lanes_doc):
    """Epoch and Artificial Analysis figures, one row per catalog model. A
    figure is attributed to a lane only when it was measured at that lane's
    effort; a figure measured at an effort no lane runs, or at an unstated
    effort, is shown as that model's context and belongs to no lane."""
    epoch_names = bench.get("epoch_benchmarks") or []
    aa_names = bench.get("aa_columns") or []
    models = bench.get("models") or {}
    out = ["<h2>Published scores per model</h2>",
           "<p>Catalog models only, from Epoch AI and Artificial Analysis. Each figure "
           "carries the effort it was measured at. A figure in full ink was measured at an "
           "effort one of your lanes runs, and that lane is named; a figure in grey was "
           "measured at an effort no lane runs, or at an effort the source did not state, "
           "and belongs to no lane. The bar under a figure is its share of the column's "
           "largest, so two models compare down a column. Comparators are not collected "
           "here; they are on the charts above.</p>"]
    if not models:
        return out + [_missing("Epoch benchmark")]
    aa_skipped = bench.get("aa_skipped")
    lanes = _lanes(lanes_doc)

    # gather every figure first, so each column knows its largest value
    table = []
    for model, rec in sorted(models.items()):
        model_lanes = sorted((name, lane.get("effort")) for name, lane in lanes.items()
                             if lane.get("model") == model) or \
            [(name, None) for name in (rec.get("lanes") or [])]
        epoch_cells = (rec.get("epoch") or {}).get("cells") or {}
        row = {"model": model, "lanes": model_lanes, "cols": {}}
        for name in epoch_names:
            row["cols"][("epoch", name)] = [
                (effort, value, f"{value * 100:.1f}" if value is not None else "—")
                for effort, value in _cell_figures(epoch_cells.get(name))]
        if aa_skipped is None:
            aa = rec.get("aa") or {}
            cols = aa.get("cols") or {}
            effort = _effort_of(aa.get("effort"))
            for name in aa_names:
                v = _num(cols.get(name))
                if v is None:
                    row["cols"][("aa", name)] = []
                    continue
                shown = str(int(round(v))) if abs(v - round(v)) < 1e-9 else f"{v:.1f}"
                row["cols"][("aa", name)] = [(effort, v, shown)]
        table.append(row)
    columns = [("epoch", n) for n in epoch_names] + ([("aa", n) for n in aa_names] if aa_skipped is None else [])
    column_max = {}
    for key in columns:
        values = [v for row in table for _e, v, _s in row["cols"].get(key, []) if v is not None]
        column_max[key] = max(values) if values else None

    head = ["model", "lanes", *epoch_names] + (aa_names if aa_skipped is None else [])
    out.append('<div class="scroll"><table class="scores"><thead><tr>')
    out.append("".join(f'<th{" class=num" if i >= 2 else ""}>{_esc(h)}</th>' for i, h in enumerate(head)))
    if aa_skipped is None and aa_names:
        out.append('</tr><tr class="sub"><th></th><th></th>'
                   + f'<th colspan="{len(epoch_names)}">Epoch AI</th>'
                   + f'<th colspan="{len(aa_names)}">Artificial Analysis</th>')
    out.append("</tr></thead><tbody>")
    for row in table:
        lane_cell = "<br>".join(f'<span class="mono">{_esc(name)}</span>' for name, _e in row["lanes"]) or "—"
        cells = [f'<td class="model"><span class="mono">{_esc(row["model"])}</span></td>', f"<td>{lane_cell}</td>"]
        for key in columns:
            cells.append(_figure_cell(row["cols"].get(key, []), row["lanes"], row["model"], column_max[key]))
        out.append("<tr>" + "".join(cells) + "</tr>")
    out.append("</tbody></table></div>")
    if aa_skipped is not None:
        out.append(f'<p class="aside">Artificial Analysis data is missing ({_esc(aa_skipped)}).</p>')
    notes = bench.get("notes") or []
    if notes:
        out.append('<details><summary>Collection notes</summary><ul class="notes">'
                   + "".join(f"<li>{_esc(n)}</li>" for n in notes) + "</ul></details>")
    return out


# --- every row, with its provenance -------------------------------------------

def _rows_section(effort_rows, lanes_doc, proposals):
    if effort_rows is None:
        return []
    items = _annotate(effort_rows, lanes_doc, proposals)
    if not items:
        return []
    items.sort(key=lambda r: (r.get("source") or "", r.get("benchmark") or "",
                              r["_lane_model"] is None, _model_key(r), _effort_key(r.get("effort"))))
    head = ["source", "benchmark", "published as", "lane model", "effort", "score", "cost",
            "observed", "provenance", "note"]
    out = ["<h2>Every row, with its provenance</h2>",
           "<p>Where each number came from. A row that names no lane model is the "
           "board's context; a published name that ought to be one of ours needs a "
           "<span class=\"mono\">published_as</span> entry on its lane. Rows with weak "
           "provenance are flagged.</p>",
           '<div class="scroll"><table class="rows"><thead><tr>'
           + "".join(f'<th{" class=num" if h in ("score", "cost") else ""}>{_esc(h)}</th>' for h in head)
           + "</tr></thead><tbody>"]
    for r in items:
        url = r.get("url")
        src = f'<a href="{_esc(url)}">{_esc(r.get("source"))}</a>' if url else _esc(r.get("source"))
        note = []
        if r.get("uncertain"):
            note.append("uncertain")
        if r["_dominated_by"]:
            note.append(f"beaten by {r['_dominated_by']}")
        if r["_off_reason"]:
            note.append("proposed off")
        unit = r.get("score_unit")
        out.append(f'<tr class="{"weak" if r["_weak"] else ""}{" nolane" if r["_lane_model"] is None else ""}">'
                   f"<td>{src}</td><td>{_esc(r.get('benchmark'))}</td>"
                   f"<td>{_esc(r.get('model'))}</td>"
                   f'<td>{"<span class=mono>" + _esc(r["_lane_model"]) + "</span>" if r["_lane_model"] else NO_LANE}</td>'
                   f"<td>{_esc(r.get('effort'))}</td>"
                   f'<td class="num">{_esc(_fmt_score(r["_score"], unit)) if r["_score"] is not None else _esc(r.get("score"))}</td>'
                   f'<td class="num">{_esc(_fmt_money(r["_cost"])) if r["_cost"] is not None else _esc(r.get("cost_usd"))}</td>'
                   f"<td>{_esc(r.get('observed'))}</td>"
                   f'<td class="{"flag" if r.get("provenance") in WEAK_PROVENANCE else ""}">{_esc(r.get("provenance"))}</td>'
                   f"<td>{_esc(', '.join(note)) if note else ''}</td></tr>")
    out.append("</tbody></table></div>")
    return out


# --- the catalog ---------------------------------------------------------------

def _catalog_section(lanes_doc, proposals):
    lanes = _lanes(lanes_doc)
    if not lanes:
        return []
    meters = (lanes_doc or {}).get("meters") or {}
    head = ["lane", "model", "effort", "tier", "meter", "plan", "pre-screen"]
    out = ["<h2>Catalog lanes</h2>",
           "<p>The incoming catalog, read-only. The last column is the pre-screen's "
           "proposal for each lane; the wizard is where it is accepted or overruled.</p>",
           '<div class="scroll"><table class="catalog"><thead><tr>'
           + "".join(f"<th>{_esc(h)}</th>" for h in head) + "</tr></thead><tbody>"]
    for name in lanes:
        lane = lanes[name]
        meter = meters.get(lane.get("meter")) or {}
        plan = meter.get("plan")
        price = meter.get("price_month")
        plan_cell = f"{_esc(plan)}, ${price}/mo" if plan and price is not None else _esc(plan)
        verdict = proposals.get(name)
        if verdict is None:
            verdict_cell = ('<span class="quiet">recorded off</span>' if lane.get("enabled") is False
                            else '<span class="quiet">—</span>')
        else:
            on, why = verdict
            cls = "" if on else ("off" if why.startswith("dominated by") else "quiet")
            verdict_cell = f'<span class="{cls}">{"carry" if on else "off"}: {_esc(why)}</span>'
        out.append("<tr>"
                   f'<td><span class="mono">{_esc(name)}</span></td>'
                   f'<td><span class="mono">{_esc(lane.get("model"))}</span></td>'
                   f"<td>{_esc(lane.get('effort'))}</td>"
                   f'<td class="num">{_esc(lane.get("tier"))}</td>'
                   f"<td>{_esc(lane.get('meter'))}</td>"
                   f"<td>{plan_cell}</td>"
                   f"<td>{verdict_cell}</td></tr>")
    out.append("</tbody></table></div>")
    return out


def _missing(kind):
    return f'<p class="missing">{_esc(kind)} data is missing.</p>'


# --- style ---------------------------------------------------------------------

STYLE = """
:root { color-scheme: light;
  --page: #f2f3f5; --surface: #ffffff; --ink: #14171c; --ink-2: #4b535e;
  --muted: #7b8290; --grid: #e4e7eb; --rule: #d5d9df; --head: #eceef1;
  --accent: #2a78d6; --off: #d03b3b; --off-ink: #a12727; --flag: #f7edd6; --flag-ink: #6b4d00;
  --sans: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
  --mono: ui-monospace, "SF Mono", Menlo, Consolas, "DejaVu Sans Mono", monospace; }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { color-scheme: dark;
    --page: #121417; --surface: #1a1d21; --ink: #f1f2f4; --ink-2: #b9bfc8;
    --muted: #8a919c; --grid: #2a2f36; --rule: #363c45; --head: #22262c;
    --accent: #3987e5; --off: #d9403f; --off-ink: #f08a8a; --flag: #3a2f12; --flag-ink: #e9c36a; } }
:root[data-theme="dark"] { color-scheme: dark;
  --page: #121417; --surface: #1a1d21; --ink: #f1f2f4; --ink-2: #b9bfc8;
  --muted: #8a919c; --grid: #2a2f36; --rule: #363c45; --head: #22262c;
  --accent: #3987e5; --off: #d9403f; --off-ink: #f08a8a; --flag: #3a2f12; --flag-ink: #e9c36a; }
* { box-sizing: border-box; }
body { font-family: var(--sans); font-size: 14px; line-height: 1.5; color: var(--ink);
  background: var(--page); margin: 0; padding-block: 2rem 4rem; padding-inline: 1.25rem; }
main { max-width: 64rem; margin: 0 auto; }
h1 { font-size: 1.5rem; font-weight: 600; letter-spacing: -0.015em; margin: 0 0 0.35rem; }
h2 { font-size: 1.1rem; font-weight: 600; letter-spacing: -0.01em; margin: 2.4rem 0 0.4rem; }
p { margin: 0.35rem 0; max-width: 46rem; }
a { color: inherit; text-decoration: underline; text-decoration-color: var(--muted); text-underline-offset: 2px; }
a:focus-visible, summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
header p { color: var(--ink-2); }
.verdict { font-size: 1rem; color: var(--ink); margin-top: 0.8rem; max-width: none; }
.verdict .key { vertical-align: -3px; margin-right: 0.35rem; }
.mono { font-family: var(--mono); font-size: 0.93em; }
.meta { color: var(--ink-2); margin-top: -0.2rem; }
.aside, .quiet { color: var(--muted); }
.aside { font-size: 13px; }
.off { color: var(--off-ink); }
.flag { background: var(--flag); color: var(--flag-ink); }
.missing { border: 1px dashed var(--muted); padding: 0.5rem 0.7rem; background: var(--surface); }
.charts { margin-top: 1.6rem; }
.legend { list-style: none; padding: 0; margin: 0.4rem 0 0.2rem; display: flex; flex-wrap: wrap;
  gap: 0.3rem 1.4rem; color: var(--ink-2); font-size: 13px; }
.legend li { display: inline-flex; align-items: flex-start; gap: 0.45rem; max-width: 30rem; }
.legend .key { flex: none; margin-top: 3px; }
.charts > p { color: var(--ink-2); font-size: 13px; }
.board { margin-top: 2rem; }
.board h2 { margin-top: 0; }
figure { margin: 0.8rem 0 0; }
figure svg { display: block; border: 1px solid var(--rule); border-radius: 3px; }
figcaption { margin: 0.6rem 0 0.2rem; font-size: 15px; line-height: 1.45; max-width: 46rem; }
svg text { font-family: var(--sans); fill: var(--ink-2); }
svg .grid { stroke: var(--grid); stroke-width: 1; }
svg .axis { stroke: var(--rule); stroke-width: 1; }
svg text.tick { font-size: 10.5px; fill: var(--muted); font-variant-numeric: tabular-nums; }
svg text.axis-title { font-size: 11px; fill: var(--muted); }
svg text.effort { font-size: 11px; fill: var(--ink); }
svg text.name { font-size: 11px; font-weight: 600; fill: var(--ink); }
svg text.name.cmp { font-weight: 500; fill: var(--ink-2); }
svg text.off { text-decoration: line-through; fill: var(--off-ink); }
svg .pt:hover circle:first-of-type { fill: var(--grid); opacity: 0.6; }
.scroll { overflow-x: auto; margin: 0.6rem 0 0.4rem; }
table { border-collapse: collapse; width: 100%; font-size: 13px; background: var(--surface); }
th, td { padding: 0.32rem 0.55rem; text-align: left; vertical-align: top;
  border-bottom: 1px solid var(--grid); }
th { background: var(--head); font-weight: 600; color: var(--ink-2); white-space: nowrap; }
th.num, td.num { text-align: right; font-variant-numeric: tabular-nums; }
td.model { border-right: 1px solid var(--grid); }
.sub { display: block; font-size: 12px; color: var(--muted); font-family: var(--sans); }
.sweep tr.first td { border-top: 1px solid var(--rule); }
.sweep td.step { color: var(--ink-2); }
.sweep tr.comparator td, .sweep tr.own_other td { color: var(--ink-2); }
.sweep tr.lane td, .sweep tr.lane_off td { color: var(--ink); }
.sweep tr.weak td { border-left: 3px solid var(--flag-ink); }
.scores td.num { min-width: 7rem; }
.scores .fig { display: block; }
.scores .fig + .fig { margin-top: 0.45rem; }
.scores .at { display: block; font-size: 11px; color: var(--muted); font-variant-numeric: normal; font-weight: 400; }
.scores .fig.unattributed { color: var(--muted); }
.scores .fig.attributed { color: var(--ink); font-weight: 600; }
.scores .track { display: block; height: 3px; margin-top: 3px; background: var(--grid); border-radius: 2px; }
.scores .bar { display: block; height: 3px; border-radius: 2px; background: var(--accent); }
.scores .fig.unattributed .bar { background: var(--muted); opacity: 0.55; }
.scores tr.sub th { font-weight: 500; font-size: 12px; text-align: center; }
.rows tr.weak td { border-left: 3px solid var(--flag-ink); }
.rows tr.nolane td { color: var(--ink-2); }
details { margin-top: 0.6rem; color: var(--ink-2); }
summary { cursor: pointer; }
.notes { font-size: 12.5px; padding-left: 1.2rem; }
footer { margin-top: 3rem; color: var(--muted); font-size: 12.5px; }
@media (max-width: 40rem) { body { padding-inline: 1rem; } figcaption { font-size: 14px; } }
""".strip()


def render(bench, lanes_doc, effort_rows=None):
    """Return a self-contained HTML document. No network resources."""
    proposals = _proposals(lanes_doc, effort_rows)
    chunks = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Delegate benchmark evidence</title>",
        "<style>",
        STYLE,
        "</style>",
        "</head>",
        "<body>",
        "<main>",
    ]
    chunks.extend(_header(lanes_doc, effort_rows, proposals))
    chunks.extend(_charts_section(effort_rows, lanes_doc, proposals))
    if bench is None:
        chunks.append("<h2>Published scores per model</h2>")
        chunks.append(_missing("Benchmark collection"))
    else:
        chunks.extend(_scores_section(bench, lanes_doc))
    chunks.extend(_rows_section(effort_rows, lanes_doc, proposals))
    chunks.extend(_catalog_section(lanes_doc, proposals))
    chunks.append("<footer>Epoch AI data is CC-BY 4.0. Artificial Analysis data requires "
                  "attribution. Terminal-Bench scores an agent-model pair, never a model "
                  "alone. Costs are never comparable across sources.</footer>")
    chunks.extend(["</main>", "</body>", "</html>", ""])
    return "\n".join(chunks)


def write(path, bench, lanes_doc, effort_rows=None):
    """Write the rendered page to path and return path."""
    text = render(bench, lanes_doc, effort_rows)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path
