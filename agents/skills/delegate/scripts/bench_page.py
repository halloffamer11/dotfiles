#!/usr/bin/env python3
"""Read-only HTML view of gathered benchmark data for the setup wizard.

One person opens this from the tier screens, once every few months, to decide
which paid lanes to carry and what tier each deserves. The page has to answer
at a glance: which model is better, whether a dearer effort level is buying
anything, and what the pre-screen is about to switch off. So the plots come
first, each with its own settings, and every table is the evidence behind
them, collapsed until asked for.

Self-contained: inline CSS, one inline script (`assets/bench_page.js`) and the
data it draws as inline JSON; no remote resource. It is opened as a file://
URL and may be read with the network off. Every decision in the data (the
kind of each point, what the pre-screen proposes off, which effort beats
which) is made here, from `bench`; the script only filters
what is shown, finds the frontier of it, and lays it out.
"""
import hashlib
import html
import json
import math
import os
from collections import defaultdict

import bench
from bench import (
    AA_COST_COLUMN,
    KIND_DOMINATED,
    carry_reason,
    certain_effort_rows,
    dominating_row,
    evidence_unavailable,
    fmt_aa_value,
    fmt_cost,
    group_lanes,
    lane_order,
    model_group,
    propose_enabled,
)
from catalog import EFFORTS

# A published sweep runs the API's own enum, which starts below the lowest
# effort a lane can be set to. `none` is a real row and the cheapest one, so a
# model's sweep is drawn from it; the pre-screen still never lets it dominate.
EFFORT_ORDER = ("none",) + EFFORTS

NO_LANE = "no lane"

# Provenance the page must not let look like a verified figure. `uncertain`
# rows are excluded from the pre-screen's rule; `self-reported` rows are not,
# which is why both are drawn the same way and the legend says so.
WEAK_PROVENANCE = ("self-reported",)

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
SOURCES_PATH = bench.SOURCES_PATH
BOARDS_PATH = bench.BOARDS_PATH
SCRIPT_PATH = os.path.join(ASSETS, "bench_page.js")

# Said in place of a description for a board `assets/boards.json` does not
# cover. A description is quoted from the source's own methodology page, never
# written from memory, so a board nobody has fetched a page for says so.
NO_ABOUT = ("No description on file for this board: nobody has fetched its source's "
            "methodology page into assets/boards.json.")
ABOUT_FIELDS = bench.ABOUT_FIELDS

# The four kinds of point on a plot. A lane is a thing the reader pays for
# and can dispatch to; the rest is context, and the distinction has to survive
# at a glance, so each kind has its own shape and fill, not just a colour.
LANE, LANE_OFF, OWN_OTHER, COMPARATOR = "lane", "lane_off", "own_other", "comparator"


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


def _effort_desc(effort):
    """Most effort first, a stranger last: the order every table lists a
    model's efforts in (ticket 26)."""
    try:
        return (0, -EFFORT_ORDER.index(effort), "")
    except ValueError:
        return (1, 0, str(effort))


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
    disagree in front of the person checking the arithmetic.

    Returns {name: carry_decision}. `effort_rows is None` (unavailable evidence)
    is distinct from an empty proposal.
    """
    if not _lanes(lanes_doc):
        return {}
    try:
        return propose_enabled(lanes_doc, effort_rows)
    except Exception:
        return {}


def _proposed_off(proposals):
    """{lane name: display reason} for lanes the pre-screen would switch off on
    the strength of the data, not lanes already recorded off or never carried."""
    return {name: carry_reason(decision) for name, decision in (proposals or {}).items()
            if decision.get("kind") == KIND_DOMINATED}


def _decision_for(proposals, names):
    """The first dominated decision among `names`, else None."""
    for name in names or ():
        decision = (proposals or {}).get(name)
        if decision and decision.get("kind") == KIND_DOMINATED:
            return decision
    return None


def _load_sources():
    return bench.load_sources()


def _load_boards():
    return bench.load_boards()


def board_about(source, benchmark, boards=None):
    """What one board measures, quoted from its source's methodology page."""
    return bench.board_about(source, benchmark, boards=boards)


def _cost_basis(source_meta):
    """What a dollar on this source's axis is. Costs are not comparable
    across sources, so every plot says what its own cost is."""
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
    effort), whether its provenance is weak, and which effort dominates it.

    Identity, standing, cost basis and version come from `bench.evidence_records`
    so the HTML table is the same records model inspection prints.
    """
    off = _proposed_off(proposals)
    annotated = []
    for rec in bench.evidence_records(effort_rows, lanes_doc):
        row = rec.get("row") if isinstance(rec.get("row"), dict) else {}
        item = dict(row)
        lane_model = rec.get("lane_model")
        item["_lane_model"] = lane_model
        item["_model_lanes"] = _lanes_of_model(lanes_doc, lane_model) if lane_model else []
        item["_lanes"] = list(rec.get("lanes") or [])
        item["_weak"] = bool(row.get("uncertain")) or row.get("provenance") in WEAK_PROVENANCE
        item["_score"] = _num(row.get("score"))
        item["_cost"] = _num(row.get("cost_usd"))
        item["_identity"] = rec.get("identity")
        item["_identity_reason"] = rec.get("identity_reason")
        item["_version"] = rec.get("version")
        item["_standing"] = rec.get("standing")
        item["_cost_basis"] = rec.get("cost_basis")
        item["_direction"] = rec.get("direction")
        item["_attributed"] = rec.get("attributed")
        if item["_lanes"]:
            item["_kind"] = LANE_OFF if any(name in off for name in item["_lanes"]) else LANE
        elif lane_model:
            item["_kind"] = OWN_OTHER
        else:
            item["_kind"] = COMPARATOR
        decision = _decision_for(proposals, item["_lanes"])
        item["_off_reason"] = carry_reason(decision) if decision else None
        item["_off_kind"] = decision.get("kind") if decision else None
        item["_off_source"] = decision.get("source") if decision else None
        item["_off_competitor"] = decision.get("competitor") if decision else None
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
        rows.sort(key=lambda r: _effort_desc(r.get("effort")))
    return groups


def _ordered_models(groups):
    """Our models first, then comparators, each by best score, high first."""
    def key(model):
        rows = groups[model]
        ours = any(r["_lane_model"] for r in rows)
        best = max((r["_score"] for r in rows if r["_score"] is not None), default=-1.0)
        return (0 if ours else 1, -best, model)
    return sorted(groups, key=key)


def _plotted(item):
    return item["_score"] is not None and item["_cost"] is not None and item["_cost"] > 0


# --- the header glyphs ---------------------------------------------------------

# The same marks the script draws, for the verdict line, which has to read with
# the script off. A CSS variable keeps each theme-aware; the fallback keeps it
# legible out of the page.
GROUND = "var(--surface, #ffffff)"
ACCENT = "var(--accent, #2b5fc4)"
OFF = "var(--off, #c63d33)"


def _legend_glyph(kind):
    """A lane or a proposed-off lane's mark, in a 16x16 box."""
    if kind == LANE_OFF:
        mark = (f'<circle cx="8" cy="8" r="6.5" fill="{OFF}" stroke="{GROUND}" stroke-width="1.5" />'
                f'<path d="M5,5 L11,11 M5,11 L11,5" stroke="{GROUND}" stroke-width="1.8" '
                'stroke-linecap="round" />')
    else:
        mark = f'<circle cx="8" cy="8" r="6" fill="{ACCENT}" stroke="{GROUND}" stroke-width="1.5" />'
    return (f'<svg class="key" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">'
            f"{mark}</svg>")


# --- what each board says -------------------------------------------------------

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


NOTHING_TO_DRAW = ("No row on this board carries both a score and a positive cost, so there is "
                   "nothing to draw. The rows are in its table.")


def _boards(items):
    """{(source, benchmark): rows}, ordered so the board where a decision can
    be made comes first: most carried lanes measured at the effort they run,
    then a composite index before its components, then most of our models."""
    boards = defaultdict(list)
    for r in items:
        boards[(r.get("source") or "?", r.get("benchmark") or "?")].append(r)

    def board_key(key):
        rows = boards[key]
        return (-sum(1 for r in rows if r["_kind"] in (LANE, LANE_OFF)),
                not any(r.get("composite") for r in rows),
                -sum(1 for r in rows if r["_lane_model"]), key)

    return [(key, boards[key]) for key in sorted(boards, key=board_key)]


def _board_facts(source, benchmark, items, source_meta):
    """What one board is and what it says, shared by the plot's data and its
    table in the evidence section."""
    plotted = [r for r in items if _plotted(r)]
    groups = _group_by_model(plotted)
    unit = next((r.get("score_unit") for r in items if r.get("score_unit")), None)
    observed = sorted({r.get("observed") for r in items if r.get("observed")})
    when = (observed[0] if len(observed) == 1 else f"{observed[0]} to {observed[-1]}") if observed else "date not stated"
    url = (source_meta or {}).get("url") or next((r.get("url") for r in items if r.get("url")), None)
    if plotted:
        off_points = [r for r in plotted if r["_kind"] == LANE_OFF]
        finding = _finding(groups, _ordered_models(groups), off_points, unit)
    else:
        finding = NOTHING_TO_DRAW
    unplotted = sorted({f"{_short_model(r.get('model'), r['_lane_model'])} {r.get('effort')}"
                        for r in items if not _plotted(r)})
    return {"source": source, "benchmark": benchmark,
            "composite": any(bool(r.get("composite")) for r in items),
            "basis": _cost_basis(source_meta), "url": url, "when": when, "unit": unit,
            "finding": finding, "rows": len(items),
            "models": len({_model_key(r) for r in items}), "unplotted": unplotted}


def _point(r, lanes):
    """One row as the script draws it."""
    at = [{"name": n, "harness": lanes[n].get("harness"), "meter": lanes[n].get("meter"),
           "tier": lanes[n].get("tier")}
          for n in r["_lanes"]]
    harness = sorted({lane["harness"] for lane in at if lane["harness"]}) or \
        sorted({lanes[n].get("harness") for n in r["_model_lanes"] if lanes[n].get("harness")})
    # colour is the meter (ticket 27): the lanes' own, else the model's lanes'
    meter = sorted({lane["meter"] for lane in at if lane["meter"]}) or \
        sorted({lanes[n].get("meter") for n in r["_model_lanes"] if lanes[n].get("meter")})
    tiers = [lane["tier"] for lane in at if isinstance(lane["tier"], int)]
    if r.get("uncertain"):
        provenance = "uncertain"
    else:
        provenance = str(r.get("provenance") or "unlabelled")
    return {"model": _model_key(r), "name": _short_model(r.get("model"), r["_lane_model"]),
            "published": r.get("model"), "ours": bool(r["_lane_model"]),
            "effort": r.get("effort") or "?", "score": r["_score"], "cost": r["_cost"],
            "plotted": _plotted(r), "kind": r["_kind"], "weak": r["_weak"], "lanes": at,
            "harness": harness, "meter": meter, "tier": min(tiers) if tiers else None,
            "off": r["_off_reason"], "beatenBy": r["_dominated_by"],
            "carryKind": r.get("_off_kind"), "source": r.get("_off_source"),
            "competitor": r.get("_off_competitor") or r["_dominated_by"],
            "provenance": provenance, "observed": r.get("observed")}


def _carried(lane):
    return lane.get("enabled", True) is not False and lane.get("effort") != "ultra"


def _lane_list(lanes_doc, bench, items, proposals):
    """Every lane the tier panel lists, in the tier pages' order (benchmark
    order, grouped by model, efforts most to least), with what the panel says
    of each: its harness, its group, whether the catalog carries it, the
    pre-screen's reason if it proposes it off, and whether any board draws it
    as a dot. A carried lane with no rows is still a lane that takes a tier,
    so it is listed rather than dropped (ticket 26)."""
    lanes = _lanes(lanes_doc)
    drawn = {name for r in items if _plotted(r) for name in r["_lanes"]}
    off = _proposed_off(proposals)
    out = []
    for name in lane_order({"lanes": lanes}, bench):
        lane = lanes[name]
        decision = (proposals or {}).get(name) or {}
        out.append({"name": name, "harness": lane.get("harness"), "meter": lane.get("meter"),
                    "model": lane.get("model"),
                    "group": model_group(lane), "effort": lane.get("effort"),
                    "tier": lane.get("tier") if isinstance(lane.get("tier"), int) else None,
                    "carried": _carried(lane), "off": off.get(name), "rows": name in drawn,
                    "kind": decision.get("kind"), "source": decision.get("source"),
                    "competitor": decision.get("competitor")})
    return out


def meter_shades(lanes_doc):
    """Every meter the catalog's lanes use, with its harness and a shade of that
    harness's colour: the meter most of the harness's lanes use takes the
    harness colour itself (shade 0), the next shade 1, and so on, ties by name.
    Load balance is across quotas, so colour is the meter (ticket 27), and two
    meters on one harness (`claude-general`, `claude-fable`) read as kin. Listed
    harness by harness, each harness's meters by shade."""
    counts = defaultdict(lambda: defaultdict(int))
    for lane in _lanes(lanes_doc).values():
        if lane.get("harness") and lane.get("meter"):
            counts[lane["harness"]][lane["meter"]] += 1
    out = []
    for harness in sorted(counts):
        ranked = sorted(counts[harness], key=lambda m: (-counts[harness][m], m))
        out += [{"name": m, "harness": harness, "shade": i} for i, m in enumerate(ranked)]
    return out


def catalog_key(lanes_doc):
    """A short key for this catalog's lane names, so the page's own tiers are
    kept apart from another catalog's in the same browser (ticket 26)."""
    names = "\n".join(sorted(_lanes(lanes_doc)))
    return hashlib.sha1(names.encode("utf-8")).hexdigest()[:12]


def plot_data(effort_rows, lanes_doc, proposals=None, bench=None):
    """Everything the plots draw, as one JSON-ready dict: every board with its
    points, the two boards the page opens on, the harnesses and efforts the
    settings offer, and the lanes the tier panel lists."""
    if proposals is None:
        proposals = _proposals(lanes_doc, effort_rows)
    items = _annotate(effort_rows, lanes_doc, proposals)
    sources = _load_sources()
    described = _load_boards()
    lanes = _lanes(lanes_doc)
    boards = []
    for i, ((source, benchmark), rows) in enumerate(_boards(items)):
        board = _board_facts(source, benchmark, rows, sources.get(source) or {})
        board["id"] = f"b{i}"
        board["sourceName"] = (sources.get(source) or {}).get("name") or source
        board["about"] = board_about(source, benchmark, described)
        board["aboutMissing"] = None if board["about"] else NO_ABOUT
        board["points"] = [_point(r, lanes) for r in rows]
        boards.append(board)
    # Two plots to start: the board a decision is made on, and the best board
    # from another source if there is one, else the next board of this one.
    defaults = [b["id"] for b in boards[:1]]
    if boards:
        other = next((b for b in boards if b["source"] != boards[0]["source"]), None)
        other = other or (boards[1] if len(boards) > 1 else None)
        if other:
            defaults.append(other["id"])
    efforts = {r.get("effort") for r in items if r.get("effort")}
    return {"boards": boards, "defaults": defaults,
            "harnesses": sorted({lane.get("harness") for lane in lanes.values() if lane.get("harness")}),
            "meters": meter_shades(lanes_doc),
            "efforts": sorted(efforts, key=_effort_key),
            "lanes": _lane_list(lanes_doc, bench, items, proposals),
            "catalogKey": catalog_key(lanes_doc)}


def _json_for_script(data):
    """JSON that cannot end the script element it sits in, whatever a
    benchmark page printed as a model name."""
    text = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    return text.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")


def _script():
    with open(SCRIPT_PATH, encoding="utf-8") as f:
        text = f.read()
    if "</script" in text.lower():
        raise ValueError(f"{SCRIPT_PATH} must not contain a closing script tag")
    return text


def _plots_section(effort_rows, lanes_doc, proposals, bench=None):
    out = ['<section class="plots">', "<h2>Score against cost</h2>"]
    if effort_rows is None:
        return out + [_missing("Per-effort"), "</section>"]
    data = plot_data(effort_rows, lanes_doc, proposals, bench)
    if not data["boards"]:
        return out + ["<p>No per-effort rows.</p>", "</section>"]
    out += ['<p class="lede">Up is better and left is cheaper. The amber line is the best score '
            "the money buys, and everything in the shade under it is beaten by a point on the "
            "line. Colour is the meter, the quota a lane spends. Each plot is one benchmark from "
            "one source, because a dollar on one board is not a dollar on another. Drag a tier "
            "line to move it; click a dot and press 1 to 4 to give its lane a tier, or o to turn "
            "it off.</p>",
            '<div class="board">',
            '<div class="plot-column">',
            '<div id="plots"></div>',
            '<button id="add-plot" type="button" class="add" hidden>Add a plot</button>',
            '<section id="sensitivity" class="sensitivity" aria-label="Tiers each board alone would give" hidden></section>',
            "</div>",
            '<aside id="tiers" class="tiers" aria-label="Tiers drawn on this page" hidden></aside>',
            "</div>",
            '<noscript><p class="missing">The plots need JavaScript. Every number is in the '
            "tables under “The numbers”.</p></noscript>",
            f'<script type="application/json" id="bench-data">{_json_for_script(data)}</script>',
            "</section>"]
    return out + _comparison_section(data)


def _comparison_section(data):
    """Every board side by side: what it measures, what its number is, and what
    a dollar on its axis is. Open, not collapsed with the evidence: it is the
    key to the plots above it, not a figure to check."""
    boards = data["boards"]
    head = ["board", "source", "what it measures", "scale", "cost basis"]
    out = ['<section class="compare">', "<h2>What each board measures</h2>",
           '<p class="lede">Quoted from each source\'s own methodology page, which is linked. '
           "Costs are never comparable across sources, and two per-task figures measure "
           "different task sets.</p>",
           '<div class="scroll"><table class="compare">',
           "<thead><tr>" + "".join(f"<th>{_esc(h)}</th>" for h in head) + "</tr></thead><tbody>"]
    for board in boards:
        about = board["about"]
        name = _esc(board["benchmark"]) + (' <span class="sub">composite</span>' if board["composite"] else "")
        if about:
            direction = (f'<span class="sub">{_esc(about["direction"])}</span>'
                         if about.get("direction") else "")
            measures = (f'{_esc(about["measures"])}'
                        f'<span class="sub">{_esc(about["tasks"]) if about["tasks"] else ""}</span>'
                        f'<span class="sub">speaks to {_esc(about["speaks_to"])}</span>'
                        f'{direction}'
                        f'<a class="sub" href="{_esc(about["url"])}">{_esc(about["url"])}</a>')
            scale, cost = _esc(about["scale"]), _esc(about["cost"])
        else:
            measures = f'<span class="quiet">{_esc(NO_ABOUT)}</span>'
            scale, cost = "—", _esc(board["basis"])
        out.append(f"<tr><td>{name}</td><td>{_esc(board['sourceName'])}</td>"
                   f'<td class="measures">{measures}</td><td>{scale}</td><td>{cost}</td></tr>')
    out += ["</tbody></table></div>", "</section>"]
    return out


# --- the evidence: every table, collapsed ---------------------------------------

def _sweep_table(items, unit):
    """The plot as a table: each model's efforts from most to least, with
    the step up from the effort below, so 'is xhigh worth 44 percent more' is
    a number on xhigh's own line."""
    groups = _group_by_model(items)
    order = _ordered_models(groups)
    head = ["model", "effort", "lane", "score", "Δ score", "cost", "Δ cost", "beaten by", "provenance"]
    out = ['<div class="scroll"><table class="sweep">',
           "<thead><tr>" + "".join(
               f'<th{" class=num" if h in ("score", "Δ score", "cost", "Δ cost") else ""}>{_esc(h)}</th>'
               for h in head) + "</tr></thead><tbody>"]
    for model in order:
        rows = groups[model]
        for i, r in enumerate(rows):
            # the step is what this effort buys over the one below it
            prev = rows[i + 1] if i + 1 < len(rows) else None
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
    out.append("</tbody></table></div>")
    return "\n".join(out)


def _details(summary, count, body):
    """One collapsed block of the evidence. Closed by default: the tables are
    there to check a figure, not to read."""
    counted = f' <span class="count">{_esc(count)}</span>' if count else ""
    return [f"<details><summary>{summary}{counted}</summary>", '<div class="inner">', *body,
            "</div>", "</details>"]


def _boards_block(effort_rows, lanes_doc, proposals):
    if effort_rows is None:
        return []
    items = _annotate(effort_rows, lanes_doc, proposals)
    if not items:
        return []
    sources = _load_sources()
    body = ["<p>Each model's efforts from most to least, with what each step up from the "
            "effort below costs and buys. A lane's efforts sit in full ink; a comparator is "
            "nobody's lane.</p>"]
    boards = _boards(items)
    for (source, benchmark), rows in boards:
        facts = _board_facts(source, benchmark, rows, sources.get(source) or {})
        src = (f'<a href="{_esc(facts["url"])}">{_esc(source)}</a>' if facts["url"] else _esc(source))
        body += [f'<details class="board"><summary>{_esc(benchmark)} '
                 f'<span class="count">{_esc(source)}, {facts["rows"]} rows</span></summary>',
                 f'<p class="meta">{src}, {_esc(facts["basis"])}, observed {_esc(facts["when"])}.</p>',
                 f'<p class="finding">{_esc(facts["finding"])}</p>']
        if facts["unplotted"] and facts["finding"] != NOTHING_TO_DRAW:
            body.append(f'<p class="aside">Not drawn, no usable score or cost: '
                        f'{_esc(", ".join(facts["unplotted"]))}.</p>')
        unit = next((r.get("score_unit") for r in rows if r.get("score_unit")), None)
        body += [_sweep_table(rows, unit), "</details>"]
    return _details("Each board, model by model", f"{len(boards)} boards", body)


def _rows_block(effort_rows, lanes_doc, proposals):
    if effort_rows is None:
        return []
    items = _annotate(effort_rows, lanes_doc, proposals)
    if not items:
        return []
    items.sort(key=lambda r: (r.get("source") or "", r.get("benchmark") or "",
                              r["_lane_model"] is None, _model_key(r), _effort_desc(r.get("effort"))))
    head = ["source", "benchmark", "version", "published as", "lane model", "effort", "score",
            "cost", "cost basis", "standing", "observed", "provenance", "note"]
    body = ["<p>Where each number came from. A row that names no lane model is the "
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
        if r.get("_identity") == "unresolved" and r.get("_identity_reason"):
            note.append(r["_identity_reason"])
        if r["_dominated_by"]:
            note.append(f"beaten by {r['_dominated_by']}")
        if r["_off_reason"]:
            note.append("proposed off")
        if not r.get("_attributed") and r.get("_lane_model"):
            note.append("not attributed to a lane at this effort")
        unit = r.get("score_unit")
        standing = r.get("_standing") or {}
        if standing.get("rank") is not None:
            tied = " tied" if standing.get("tied") else ""
            standing_cell = (f"{standing['rank']}/{standing.get('n')} "
                             f"{standing.get('direction')}{tied}")
        else:
            standing_cell = f"unknown ({standing.get('direction') or 'unknown'})"
        body.append(f'<tr class="{"weak" if r["_weak"] else ""}{" nolane" if r["_lane_model"] is None else ""}">'
                    f"<td>{src}</td><td>{_esc(r.get('benchmark'))}</td>"
                    f"<td>{_esc(r.get('_version'))}</td>"
                    f"<td>{_esc(r.get('model'))}</td>"
                    f'<td>{"<span class=mono>" + _esc(r["_lane_model"]) + "</span>" if r["_lane_model"] else NO_LANE}</td>'
                    f"<td>{_esc(r.get('effort'))}</td>"
                    f'<td class="num">{_esc(_fmt_score(r["_score"], unit)) if r["_score"] is not None else _esc(r.get("score"))}</td>'
                    f'<td class="num">{_esc(_fmt_money(r["_cost"])) if r["_cost"] is not None else _esc(r.get("cost_usd"))}</td>'
                    f"<td>{_esc(r.get('_cost_basis'))}</td>"
                    f"<td>{_esc(standing_cell)}</td>"
                    f"<td>{_esc(r.get('observed'))}</td>"
                    f'<td class="{"flag" if r.get("provenance") in WEAK_PROVENANCE else ""}">{_esc(r.get("provenance"))}</td>'
                    f"<td>{_esc(', '.join(note)) if note else ''}</td></tr>")
    body.append("</tbody></table></div>")
    return _details("Every row, with its provenance", f"{len(items)} rows", body)


def _catalog_block(lanes_doc, proposals):
    lanes = _lanes(lanes_doc)
    if not lanes:
        return []
    meters = (lanes_doc or {}).get("meters") or {}
    head = ["lane", "model", "effort", "tier", "meter", "plan", "pre-screen"]
    body = ["<p>The incoming catalog, read-only. The last column is the pre-screen's "
            "proposal for each lane; the wizard is where it is accepted or overruled.</p>",
            '<div class="scroll"><table class="catalog"><thead><tr>'
            + "".join(f"<th>{_esc(h)}</th>" for h in head) + "</tr></thead><tbody>"]
    for name in group_lanes(list(lanes), lanes_doc):
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
            on = verdict.get("enabled")
            why = carry_reason(verdict)
            cls = "" if on else ("off" if verdict.get("kind") == KIND_DOMINATED else "quiet")
            verdict_cell = f'<span class="{cls}">{"carry" if on else "off"}: {_esc(why)}</span>'
        body.append("<tr>"
                    f'<td><span class="mono">{_esc(name)}</span></td>'
                    f'<td><span class="mono">{_esc(lane.get("model"))}</span></td>'
                    f"<td>{_esc(lane.get('effort'))}</td>"
                    f'<td class="num">{_esc(lane.get("tier"))}</td>'
                    f"<td>{_esc(lane.get('meter'))}</td>"
                    f"<td>{plan_cell}</td>"
                    f"<td>{verdict_cell}</td></tr>")
    body.append("</tbody></table></div>")
    return _details("Catalog lanes and the pre-screen's proposal", f"{len(lanes)} lanes", body)


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
    # most effort first, an unstated effort last
    return sorted(figures, key=lambda f: _effort_desc(f[0]) if f[0] else (2, 0, ""))


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
        owners = [n for n, e in model_lanes if bench.effort_attributes(effort, e)]
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


def _scores_block(bench, lanes_doc):
    """Epoch and Artificial Analysis figures, one row per catalog model. A
    figure is attributed to a lane only when it was measured at that lane's
    effort; a figure measured at an effort no lane runs, or at an unstated
    effort, is shown as that model's context and belongs to no lane."""
    title = "Published scores per model, from Epoch AI and Artificial Analysis"
    if bench is None:
        return _details(title, "", [_missing("Benchmark collection")])
    epoch_names = bench.get("epoch_benchmarks") or []
    aa_names = bench.get("aa_columns") or []
    models = bench.get("models") or {}
    out = ["<p>Catalog models only. Each figure carries the effort it was measured at. A "
           "figure in full ink was measured at an effort one of your lanes runs, and that "
           "lane is named; a figure in grey was measured at an effort no lane runs, or at an "
           "effort the source did not state, and belongs to no lane. The bar under a figure is "
           "its share of the column's largest, so two models compare down a column. "
           "Comparators are not collected here; they are on the plots above.</p>"]
    if not models:
        return _details(title, "", out + [_missing("Epoch benchmark")])
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
                row["cols"][("aa", name)] = [(effort, v, fmt_aa_value(v))]
            cost = _num(aa.get("cost_usd"))
            row["cols"][("aa", AA_COST_COLUMN)] = [] if cost is None else [(effort, cost, fmt_cost(cost))]
        table.append(row)
    # cost per task sits beside the AA scores when the rows carry it
    aa_shown = list(aa_names)
    if aa_skipped is None and aa_names and any(row["cols"].get(("aa", AA_COST_COLUMN)) for row in table):
        aa_shown.append(AA_COST_COLUMN)
    columns = [("epoch", n) for n in epoch_names] + ([("aa", n) for n in aa_shown] if aa_skipped is None else [])
    column_max = {}
    for key in columns:
        values = [v for row in table for _e, v, _s in row["cols"].get(key, []) if v is not None]
        column_max[key] = max(values) if values else None

    head = ["model", "lanes", *epoch_names] + (aa_shown if aa_skipped is None else [])
    out.append('<div class="scroll"><table class="scores"><thead><tr>')
    out.append("".join(f'<th{" class=num" if i >= 2 else ""}>{_esc(h)}</th>' for i, h in enumerate(head)))
    if aa_skipped is None and aa_names:
        out.append('</tr><tr class="sub"><th></th><th></th>'
                   + f'<th colspan="{len(epoch_names)}">Epoch AI</th>'
                   + f'<th colspan="{len(aa_shown)}">Artificial Analysis</th>')
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
        out.append('<details class="notes-block"><summary>Collection notes</summary><ul class="notes">'
                   + "".join(f"<li>{_esc(n)}</li>" for n in notes) + "</ul></details>")
    return _details(title, f"{len(models)} models", out)


def _missing(kind):
    return f'<p class="missing">{_esc(kind)} data is missing.</p>'


# --- the header ----------------------------------------------------------------

def _header(lanes_doc, effort_rows, proposals):
    lanes = _lanes(lanes_doc)
    off = _proposed_off(proposals)
    carried = sum(1 for name, lane in lanes.items() if lane.get("enabled", True) and lane.get("effort") != "ultra")
    out = ["<header>", "<h1>Benchmark evidence for the lane catalog</h1>",
           "<p>Read-only for the catalog: a tier or an off drawn here stays in this browser, keyed to "
           "this catalog, until you paste it into the wizard, which is the only thing that writes. "
           f"{len(lanes)} lanes in the catalog, {carried} carried."
           + (f" {len(effort_rows)} per-effort rows." if effort_rows else "")
           + "</p>"]
    if off:
        names = "; ".join(f'<span class="mono">{_esc(n)}</span>, {_esc(why)}' for n, why in sorted(off.items()))
        out.append(f'<p class="verdict">{_legend_glyph(LANE_OFF)} The pre-screen proposes to '
                   f"switch off {len(off)} lane{'s' if len(off) != 1 else ''}: {names}.</p>")
    elif evidence_unavailable(effort_rows, proposals):
        out.append(f'<p class="verdict">{_legend_glyph(LANE)} Per-effort evidence is unavailable, '
                   "so the pre-screen proposes nothing.</p>")
    elif effort_rows is not None:
        out.append(f'<p class="verdict">{_legend_glyph(LANE)} The pre-screen proposes to switch '
                   "nothing off: no carried lane is beaten by a cheaper effort of its own model.</p>")
    out.append("</header>")
    return out


# --- style ---------------------------------------------------------------------

STYLE = """
:root { color-scheme: light;
  --page: #eceee9; --surface: #fbfbf8; --ink: #1a1e1c; --ink-2: #4c5450;
  --muted: #7c8480; --grid: #e3e6e0; --rule: #cdd2ca; --head: #f0f2ed;
  --accent: #2b5fc4; --off: #c63d33; --off-ink: #a3291f;
  --frontier: #c27806; --frontier-ink: #7f4d00; --flag: #f6ecd2; --flag-ink: #6b4d00;
  --h-codex: #2b5fc4; --h-claude: #7a4cc2; --h-agy: #13866a; --h-grok: #b3306f;
  --h-codex-1: #173a82; --h-claude-1: #43207e; --h-agy-1: #0a5443; --h-grok-1: #6e1a43;
  --sans: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
  --mono: ui-monospace, "SF Mono", Menlo, Consolas, "DejaVu Sans Mono", monospace; }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { color-scheme: dark;
    --page: #121513; --surface: #1a1e1b; --ink: #edf0ec; --ink-2: #b3bbb5;
    --muted: #848c87; --grid: #272c28; --rule: #363c37; --head: #20241f;
    --accent: #6b95f0; --off: #e2574c; --off-ink: #f39a90;
    --frontier: #f0a53a; --frontier-ink: #f6c47a; --flag: #3a2f12; --flag-ink: #e9c36a;
    --h-codex: #6b95f0; --h-claude: #a784e6; --h-agy: #3cbf98; --h-grok: #e0679f;
    --h-codex-1: #b7cdfa; --h-claude-1: #dccafb; --h-agy-1: #a3e8d2; --h-grok-1: #f4b8d3; } }
:root[data-theme="dark"] { color-scheme: dark;
  --page: #121513; --surface: #1a1e1b; --ink: #edf0ec; --ink-2: #b3bbb5;
  --muted: #848c87; --grid: #272c28; --rule: #363c37; --head: #20241f;
  --accent: #6b95f0; --off: #e2574c; --off-ink: #f39a90;
  --frontier: #f0a53a; --frontier-ink: #f6c47a; --flag: #3a2f12; --flag-ink: #e9c36a;
  --h-codex: #6b95f0; --h-claude: #a784e6; --h-agy: #3cbf98; --h-grok: #e0679f;
  --h-codex-1: #b7cdfa; --h-claude-1: #dccafb; --h-agy-1: #a3e8d2; --h-grok-1: #f4b8d3; }
* { box-sizing: border-box; }
body { font-family: var(--sans); font-size: 14px; line-height: 1.5; color: var(--ink);
  background: var(--page); margin: 0; padding-block: 2rem 4rem; padding-inline: 1.25rem; }
main { max-width: 104rem; margin: 0 auto; }
h1 { font-size: 1.55rem; font-weight: 650; letter-spacing: -0.02em; margin: 0 0 0.35rem; }
h2 { font-size: 1.15rem; font-weight: 650; letter-spacing: -0.01em; margin: 2.4rem 0 0.3rem; }
h3 { font-size: 1rem; font-weight: 650; margin: 1.1rem 0 0.15rem; }
p { margin: 0.35rem 0; max-width: 48rem; }
a { color: inherit; text-decoration: underline; text-decoration-color: var(--muted); text-underline-offset: 2px; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
header p { color: var(--ink-2); }
.verdict { font-size: 1rem; color: var(--ink); margin-top: 0.8rem; max-width: none; }
.verdict .key { vertical-align: -3px; margin-right: 0.35rem; }
.mono { font-family: var(--mono); font-size: 0.93em; }
.meta { color: var(--ink-2); margin: 0.25rem 0 0; }
.aside, .quiet { color: var(--muted); }
.aside { font-size: 13px; }
.off { color: var(--off-ink); }
.flag { background: var(--flag); color: var(--flag-ink); }
.missing { border: 1px dashed var(--muted); padding: 0.5rem 0.7rem; background: var(--surface); }
.lede { color: var(--ink-2); }
.plot { background: var(--surface); border: 1px solid var(--rule); border-radius: 6px;
  padding: 0.9rem 1.1rem 1.1rem; margin-top: 1.1rem; }
.plot-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 0.5rem 1rem; }
.pick { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 0.3rem 0.6rem; color: var(--ink-2); max-width: 100%; }
.pick select { font: inherit; font-size: 1.1rem; font-weight: 650; color: var(--ink); background: var(--surface);
  border: 1px solid var(--rule); border-radius: 4px; padding: 0.25rem 0.45rem; max-width: 100%; }
.finding { font-size: 15px; line-height: 1.45; margin-top: 0.45rem; max-width: 60rem; }
.plot-body { display: grid; grid-template-columns: minmax(0, 1fr) 15.5rem; gap: 1.1rem; margin-top: 0.7rem; align-items: stretch; }
.chart { position: relative; display: flex; flex-direction: column; min-width: 0; }
.plot-canvas { position: relative; flex: 1; min-height: 350px; }
.plot-canvas > svg { position: absolute; display: block; width: 100%; height: 100%; border: 1px solid var(--grid); border-radius: 4px;
  cursor: crosshair; touch-action: none; user-select: none; -webkit-user-select: none; }
.hint { display: flex; flex-wrap: wrap; align-items: center; gap: 0.3rem 0.7rem; font-size: 12.5px;
  color: var(--muted); margin-top: 0.45rem; }
.reset { font: inherit; font-size: 12.5px; padding: 0.2rem 0.65rem; flex: none;
  background: var(--surface); color: var(--ink); border: 1px solid var(--rule); border-radius: 4px; cursor: pointer; }
.reset[aria-disabled="true"] { color: var(--muted); cursor: default; }
.about { margin-top: 0.55rem; padding-left: 0.8rem; border-left: 3px solid var(--rule); max-width: 60rem; }
.about .measures { color: var(--ink); margin: 0; }
.about dl { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 0.1rem 0.8rem;
  margin: 0.35rem 0 0; font-size: 13px; }
.about dt { color: var(--muted); }
.about dd { margin: 0; color: var(--ink-2); }
.about .cite { font-size: 12.5px; color: var(--muted); margin-top: 0.3rem; overflow-wrap: anywhere; }
table.compare td.measures { min-width: 22rem; }
table.compare .sub { overflow-wrap: anywhere; }
.tip { position: absolute; z-index: 2; pointer-events: none; background: var(--surface); color: var(--ink);
  border: 1px solid var(--rule); border-radius: 4px; box-shadow: 0 3px 10px rgba(0, 0, 0, 0.14);
  font-size: 12.5px; line-height: 1.4; padding: 0.45rem 0.6rem; max-width: 21rem; }
.tip .tip-head { font-weight: 650; }
.tip .quiet { color: var(--muted); }
.tip .flag { background: none; }
.rail { display: flex; flex-direction: column; gap: 0.75rem; font-size: 13px; min-width: 0; }
.rail fieldset { border: 0; margin: 0; padding: 0; min-width: 0; }
.rail legend { font-weight: 650; color: var(--ink); padding: 0; margin-bottom: 0.2rem; }
.radios { display: flex; flex-direction: column; }
.radios label, .check { display: flex; align-items: center; gap: 0.4rem; color: var(--ink-2); cursor: pointer; }
.radios input, .check input, .model-row input { margin: 0; accent-color: var(--accent); }
.chips { display: flex; flex-wrap: wrap; gap: 0.3rem; }
.chip { font: inherit; font-size: 12.5px; padding: 0.1rem 0.55rem; border-radius: 999px; cursor: pointer;
  border: 1px solid var(--rule); background: transparent; color: var(--muted); text-decoration: line-through; }
.chip[aria-pressed="true"] { background: var(--ink); border-color: var(--ink); color: var(--surface); text-decoration: none; }
.model-tools input { width: 100%; font: inherit; padding: 0.25rem 0.45rem; color: var(--ink);
  background: var(--surface); border: 1px solid var(--rule); border-radius: 4px; }
.bulk { display: flex; flex-wrap: wrap; gap: 0.2rem 0.8rem; margin: 0.35rem 0 0.25rem; }
.model-list { max-height: 16rem; overflow-y: auto; border: 1px solid var(--grid); border-radius: 4px; padding: 0.1rem 0.45rem 0.3rem; }
.model-list .group { margin: 0.35rem 0 0.05rem; font-size: 12px; color: var(--muted); }
.model-row { display: flex; align-items: center; gap: 0.4rem; cursor: pointer; }
.model-row .nm { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.model-row .tag { font-size: 11.5px; color: var(--muted); }
.quiet-button { font: inherit; font-size: 12.5px; background: none; border: 0; padding: 0; cursor: pointer;
  color: var(--ink-2); text-decoration: underline; text-decoration-color: var(--muted); text-underline-offset: 2px; }
.wide { align-self: flex-start; }
.add { font: inherit; margin-top: 1rem; padding: 0.35rem 0.9rem; cursor: pointer; color: var(--ink);
  background: var(--surface); border: 1px solid var(--rule); border-radius: 4px; }
.plot-legend { display: flex; flex-wrap: wrap; gap: 0.25rem 1.1rem; margin-top: 0.5rem; font-size: 12.5px; color: var(--ink-2); }
.plot-legend .item { display: inline-flex; align-items: center; gap: 0.35rem; }
.plot-legend .note { color: var(--muted); }
.key { flex: none; }
svg text { font-family: var(--sans); fill: var(--ink-2); }
svg .grid { stroke: var(--grid); stroke-width: 1; }
svg .axis { stroke: var(--rule); stroke-width: 1; }
svg text.tick { font-size: 11px; fill: var(--muted); font-variant-numeric: tabular-nums; }
svg text.axis-title { font-size: 11.5px; fill: var(--muted); }
svg text.empty { font-size: 14px; fill: var(--muted); }
svg .wash { fill: var(--frontier); opacity: 0.1; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) svg .wash { opacity: 0.06; } }
:root[data-theme="dark"] svg .wash { opacity: 0.06; }
svg .steps { fill: none; stroke: var(--frontier); stroke-width: 2.4; stroke-linejoin: round; }
svg .halo { fill: none; stroke: var(--frontier); stroke-width: 2; }
svg .sweep { fill: none; stroke: var(--muted); stroke-width: 1.2; opacity: 0.3; }
svg .sweep.ours { stroke: var(--accent); opacity: 0.45; }
svg text.label { font-size: 11.5px; fill: var(--ink); paint-order: stroke; stroke: var(--surface);
  stroke-width: 3px; stroke-linejoin: round; }
svg text.label.cmp { fill: var(--ink-2); }
svg text.label.fr { font-weight: 650; fill: var(--frontier-ink); }
svg text.label.off { text-decoration: line-through; fill: var(--off-ink); }
svg .band { fill: var(--accent); fill-opacity: 0.08; stroke: var(--accent); stroke-dasharray: 3 3; }
svg.focusing .pt, svg.focusing text.label, svg.focusing .sweep { opacity: 0.16; }
svg.focusing .hot { opacity: 1 !important; }
svg.focusing .sweep.hot { stroke-width: 2.2; }
svg .pt.dim, svg text.label.dim { opacity: 0.16; }
svg.panning { cursor: grabbing; }
svg .tier-line { stroke: var(--ink-2); stroke-width: 1; stroke-dasharray: 5 4; }
svg .tier-grip { stroke: transparent; stroke-width: 14; cursor: ns-resize; }
svg .tier-grip:hover + .tier-line, svg .tier-line.held { stroke: var(--ink); stroke-width: 1.6; stroke-dasharray: none; }
svg text.band-name { font-size: 11px; fill: var(--ink-2); paint-order: stroke; stroke: var(--surface); stroke-width: 3px; }
svg .sel { fill: none; stroke: var(--ink); stroke-width: 1.5; }
svg text.digit { font-size: 10.5px; font-weight: 700; fill: var(--surface); text-anchor: middle;
  pointer-events: none; font-variant-numeric: tabular-nums; }
.board { display: grid; grid-template-columns: minmax(0, 1fr) 21.5rem; gap: 1.25rem; align-items: start; }
.plot-column { min-width: 0; }
.tiers { position: sticky; top: 0.75rem; max-height: calc(100vh - 1.5rem); overflow-y: auto;
  background: var(--surface); border: 1px solid var(--rule); border-radius: 6px; padding: 0.8rem 0.95rem 0.9rem;
  margin-top: 1.1rem; font-size: 13px; }
.tiers h2 { font-size: 1rem; margin: 0 0 0.15rem; }
.tiers h3 { display: flex; align-items: baseline; gap: 0.5rem; font-size: 13.5px; margin: 0.9rem 0 0.1rem;
  padding-top: 0.55rem; border-top: 1px solid var(--grid); }
.tiers h3 .n { font-weight: 400; color: var(--muted); }
.tiers h3 .focus { margin-left: auto; }
.tiers h4 { display: flex; align-items: center; gap: 0.35rem; font-size: 12px; font-weight: 600; color: var(--ink-2);
  margin: 0.45rem 0 0.1rem; }
.tiers h4 .n { font-weight: 400; color: var(--muted); }
.tiers .note { color: var(--muted); font-size: 12.5px; margin: 0.15rem 0 0.5rem; }
.tiers .empty { color: var(--muted); font-size: 12.5px; margin: 0.1rem 0; }
.swatch { display: inline-block; width: 9px; height: 9px; border-radius: 50%; flex: none; }
table.counts { width: 100%; font-size: 12.5px; margin: 0.45rem 0 0.35rem; background: transparent; }
table.counts th, table.counts td { padding: 0.15rem 0.3rem; border-bottom: 1px solid var(--grid); background: transparent; }
table.counts th { font-weight: 500; color: var(--ink-2); white-space: nowrap; text-align: left; }
table.counts th .swatch { vertical-align: 0; margin-right: 0.3rem; }
table.counts th.h { text-align: center; color: var(--muted); }
table.counts td { text-align: center; font-variant-numeric: tabular-nums; }
table.counts td.tot, table.counts tr.tot td, table.counts tr.tot th { font-weight: 650; color: var(--ink); }
table.counts td.zero { color: var(--muted); }
table.counts .unset { color: var(--muted); }
table.counts tr.tot th, table.counts tr.tot td { border-bottom: 0; border-top: 1px solid var(--rule); }
.tier-tools { display: flex; flex-wrap: wrap; gap: 0.35rem; margin: 0.3rem 0 0.2rem; }
.tier-tools .reset[aria-pressed="true"] { background: var(--ink); color: var(--surface); border-color: var(--ink); }
.tiers textarea { width: 100%; font: 12px var(--mono); color: var(--ink); background: var(--page);
  border: 1px solid var(--rule); border-radius: 4px; padding: 0.35rem 0.45rem; margin-top: 0.35rem; resize: vertical; }
.lane-row { display: flex; align-items: center; gap: 0.45rem; padding: 0.08rem 0; }
.lane-row.selected, .lane-row:hover { background: var(--head); }
.lane-row .nm { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font: 12.5px var(--mono); color: var(--ink); background: none; border: 0; padding: 0; text-align: left; cursor: pointer; }
.lane-row .nm:hover { text-decoration: underline; text-decoration-color: var(--muted); }
.lane-row .tag { font-size: 11px; color: var(--muted); flex: none; }
.lane-row .tag.off { color: var(--off-ink); }
.boxes { display: inline-flex; gap: 2px; flex: none; }
.box { width: 1.25rem; height: 1.25rem; padding: 0; font: 11px var(--mono); line-height: 1; cursor: pointer;
  color: var(--muted); background: var(--surface); border: 1px solid var(--rule); border-radius: 3px; }
.box:hover { border-color: var(--ink-2); color: var(--ink); }
.box[aria-pressed="true"] { background: var(--ink); border-color: var(--ink); color: var(--surface); }
.box.off-box { width: auto; padding: 0 0.3rem; margin-left: 3px; }
.box.off-box[aria-pressed="true"] { background: var(--off); border-color: var(--off); color: var(--surface); }
.lane-row.is-off .nm { color: var(--muted); text-decoration: line-through; text-decoration-color: var(--off); }
.lane-row { flex-wrap: wrap; }
.lane-row .tag.beaten { color: var(--frontier-ink); flex-basis: 100%; padding-left: 8.6rem; margin-top: -0.1rem;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tip .beaten { color: var(--frontier-ink); }
.sensitivity { background: var(--surface); border: 1px solid var(--rule); border-radius: 6px;
  padding: 0.9rem 1.1rem 1rem; margin-top: 1.1rem; }
.sensitivity h2 { margin: 0 0 0.2rem; }
.sensitivity .lede { font-size: 13px; max-width: 60rem; }
table.sens { width: auto; min-width: 100%; font-size: 12.5px; }
table.sens th, table.sens td { padding: 0.2rem 0.45rem; }
table.sens thead th { vertical-align: bottom; white-space: normal; min-width: 4.2rem; max-width: 7.5rem;
  font-weight: 600; line-height: 1.25; }
table.sens thead th .sub { font-weight: 400; }
table.sens thead th.lane { min-width: 12rem; }
table.sens th.composite, table.sens td.composite { background: var(--head); }
table.sens td.cell, table.sens th.cell, table.sens td.agree { text-align: center; font-variant-numeric: tabular-nums; }
table.sens td.cell.none { color: var(--muted); }
table.sens td.cell.diff span { display: inline-block; min-width: 1.35rem; border-radius: 3px;
  background: var(--flag); color: var(--flag-ink); box-shadow: inset 0 0 0 1px var(--flag-ink); font-weight: 650; }
table.sens td.mine { font-weight: 650; text-align: center; }
table.sens tr.grp th { background: transparent; color: var(--ink); font-size: 13px; padding-top: 0.6rem;
  border-bottom: 1px solid var(--rule); }
table.sens tr.grp th .n { font-weight: 400; color: var(--muted); margin-left: 0.4rem; }
table.sens td.lane { font: 12px var(--mono); white-space: nowrap; }
table.sens td.lane .swatch { margin-right: 0.4rem; vertical-align: 0; }
table.sens td.agree.low { color: var(--off-ink); font-weight: 650; }
.picker { position: absolute; z-index: 3; background: var(--surface); color: var(--ink); border: 1px solid var(--ink);
  border-radius: 4px; box-shadow: 0 3px 10px rgba(0, 0, 0, 0.16); font-size: 12.5px; padding: 0.4rem 0.55rem; max-width: 18rem; }
.picker .who { font: 12.5px var(--mono); margin-bottom: 0.3rem; }
.picker .row { display: flex; align-items: center; gap: 0.4rem; }
.picker .box { width: 1.6rem; height: 1.6rem; font-size: 12.5px; }
.picker .quiet { font-size: 12px; margin-top: 0.3rem; }
.bands-button[disabled] { color: var(--muted); cursor: default; text-decoration: none; }
.frontier-table .quiet { font-size: 13px; }
table.frontier tr.hot td { background: var(--head); }
table.frontier tr.off-row td { color: var(--off-ink); }
.evidence > p { color: var(--ink-2); }
.evidence details { background: var(--surface); border: 1px solid var(--rule); border-radius: 6px; margin-top: 0.6rem; }
.evidence summary { padding: 0.55rem 0.9rem; font-weight: 650; cursor: pointer; }
.evidence details[open] > summary { border-bottom: 1px solid var(--grid); }
.evidence .inner { padding: 0.3rem 0.9rem 0.8rem; }
.evidence details details { border: 0; border-top: 1px solid var(--grid); border-radius: 0; margin: 0; }
.evidence details details summary { font-weight: 600; padding-inline: 0; }
.evidence .count { font-weight: 400; color: var(--muted); margin-left: 0.35rem; }
.evidence .notes-block summary { font-weight: 400; }
.scroll { overflow-x: auto; margin: 0.6rem 0 0.4rem; }
table { border-collapse: collapse; width: 100%; font-size: 13px; background: var(--surface); }
th, td { padding: 0.32rem 0.55rem; text-align: left; vertical-align: top;
  border-bottom: 1px solid var(--grid); }
th { background: var(--head); font-weight: 600; color: var(--ink-2); white-space: nowrap; }
th.num, td.num { text-align: right; font-variant-numeric: tabular-nums; }
td.model { border-right: 1px solid var(--grid); }
.sub { display: block; font-size: 12px; color: var(--muted); font-family: var(--sans); }
.sub.off { color: var(--off-ink); }
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
.notes { font-size: 12.5px; padding-left: 1.2rem; }
footer { margin-top: 3rem; color: var(--muted); font-size: 12.5px; }
@media (max-width: 62rem) { .plot-body, .board { grid-template-columns: minmax(0, 1fr); }
  .tiers { position: static; max-height: none; } }
@media (max-width: 40rem) { body { padding-inline: 1rem; } .plot { padding-inline: 0.7rem; } .finding { font-size: 14px; } }
@media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto; } }
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
    chunks.extend(_plots_section(effort_rows, lanes_doc, proposals, bench))
    chunks += ['<section class="evidence">', "<h2>The numbers</h2>",
               "<p>Every figure behind the plots and the pre-screen, closed until you open one.</p>"]
    chunks.extend(_boards_block(effort_rows, lanes_doc, proposals))
    chunks.extend(_rows_block(effort_rows, lanes_doc, proposals))
    chunks.extend(_catalog_block(lanes_doc, proposals))
    chunks.extend(_scores_block(bench, lanes_doc))
    chunks.append("</section>")
    chunks.append("<footer>Epoch AI data is CC-BY 4.0. Artificial Analysis data requires "
                  "attribution. Terminal-Bench scores an agent-model pair, never a model "
                  "alone. Costs are never comparable across sources.</footer>")
    chunks.extend(["</main>", f"<script>\n{_script()}</script>", "</body>", "</html>", ""])
    return "\n".join(chunks)


def write(path, bench, lanes_doc, effort_rows=None):
    """Write the rendered page to path and return path."""
    text = render(bench, lanes_doc, effort_rows)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path
