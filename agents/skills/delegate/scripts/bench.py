#!/usr/bin/env python3
"""bench.py — benchmark ranking report for the human who sets lane tiers.

Evidence for the human's tier decisions; never read by routing
or any other script, skill, or hook.

Sources:
  Epoch AI, Benchmarking Hub, https://epoch.ai/data/eci_benchmarks.csv, CC-BY 4.0
  Artificial Analysis, https://artificialanalysis.ai, the per-effort rows that
    `effort.py aa` reads out of a /models/<slug> page and accepts (ticket 19).
    No API and no key: the free API held one entry per model on a first page
    of 200, so most lanes had no figure at their own effort.

  python3 bench.py [--config-dir DIR] [--out-dir DIR] [--date YYYY-MM-DD]
                   [--epoch-csv FILE] [--effort-rows FILE ...]
  python3 bench.py model MODEL [--config-dir DIR] [--effort-rows FILE ...]
                               [--epoch-csv FILE] [--json]
"""
import argparse
import csv
import io
import json
import os
import re
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

import catalog
# Reconciling a source's printed model name against a lane model is the
# catalog's own knowledge; both this report and the setup pre-screen read it
# from there rather than keeping a second copy.
from catalog import CatalogError, EFFORTS, normalize_name, resolve_published_model, strip_effort_suffix

EPOCH_URL = "https://epoch.ai/data/eci_benchmarks.csv"
DEFAULT_OUT_DIR = "~/.cache/delegate/bench/"
EXPECTED_HEADER = (
    "model_id,benchmark_id,performance,benchmark,benchmark_release_date,"
    "model,model_version,Model,date,source"
)
EXPECTED_FIELDS = EXPECTED_HEADER.split(",")
EPOCH_BENCHMARKS = (
    "DeepSWE",
    "FrontierCode",
    "APEX-Agents",
    "Terminal Bench",
    "SWE-Bench verified",
)
EFFORT_FALLBACK = ("max", "xhigh", "high")
# Every effort a lane can carry, strongest first: this has to cover
# catalog.EFFORTS, because a source reports whatever the vendor exposes. While
# it stopped at `xhigh` a max-effort figure could never be preferred, and the
# distance between two efforts was measured on a scale missing its top half
# (ticket 17).
LANE_EFFORT_ORDER = ("ultra", "max", "xhigh", "high", "medium", "low")
# When one effort has to stand for a model — the model-level figure, and the
# `lane effort` a note names — it is the strongest effort a lane actually works
# at. `ultra` is generated disabled and no source scores it, so it never stands
# for the model even when a lane carries it.
EFFORT_PREFERENCE = tuple(e for e in LANE_EFFORT_ORDER if e != "ultra")
# The key a figure gets when the source stated no effort. It is a key like any
# other, so the figure is never dropped for being unlabelled - and it matches
# no lane, so it is never attributed for being unlabelled either.
UNKNOWN_EFFORT = "unknown"
AA_SOURCE = "aa"
# The AA columns are whichever component benchmarks the accepted rows carry, in
# the order the rows first name them; the composite Intelligence Index is never
# one (its weighting is unpublished, assets/sources.json). Cost per task sits
# beside them and is never ranked: it is the index's figure for the variant.
AA_COST_COLUMN = "Cost/task (USD)"
AA_NO_ROWS = "no rows from effort.py aa given (--effort-rows)"
ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
BOARDS_PATH = os.path.join(ASSETS_DIR, "boards.json")
SOURCES_PATH = os.path.join(ASSETS_DIR, "sources.json")
ABOUT_FIELDS = ("url", "fetched", "measures", "tasks", "score", "scale", "cost",
                "speaks_to", "direction")
DIRECTION_HIGHER = "higher-is-better"
DIRECTION_LOWER = "lower-is-better"
DIRECTION_UNKNOWN = "unknown"
EPOCH_SOURCE = "epoch"
BOARD_VERSION_RE = re.compile(r"(?:v)?(\d+\.\d+(?:\.\d+)?)\s*$", re.I)


class BenchError(Exception):
    """Fatal Epoch or catalog-adjacent failure; printed as bench: <msg>."""


def utc_today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def split_model_version(model_version):
    text = (model_version or "").strip()
    if not text:
        return "", "unknown"
    if "_" not in text:
        return text, "unknown"
    slug, effort = text.rsplit("_", 1)
    if not slug:
        return text, "unknown"
    if not effort:
        return slug, "unknown"
    return slug, effort


def catalog_models(lanes):
    models = {}
    for lane_name, lane in lanes.items():
        model = lane["model"]
        rec = models.get(model)
        if rec is None:
            rec = {"lanes": [], "efforts": []}
            models[model] = rec
        rec["lanes"].append(lane_name)
        effort = lane["effort"]
        if effort not in rec["efforts"]:
            rec["efforts"].append(effort)
    return models


def lane_effort_of(rec):
    efforts = rec["efforts"]
    if len(efforts) == 1:
        return efforts[0]
    for effort in EFFORT_PREFERENCE:
        if effort in efforts:
            return effort
    return efforts[0]


def model_matches_slug(catalog_model, slug):
    if slug == catalog_model:
        return True
    base, _suffix_effort = strip_effort_suffix(catalog_model)
    return bool(base) and slug == base


def as_number(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def rank_by_score(scores):
    """Competition rank: 1 is best, ties share the better rank, next rank skips."""
    items = [(model, score) for model, score in scores.items() if score is not None]
    ranks = {}
    for model, score in items:
        better = sum(1 for _m, other in items if other > score)
        ranks[model] = better + 1
    return ranks


def mean_rank_display(ranks_by_bench, model):
    present = [ranks_by_bench[b][model] for b in ranks_by_bench if model in ranks_by_bench[b]]
    n = len(present)
    if n == 0:
        return None, "— (n=0)"
    mean = sum(present) / n
    return mean, f"{mean:.1f} (n={n})"


def fmt_pct(score):
    if score is None:
        return "—"
    return f"{score * 100:.1f}"


def fmt_aa_value(score):
    """An AA component score as the rows carry it: most are fractions
    (Terminal-Bench 2.1 0.873), Omniscience is a signed figure (-63.05)."""
    if score is None:
        return "—"
    if abs(score - round(score)) < 1e-9:
        return str(int(round(score)))
    if abs(score) < 1:
        return f"{score:.3f}"
    return f"{score:.1f}"


def fmt_cost(cost):
    return "—" if cost is None else f"{cost:.2f}"


def md_table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def read_text_file(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return f.read()


def fetch_bytes(url, headers=None, timeout=60):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def load_epoch_csv_text(text):
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = text.splitlines()
    first = lines[0].strip() if lines else ""
    if first != EXPECTED_HEADER:
        raise BenchError("Epoch CSV missing expected header")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames != EXPECTED_FIELDS:
        raise BenchError("Epoch CSV missing expected header")
    rows = []
    for raw in reader:
        benchmark = (raw.get("benchmark") or "").strip()
        if benchmark not in EPOCH_BENCHMARKS:
            continue
        performance = as_number(raw.get("performance"))
        if performance is None:
            continue
        model_version = (raw.get("model_version") or "").strip()
        slug, effort = split_model_version(model_version)
        rows.append(
            {
                "benchmark": benchmark,
                "performance": performance,
                "model_version": model_version,
                "slug": slug,
                "effort": effort,
                "source": (raw.get("source") or "").strip(),
                "model": (raw.get("model") or "").strip(),
                "date": (raw.get("date") or "").strip(),
                "benchmark_release_date": (raw.get("benchmark_release_date") or "").strip(),
            }
        )
    return rows


def load_epoch(epoch_csv):
    if epoch_csv:
        path = os.path.abspath(os.path.expanduser(epoch_csv))
        try:
            text = read_text_file(path)
        except OSError as e:
            raise BenchError(f"cannot read Epoch CSV: {e}") from e
        return load_epoch_csv_text(text)
    try:
        raw = fetch_bytes(EPOCH_URL)
        text = raw.decode("utf-8-sig")
    except Exception as e:
        raise BenchError(f"cannot read Epoch CSV: {e}") from e
    return load_epoch_csv_text(text)


def match_epoch_rows(epoch_rows, models):
    matched = defaultdict(list)
    for row in epoch_rows:
        for model in models:
            if model_matches_slug(model, row["slug"]):
                matched[(model, row["benchmark"])].append(row)
    return matched


def choose_effort(available, lane_efforts):
    for effort in EFFORT_PREFERENCE:
        if effort in lane_efforts and effort in available:
            return effort
    for effort in lane_efforts:
        if effort in available:
            return effort
    for effort in EFFORT_FALLBACK:
        if effort in available:
            return effort
    return None


def _effort_rank(effort):
    """Sort key over efforts: strongest first, `unknown` last."""
    if effort in LANE_EFFORT_ORDER:
        return LANE_EFFORT_ORDER.index(effort)
    return len(LANE_EFFORT_ORDER)


def effort_cell_key(effort):
    """The cell key for one measured effort, or `unknown` for an unstated one."""
    return str(effort) if effort else UNKNOWN_EFFORT


def collect_epoch_cells(rows):
    """Every effort measured for one model on one benchmark, keyed by effort.

    Two rows at the same effort are one figure, with `duplicates` naming the
    disagreement. Two rows at different efforts are two figures: a lane may
    claim only the figure measured at its own effort, so collapsing them here
    is what attributed one model's whole sweep to every one of its lanes
    (ticket 17).
    """
    by_effort = defaultdict(list)
    for row in rows:
        by_effort[effort_cell_key(row["effort"])].append(row)
    cell = {}
    for effort, group in by_effort.items():
        best = max(group, key=lambda r: r["performance"])
        scores = {c["performance"] for c in group}
        dup_pairs = None
        if len(scores) > 1:
            dup_pairs = []
            seen = set()
            for cand in sorted(group, key=lambda r: (-r["performance"], r["source"])):
                key = (cand["performance"], cand["source"])
                if key in seen:
                    continue
                seen.add(key)
                dup_pairs.append(key)
        cell[effort] = {
            "performance": best["performance"],
            "source": best["source"],
            "duplicates": dup_pairs,
        }
    return cell


def effort_attributes(measured_effort, lane_effort):
    """Whether a figure measured at `measured_effort` is this lane's figure.

    The whole of the attribution rule, in one place: equality, and `unknown`
    matching nothing, because a source that did not state an effort has not
    said which lane it measured. The report, the wizard and the page all read
    it from here, so the page can never disagree with the decision the wizard
    offers (the reason `dominating_row` is exported rather than copied).
    """
    if not lane_effort:
        return False
    return effort_cell_key(measured_effort) == str(lane_effort)


def lane_figure(cell, lane_effort):
    """The one figure in a cell a lane may claim, or None."""
    for effort, figure in (cell or {}).items():
        if effort_attributes(effort, lane_effort):
            out = dict(figure)
            out["effort"] = effort
            return out
    return None


def model_figure(cell, lane_efforts):
    """The one figure the model-level view reports for a cell: measured at a
    lane's effort where possible, else the strongest fallback effort, else the
    best score in the cell. It stands for the model, never for one lane."""
    if not cell:
        return None
    chosen = choose_effort(cell, lane_efforts)
    if chosen is None:
        chosen = max(
            cell.items(),
            key=lambda kv: (kv[1]["performance"], kv[1]["source"] or ""),
        )[0]
    figure = dict(cell[chosen])
    # the key as the source left it, `unknown` included: the notes and the
    # page both say which effort a figure was measured at, and "unknown" is
    # a fact where "" would read as an omission
    figure["effort"] = chosen
    return figure


def model_figures(cells, lane_efforts):
    """{benchmark: the model-level figure}, for the tables and the notes."""
    out = {}
    for bench, cell in (cells or {}).items():
        figure = model_figure(cell, lane_efforts)
        if figure:
            out[bench] = figure
    return out


def effort_used_label(figures, lane_effort):
    used = [(bench, figures[bench]["effort"]) for bench in EPOCH_BENCHMARKS if figures.get(bench)]
    if not used:
        return "—"
    unique = {effort for _b, effort in used}
    if len(unique) == 1:
        return next(iter(unique))
    parts = []
    for bench, effort in used:
        if effort != lane_effort:
            parts.append(f"{bench}: {effort}")
    return "; ".join(parts) if parts else lane_effort


def sort_report_rows(items):
    def key(item):
        mean = item["mean"]
        if mean is None:
            return (1, 0.0, item["model"])
        return (0, mean, item["model"])

    return sorted(items, key=key)


def build_epoch_section(models, matched):
    scores_by_bench = {b: {} for b in EPOCH_BENCHMARKS}
    cells_by_model = {}
    figures_by_model = {}
    for model, rec in models.items():
        lane_efforts = rec["efforts"]
        cells = {}
        for bench in EPOCH_BENCHMARKS:
            cell = collect_epoch_cells(matched.get((model, bench), []))
            if cell:
                cells[bench] = cell
        cells_by_model[model] = cells
        figures = model_figures(cells, lane_efforts)
        figures_by_model[model] = figures
        for bench, figure in figures.items():
            scores_by_bench[bench][model] = figure["performance"]
    ranks_by_bench = {b: rank_by_score(scores_by_bench[b]) for b in EPOCH_BENCHMARKS}
    items = []
    for model, rec in models.items():
        mean, mean_s = mean_rank_display(ranks_by_bench, model)
        items.append(
            {
                "model": model,
                "lanes": ", ".join(sorted(rec["lanes"])),
                "lane_effort": lane_effort_of(rec),
                "lane_efforts": rec["efforts"],
                "cells": cells_by_model[model],
                "figures": figures_by_model[model],
                "mean": mean,
                "mean_s": mean_s,
                "gap": mean is None,
            }
        )
    return sort_report_rows(items)


def load_effort_rows(paths):
    """Every row from one accepted-rows file or several, in order."""
    rows = []
    for path in paths or ():
        full = os.path.abspath(os.path.expanduser(path))
        try:
            doc = json.loads(read_text_file(full))
        except OSError as e:
            raise BenchError(f"cannot read effort rows: {e}") from e
        except json.JSONDecodeError as e:
            raise BenchError(f"effort rows {path}: invalid JSON: {e}") from e
        if not isinstance(doc, list):
            raise BenchError(f"effort rows {path}: expected a JSON list")
        rows.extend(doc)
    return rows


def aa_component_rows(effort_rows, lanes_doc):
    """The Artificial Analysis component rows that name a lane model.

    Rows of other sources, the composite index, and rows naming nobody's
    model are left out; a row's model is resolved by the catalog, with its
    effort, so an agy family member is found by the effort it carries.
    """
    out = []
    for row in effort_rows or []:
        if not isinstance(row, dict) or row.get("source") != AA_SOURCE or row.get("composite"):
            continue
        benchmark = row.get("benchmark")
        score = as_number(row.get("score"))
        if not isinstance(benchmark, str) or not benchmark.strip() or score is None:
            continue
        effort = row.get("effort")
        model = catalog.resolve_published_model(row.get("model"), lanes_doc, effort=effort)
        if model is None:
            continue
        out.append({
            "model": model,
            "effort": effort_cell_key(effort),
            "benchmark": benchmark,
            "score": score,
            "cost_usd": as_number(row.get("cost_usd")),
        })
    return out


def aa_measurements(component_rows):
    """({model: {effort: {benchmark: score}}}, {(model, effort): cost per task},
    [benchmark, in the order the rows first name them]). The first row for one
    model, effort and benchmark is the figure; effort.py has already de-duplicated."""
    scores = defaultdict(lambda: defaultdict(dict))
    costs = {}
    benchmarks = []
    for row in component_rows:
        scores[row["model"]][row["effort"]].setdefault(row["benchmark"], row["score"])
        if row["cost_usd"] is not None:
            costs.setdefault((row["model"], row["effort"]), row["cost_usd"])
        if row["benchmark"] not in benchmarks:
            benchmarks.append(row["benchmark"])
    return scores, costs, benchmarks


def aa_model_effort(measured, lane_efforts):
    """The one effort whose figures stand for a model in the model view: the
    strongest effort a lane runs that AA measured, else the strongest effort AA
    measured. `none` and an unstated effort never stand for a model."""
    for effort in EFFORT_PREFERENCE:
        if effort in lane_efforts and effort in measured:
            return effort
    for effort in EFFORT_PREFERENCE:
        if effort in measured:
            return effort
    return None


def build_aa_models(models, scores, costs, benchmarks):
    """{model: {cols, effort, cost_usd, mean, mean_s} or None}: one figure per
    model per column, all measured at one effort, ranked model against model."""
    chosen = {}
    for model, rec in models.items():
        effort = aa_model_effort(scores.get(model) or {}, rec["efforts"])
        if effort is not None:
            chosen[model] = effort
    ranks = {}
    for benchmark in benchmarks:
        figures = {m: scores[m][e][benchmark] for m, e in chosen.items() if benchmark in scores[m][e]}
        if figures:
            ranks[benchmark] = rank_by_score(figures)
    out = {}
    for model in models:
        effort = chosen.get(model)
        if effort is None:
            out[model] = None
            continue
        mean, mean_s = mean_rank_display(ranks, model)
        out[model] = {
            "cols": dict(scores[model][effort]),
            "effort": effort,
            "cost_usd": costs.get((model, effort)),
            "mean": mean,
            "mean_s": mean_s,
        }
    return out


def build_notes(models, epoch_items, aa_models, aa_skipped):
    notes = []
    epoch_by_model = {item["model"]: item for item in epoch_items}
    for model in models:
        if epoch_by_model[model]["gap"]:
            notes.append(f"{model} absent from Epoch AI")
        if aa_skipped is None and aa_models.get(model) is None:
            notes.append(f"{model} absent from Artificial Analysis")
    for item in epoch_items:
        model = item["model"]
        lane_efforts = set(item["lane_efforts"])
        lane_effort = item["lane_effort"]
        for bench in EPOCH_BENCHMARKS:
            cell = item["cells"].get(bench)
            if not cell:
                continue
            figure = item["figures"].get(bench)
            if figure and figure["effort"] not in lane_efforts:
                notes.append(
                    f"{model} {bench} used effort {figure['effort']} (lane effort {lane_effort})"
                )
            for effort in sorted(cell, key=lambda e: (_effort_rank(e), e)):
                dups = cell[effort]["duplicates"]
                if dups:
                    shown = ", ".join(
                        f"{perf:.2f} ({source or 'unknown'})" for perf, source in dups
                    )
                    notes.append(f"{model} {bench} duplicate scores: {shown}")
            # every other effort the source measured is real data that reaches
            # no lane; the report is the human's evidence, so say so here
            # rather than let it vanish behind the one figure shown.
            spare = [e for e in cell if e not in lane_efforts
                     and not (figure and e == effort_cell_key(figure["effort"]))]
            for effort in sorted(spare, key=lambda e: (_effort_rank(e), e)):
                where = "at an unstated effort" if effort == UNKNOWN_EFFORT else f"at effort {effort}"
                notes.append(
                    f"{model} {bench} also measured {where} "
                    f"({cell[effort]['performance']:.2f}); no lane runs that effort"
                )
    if aa_skipped is None:
        for model, rec in models.items():
            aa = aa_models.get(model)
            if aa is not None and aa["effort"] not in rec["efforts"]:
                notes.append(
                    f"{model} Artificial Analysis figures are at effort {aa['effort']}; "
                    "no lane runs that effort, so no lane claims them"
                )
    return notes


def aa_source_line(effort_rows):
    """Where the AA rows came from: the page URLs and the dates observed."""
    urls, dates = [], []
    for row in effort_rows or []:
        if isinstance(row, dict) and row.get("source") == AA_SOURCE:
            if row.get("url") and row["url"] not in urls:
                urls.append(row["url"])
            if row.get("observed") and row["observed"] not in dates:
                dates.append(row["observed"])
    where = ", ".join(urls) if urls else "https://artificialanalysis.ai"
    when = f", observed {', '.join(sorted(dates))}" if dates else ""
    return f"Source: Artificial Analysis, {where}, per-effort rows accepted by effort.py aa{when}"


def render_report(
    date,
    epoch_table,
    aa_table,
    aa_skipped,
    notes,
    aa_source=None,
):
    lines = [
        f"# Lane benchmark ranking {date}",
        "",
        "This report is evidence for the human's tier edits and is read by no script.",
        "",
        f"Source: Epoch AI, Benchmarking Hub, {EPOCH_URL}, CC-BY 4.0, fetched {date}",
    ]
    if aa_skipped is None:
        lines.append(aa_source or aa_source_line(None))
    else:
        lines.append(f"Artificial Analysis: skipped ({aa_skipped})")
    lines.extend(["", "## Epoch AI", "", epoch_table, "", "## Artificial Analysis", ""])
    if aa_skipped is None:
        lines.append(aa_table)
    else:
        lines.append(f"Artificial Analysis: skipped ({aa_skipped})")
    lines.extend(["", "## Gaps and notes", ""])
    if notes:
        for note in notes:
            lines.append(f"- {note}")
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def build_lane_section(lanes_doc, collected_models, aa_skipped, aa_scores=None, aa_costs=None,
                       aa_benchmarks=()):
    """One record per catalog lane, holding only the figures measured at that
    lane's own effort, and the AA columns some lane has a figure for.

    `models` stays the model-level view, which is what a comparison against
    models nobody runs needs. This is the view a per-lane decision needs: the
    mean rank and its `n=` count that lane's own figures, so it is a mean of
    measurements that could have happened together. A lane whose model was
    never measured at its effort has an empty record, which is the honest
    answer and not the same as a model nobody measured. Artificial Analysis
    measures most models at every effort (ticket 19), so its figures are
    attributed per lane by the same rule, `effort_attributes`.
    """
    aa_scores = aa_scores or {}
    aa_costs = aa_costs or {}
    lanes = {}
    for lane_name, lane in (lanes_doc.get("lanes") or {}).items():
        model = lane.get("model")
        effort = lane.get("effort")
        rec = collected_models.get(model)
        cells = {}
        aa = None
        if rec:
            epoch_cells = (rec.get("epoch") or {}).get("cells") or {}
            for bench in EPOCH_BENCHMARKS:
                figure = lane_figure(epoch_cells.get(bench), effort)
                if figure:
                    cells[bench] = figure
        if aa_skipped is None:
            for measured, cols in (aa_scores.get(model) or {}).items():
                if cols and effort_attributes(measured, effort):
                    aa = {"cols": dict(cols), "effort": effort,
                          "cost_usd": aa_costs.get((model, measured))}
                    break
        lanes[lane_name] = {"model": model, "effort": effort, "cells": cells, "aa": aa}

    # ranks compare lane against lane, each at its own effort, so a rank is
    # over figures that are comparable; a lane with no figure on a benchmark is
    # absent from that benchmark's ranking rather than ranked last.
    ranks_by_bench = {}
    for bench in EPOCH_BENCHMARKS:
        scores = {name: rec["cells"][bench]["performance"]
                  for name, rec in lanes.items() if bench in rec["cells"]}
        if scores:
            ranks_by_bench[bench] = rank_by_score(scores)
    for name, rec in lanes.items():
        mean, mean_s = mean_rank_display(ranks_by_bench, name)
        rec["mean"] = mean
        rec["mean_s"] = mean_s
        rec["n"] = len(rec["cells"])
    aa_names = []
    if aa_skipped is None:
        aa_names = [col for col in aa_benchmarks
                    if any(rec["aa"] and col in rec["aa"]["cols"] for rec in lanes.values())]
        aa_ranks = {}
        for col in aa_names:
            scores = {name: rec["aa"]["cols"][col] for name, rec in lanes.items()
                      if rec["aa"] and rec["aa"]["cols"].get(col) is not None}
            if scores:
                aa_ranks[col] = rank_by_score(scores)
        for name, rec in lanes.items():
            if rec["aa"] is None:
                continue
            mean, mean_s = mean_rank_display(aa_ranks, name)
            rec["aa"]["mean"] = mean
            rec["aa"]["mean_s"] = mean_s
    return lanes, aa_names


# --- carry and display-order policy (consumed by TUI and HTML) ----------------
# Renderers own wording. Decisions carry kind/source/competitor so HTML never
# has to parse a reason phrase.

NO_ROWS_REASON = "no rows for this lane"
NO_DATA_REASON = "no per-effort data"
NOT_DOMINATED_REASON = "not dominated"
ULTRA_REASON = "ultra, never carried"

KIND_DOMINATED = "dominated"
KIND_RECORDED = "recorded"
KIND_ULTRA = "ultra"
KIND_UNAVAILABLE = "unavailable"
KIND_NO_ROWS = "no_rows"
KIND_NOT_DOMINATED = "not_dominated"


def model_group(lane):
    """The model a lane is grouped under. An agy slug family
    (`gemini-3.8-flash-high`, `-low`) is one model at several efforts, so the
    effort suffix comes off first (ticket 26)."""
    return strip_effort_suffix(normalize_name((lane or {}).get("model")))[0]


def effort_rank(effort):
    """Most effort first: ultra, max, xhigh, high, medium, low; a stranger last."""
    try:
        return -EFFORTS.index(effort)
    except ValueError:
        return 1


def group_lanes(names, lanes_doc):
    """`names` regrouped by model: each group sits where its first lane sat,
    and lists its efforts from most to least (ticket 26, item 1).

    The order `names` arrives in is the page's own (benchmark order on a tier
    page, tier on the review page, the catalog on the carry page), and it
    decides only where each group goes. Inside a group the effort decides, so
    `fable-max` is read before `fable-low` on every page and every table.
    """
    lanes = (lanes_doc or {}).get("lanes") or {}
    groups = {}
    for name in names:
        groups.setdefault(model_group(lanes.get(name)), []).append(name)
    out = []
    for members in groups.values():
        out.extend(sorted(members, key=lambda n: effort_rank((lanes.get(n) or {}).get("effort"))))
    return out


def bench_order_key(bench, name, lanes_doc=None):
    """A lane's place by Epoch rank, or AA rank if its group has no Epoch; measured
    lanes first, then by name. This is the order the tier pages open in and
    the order the benchmark page lists lanes in, so it lives in one place."""
    rec = ((bench or {}).get("lanes") or {}).get(name) if bench else None
    mean = rec.get("mean") if rec else None
    if mean is None and rec:
        lanes = (lanes_doc or {}).get("lanes") or {}
        group = model_group(lanes.get(name))
        has_epoch = any(model_group(lane) == group
                        and ((bench or {}).get("lanes", {}).get(other) or {}).get("mean") is not None
                        for other, lane in lanes.items())
        if not has_epoch:
            mean = (rec.get("aa") or {}).get("mean")
    return (mean is None, mean if mean is not None else 0, name)


def lane_order(lanes_doc, bench):
    """Every lane in the order a tier page lists them: benchmark order, then
    grouped by model with efforts most to least."""
    names = sorted((lanes_doc or {}).get("lanes") or {}, key=lambda n: bench_order_key(bench, n, lanes_doc))
    return group_lanes(names, lanes_doc)


def dominated_reason(effort, source):
    """The reason for a lane another effort dominates: `high wins on aa`.

    It names the source because two sources can disagree about one lane, and it
    is not "dominated by high (tbench)" because that is 26 places and the `why`
    column has 21 at 80 columns; `medium wins on tbench`, the longest, is 21.
    """
    return f"{effort} wins on {source}"


def is_dominated_reason(why):
    """Whether a proposal's reason is the data switching the lane off.

    Compatibility alias: renderers should read `kind`, not parse this prose.
    A decision dict is accepted so old callers can pass either form.
    """
    if isinstance(why, dict):
        return why.get("kind") == KIND_DOMINATED
    return isinstance(why, str) and " wins on " in why


def recorded_reason(enabled):
    """The reason shown for a lane whose `enabled` the human already wrote."""
    return f"{'on' if enabled else 'off'} in the catalog"


def carry_decision(lane, enabled, kind, source=None, competitor=None):
    """One structured carry verdict. Renderers turn this into wording."""
    return {
        "lane": lane,
        "enabled": enabled,
        "kind": kind,
        "source": source,
        "competitor": competitor,
    }


def carry_reason(decision):
    """Display prose for one carry decision. HTML must not parse this back."""
    if not isinstance(decision, dict):
        return NOT_DOMINATED_REASON
    kind = decision.get("kind")
    if kind == KIND_DOMINATED:
        return dominated_reason(decision.get("competitor"), decision.get("source"))
    if kind == KIND_RECORDED:
        return recorded_reason(bool(decision.get("enabled")))
    if kind == KIND_ULTRA:
        return ULTRA_REASON
    if kind == KIND_UNAVAILABLE:
        return NO_DATA_REASON
    if kind == KIND_NO_ROWS:
        return NO_ROWS_REASON
    return NOT_DOMINATED_REASON


def evidence_unavailable(effort_rows, proposals=None):
    """True when there was no per-effort evidence, as distinct from an empty proposal."""
    if effort_rows is None:
        return True
    if not proposals:
        return False
    return all(d.get("kind") == KIND_UNAVAILABLE for d in proposals.values())


def resolve_effort_rows(lanes_doc, effort_rows):
    """Returns (rows keyed by catalog model, published names that name no lane).

    A source prints a model however it pleases: `gpt-5.6-luna` from SWE Refactor
    Bench, `GPT-6 Astra` from Terminal-Bench and Artificial Analysis. Every
    comparison below is against `lane["model"]`, so each row is re-keyed to the
    lane model its printed name denotes, and the catalog owns that mapping
    (`catalog.resolve_published_model`). A row naming no lane model is dropped
    rather than reported per lane: the leaderboards carry GLM-5.3, Opus 4.8,
    Sonnet 5 and a dozen others that are nobody's lane, and one line naming them
    all is what a human needs to spot a `published_as` they still owe us.
    """
    resolved, unmatched = [], []
    for row in effort_rows or []:
        if not isinstance(row, dict):
            continue
        model = resolve_published_model(row.get("model"), lanes_doc, effort=row.get("effort"))
        if model is None:
            name = row.get("model")
            if isinstance(name, str) and name.strip() and name not in unmatched:
                unmatched.append(name)
            continue
        if model == row.get("model"):
            resolved.append(row)
        else:
            copied = dict(row)
            copied["model"] = model
            resolved.append(copied)
    return resolved, unmatched


def unmatched_message(unmatched, width=79):
    """One line naming the published models no lane runs, or "" for none."""
    if not unmatched:
        return ""
    head = "no lane runs these, ignored: "
    shown = []
    for name in unmatched:
        candidate = shown + [name]
        more = len(unmatched) - len(candidate)
        tail = f" +{more} more" if more else ""
        if len(head + ", ".join(candidate) + tail) > width:
            break
        shown.append(name)
    if not shown:
        count = len(unmatched)
        phrase = "name matches" if count == 1 else "names match"
        return f"{count} published {phrase} no lane; each is too long to print here"
    more = len(unmatched) - len(shown)
    return head + ", ".join(shown) + (f" +{more} more" if more else "")


def certain_effort_rows(effort_rows):
    """Rows that may dominate. Uncertain rows inform nothing: they must not
    dominate another lane, and they are not evidence against the lane they name.

    A row at an effort no lane can select is dropped for the same reason. The
    benchmark harnesses drive the API enum, which runs `none` to `max`, so every
    published sweep carries a `none` row — and no lane can be configured at
    `none`. Letting one dominate would switch off a real lane on the strength of
    a setting that cannot be chosen, which is exactly what it did to
    luna-low@codex: equal score to `none` at a tenth of a cent more.

    A `composite` row is a reader's figure, not evidence: Artificial Analysis
    does not publish the weighting of its Intelligence Index, so it is shown and
    never counted.
    """
    certain = []
    for row in effort_rows or []:
        if not isinstance(row, dict) or row.get("uncertain") or row.get("composite"):
            continue
        if not row.get("model") or not row.get("effort"):
            continue
        if row["effort"] not in EFFORTS:
            continue
        score, cost = row.get("score"), row.get("cost_usd")
        if isinstance(score, bool) or isinstance(cost, bool):
            continue
        if not isinstance(score, (int, float)) or not isinstance(cost, (int, float)):
            continue
        certain.append(row)
    return certain


def _beats(other, row):
    """At least the score for no more money, and strictly better in one of the two."""
    return (other["score"] >= row["score"] and other["cost_usd"] <= row["cost_usd"]
            and (other["score"] > row["score"] or other["cost_usd"] < row["cost_usd"]))


def dominating_effort(model, effort, source, certain):
    """The effort of `model` that dominates `effort` inside one source, or None.

    Dominated means another effort of the same model beats it on more than half
    of the benchmarks that source scored both on. A source with one benchmark —
    Terminal-Bench, SWE Refactor Bench — comes down to that one comparison.
    Artificial Analysis scores eight components off the same runs, and losing
    one noisy component in eight is not reason enough to switch a lane off: on
    the live page of 2026-09-11 that reading proposed twelve lanes off, nine of
    them on a single component.
    """
    mine, theirs = {}, {}
    for row in certain:
        if row.get("model") != model or row.get("source") != source:
            continue
        if row.get("effort") == effort:
            mine.setdefault(row.get("benchmark"), row)
        else:
            theirs.setdefault(row["effort"], {}).setdefault(row.get("benchmark"), row)
    for other_effort, board in theirs.items():
        shared = [benchmark for benchmark in mine if benchmark in board]
        wins = sum(1 for benchmark in shared if _beats(board[benchmark], mine[benchmark]))
        if shared and 2 * wins > len(shared):
            return other_effort
    return None


def dominating_row(row, certain):
    """The dominating effort's point on this row's own board, or None.

    The judgement belongs to the effort over its whole source
    (`dominating_effort`), so every point of a dominated effort is marked on
    every board of that source, including a board where it happens to score
    higher: the lane is off over the source, not over one chart.

    Public because the benchmark page draws this rule: a point it shows hollow
    has to be a point the pre-screen switched a lane off over, and two
    implementations of one rule would eventually disagree in front of a human
    trying to check the wizard's arithmetic.
    """
    other = dominating_effort(row.get("model"), row.get("effort"), row.get("source"), certain)
    if other is None:
        return None
    board = (row.get("source"), row.get("benchmark"))
    return next((r for r in certain
                 if r.get("model") == row.get("model") and r.get("effort") == other
                 and (r.get("source"), r.get("benchmark")) == board), None)


def _first_domination(lane, certain):
    """(effort, source) of the first source in which another effort dominates
    this lane, else None."""
    sources = []
    for row in certain:
        if row.get("model") == lane["model"] and row.get("effort") == lane["effort"]:
            if row.get("source") not in sources:
                sources.append(row.get("source"))
    for source in sources:
        other = dominating_effort(lane["model"], lane["effort"], source, certain)
        if other is not None:
            return other, source
    return None


def propose_enabled(lanes_doc, effort_rows):
    """Ticket-15 pre-screen rule. Returns {name: carry_decision}."""
    rows, _unmatched = resolve_effort_rows(lanes_doc, effort_rows)
    certain = certain_effort_rows(rows)
    supplied = effort_rows is not None
    out = {}
    for name, lane in lanes_doc["lanes"].items():
        if lane.get("effort") == "ultra":
            out[name] = carry_decision(name, False, KIND_ULTRA)
            continue
        if "enabled" in lane:
            # An explicit `enabled` is a decision the human already recorded. The
            # pre-screen proposes for lanes that have no decision yet; it does not
            # undo one. Silently switching a lane back on would put it in front of
            # the ranker again without anyone saying so.
            enabled = bool(lane["enabled"])
            out[name] = carry_decision(name, enabled, KIND_RECORDED)
            continue
        found = _first_domination(lane, certain)
        if found is not None:
            other, source = found
            out[name] = carry_decision(name, False, KIND_DOMINATED, source=source, competitor=other)
            continue
        if not supplied:
            out[name] = carry_decision(name, True, KIND_UNAVAILABLE)
        elif not any(
            not row.get("uncertain")
            and row.get("model") == lane["model"]
            and row.get("effort") == lane["effort"]
            for row in rows
        ):
            out[name] = carry_decision(name, True, KIND_NO_ROWS)
        else:
            out[name] = carry_decision(name, True, KIND_NOT_DOMINATED)
    return out


def collect(lanes_doc, epoch_csv=None, effort_rows=None):
    """Collect benchmark data for the report and interactive consumers.

    `effort_rows` are accepted rows from effort.py, any mix of sources; only
    the `aa` rows are read here. Without any, Artificial Analysis is skipped
    with a reason, the way a missing source always was.
    """
    models = catalog_models(lanes_doc["lanes"])
    epoch_rows = load_epoch(epoch_csv)
    matched = match_epoch_rows(epoch_rows, models)
    epoch_items = build_epoch_section(models, matched)

    given = any(isinstance(r, dict) and r.get("source") == AA_SOURCE for r in (effort_rows or []))
    aa_skipped = None if given else AA_NO_ROWS
    aa_scores, aa_costs, aa_benchmarks = aa_measurements(aa_component_rows(effort_rows, lanes_doc))
    aa_models = (build_aa_models(models, aa_scores, aa_costs, aa_benchmarks)
                 if aa_skipped is None else {model: None for model in models})

    notes = build_notes(models, epoch_items, aa_models, aa_skipped)
    epoch_by_model = {item["model"]: item for item in epoch_items}
    collected_models = {}
    for model, rec in models.items():
        epoch = epoch_by_model[model]
        collected_models[model] = {
            "lanes": sorted(rec["lanes"]),
            "lane_effort": epoch["lane_effort"],
            "lane_efforts": list(rec["efforts"]),
            "epoch": {
                "cells": epoch["cells"],
                "mean": epoch["mean"],
                "mean_s": epoch["mean_s"],
            },
            # cols, the effort they were all measured at, cost per task at that
            # effort, and the model-against-model mean rank; None when AA
            # measured the model at no effort that can stand for it
            "aa": aa_models.get(model),
        }
    lanes, aa_columns = build_lane_section(
        lanes_doc, collected_models, aa_skipped, aa_scores, aa_costs, aa_benchmarks)
    return {
        "models": collected_models,
        "lanes": lanes,
        "epoch_benchmarks": list(EPOCH_BENCHMARKS),
        "aa_columns": aa_columns,
        "aa_skipped": aa_skipped,
        "notes": notes,
    }


def format_collection(data, effort_rows=None, date=None):
    """Markdown report from a collect() result. Shared by the CLI and plain setup."""
    epoch_table = epoch_table_from_collection(data)
    aa_table = None if data["aa_skipped"] is not None else aa_table_from_collection(data)
    return render_report(
        date or utc_today(),
        epoch_table,
        aa_table,
        data["aa_skipped"],
        data["notes"],
        aa_source=aa_source_line(effort_rows),
    )


def epoch_table_from_collection(data):
    headers = [
        "Lane(s)",
        "Model",
        "Effort used",
        *data["epoch_benchmarks"],
        "Mean rank",
    ]
    items = []
    for model, rec in data["models"].items():
        items.append({"model": model, "mean": rec["epoch"]["mean"], "rec": rec})
    rows = []
    for item in sort_report_rows(items):
        model = item["model"]
        rec = item["rec"]
        figures = model_figures(rec["epoch"]["cells"], rec.get("lane_efforts") or [rec["lane_effort"]])
        rows.append(
            [
                ", ".join(rec["lanes"]),
                model,
                effort_used_label(figures, rec["lane_effort"]),
                *[
                    fmt_pct(figures[b]["performance"] if b in figures else None)
                    for b in data["epoch_benchmarks"]
                ],
                rec["epoch"]["mean_s"],
            ]
        )
    return md_table(headers, rows)


def aa_table_from_collection(data):
    headers = ["Lane(s)", "Model", "Effort", *data["aa_columns"], AA_COST_COLUMN, "Mean rank"]
    items = []
    for model, rec in data["models"].items():
        aa = rec["aa"]
        items.append({"model": model, "mean": aa["mean"] if aa else None, "rec": rec})
    rows = []
    for item in sort_report_rows(items):
        rec = item["rec"]
        aa = rec["aa"] or {}
        cols = aa.get("cols") or {}
        rows.append(
            [
                ", ".join(rec["lanes"]),
                item["model"],
                aa.get("effort") or "—",
                *[fmt_aa_value(cols.get(c)) for c in data["aa_columns"]],
                fmt_cost(aa.get("cost_usd")),
                aa.get("mean_s") or "— (n=0)",
            ]
        )
    return md_table(headers, rows)


# --- all-board model inspection (ticket 12) -----------------------------------
# Read-only evidence beside collect(). Human and JSON views expose the same
# records; HTML annotates from them. Nothing here writes policy or fetches.

def load_json_object(path):
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def load_boards():
    return (load_json_object(BOARDS_PATH).get("boards") or {})


def load_sources():
    return (load_json_object(SOURCES_PATH).get("sources") or {})


def load_reference_notes():
    """Web research and rejected sources: links, never accepted rows."""
    doc = load_json_object(SOURCES_PATH)
    notes = []
    refs = doc.get("reference_notes") or {}
    if isinstance(refs, dict):
        for name, entry in refs.items():
            if not isinstance(entry, dict):
                continue
            notes.append({
                "name": name,
                "note": entry.get("note"),
                "urls": list(entry.get("urls") or []),
                "accepted": False,
            })
    rejected = doc.get("rejected") or {}
    if isinstance(rejected, dict):
        for name, why in rejected.items():
            notes.append({
                "name": name,
                "note": why,
                "urls": [],
                "accepted": False,
            })
    cross = doc.get("cross_check_only") or {}
    if isinstance(cross, dict):
        for name, entry in cross.items():
            if not isinstance(entry, dict):
                continue
            url = entry.get("url")
            notes.append({
                "name": name,
                "note": entry.get("note"),
                "urls": [url] if url else [],
                "accepted": False,
            })
    return notes


def board_about(source, benchmark, boards=None):
    """What one board measures, quoted from its source's methodology page, with
    that page's URL; None when `assets/boards.json` has no entry, or the entry
    lacks a description or a URL (half a citation is not one)."""
    if boards is None:
        boards = load_boards()
    entry = ((boards or {}).get(source) or {}).get(benchmark)
    if not isinstance(entry, dict) or not entry.get("measures") or not entry.get("url"):
        return None
    about = {key: entry.get(key) for key in ABOUT_FIELDS}
    about["also"] = list(entry.get("also") or [])
    return about


def board_version(benchmark, extra=None):
    """A version printed on the board name, else an explicit extra, else None.

    `Terminal-Bench 2.1` and `Terminal-Bench 4.0` stay distinct; a missing
    version is left blank rather than guessed.
    """
    text = (benchmark or "").strip()
    match = BOARD_VERSION_RE.search(text)
    if match:
        return match.group(1)
    extra_text = (extra or "").strip() if extra else ""
    return extra_text or None


def board_direction(source, benchmark, boards=None):
    """higher-is-better, lower-is-better, or unknown. Never inferred."""
    about = board_about(source, benchmark, boards=boards)
    direction = (about or {}).get("direction")
    if direction in (DIRECTION_HIGHER, DIRECTION_LOWER):
        return direction
    return DIRECTION_UNKNOWN


def cost_basis(source, benchmark=None, sources=None, boards=None):
    """What a dollar on this board is. Costs are never comparable across sources."""
    about = board_about(source, benchmark, boards=boards) if benchmark else None
    if about and about.get("cost"):
        return about["cost"]
    if sources is None:
        sources = load_sources()
    cost = ((sources or {}).get(source) or {}).get("cost") or ""
    if cost == "usd_per_task":
        return "per task; not comparable across sources"
    if "display_cost" in cost or "whole" in cost.lower():
        return "whole run, not per task; not comparable across sources"
    if cost:
        return f"{cost}; not comparable across sources"
    return "cost as published; not comparable across sources"


def identity_of(published, lanes_doc, effort=None):
    """Lane model a printed name denotes, or an unresolved reason.

    Uses the catalog mapping and never guesses. Conflicting family members and
    a name nobody runs stay unresolved, with the candidates that collided.
    """
    resolved = resolve_published_model(published, lanes_doc, effort=effort)
    if resolved is not None:
        return {
            "lane_model": resolved,
            "identity": "resolved",
            "identity_reason": None,
            "candidates": [resolved],
        }
    key = catalog.normalize_name(published)
    if not key:
        return {
            "lane_model": None,
            "identity": "unresolved",
            "identity_reason": "empty published name",
            "candidates": [],
        }
    candidates = set()
    for lane in (lanes_doc.get("lanes") or {}).values():
        if not isinstance(lane, dict):
            continue
        model = lane.get("model")
        if not isinstance(model, str) or not model.strip():
            continue
        normalized = catalog.normalize_name(model)
        base, _suffix = catalog.strip_effort_suffix(normalized)
        if key in (normalized, base):
            candidates.add(model)
    ordered = sorted(candidates)
    if not ordered:
        return {
            "lane_model": None,
            "identity": "unresolved",
            "identity_reason": "no catalog model",
            "candidates": [],
        }
    if effort:
        reason = "conflicting identity: effort does not select one family member"
    else:
        reason = "conflicting identity: family members without an effort"
    return {
        "lane_model": None,
        "identity": "unresolved",
        "identity_reason": reason,
        "candidates": ordered,
    }


def inspect_targets(query, lanes_doc):
    """Catalog models the query names, and the identity of the query itself."""
    query = (query or "").strip()
    ident = identity_of(query, lanes_doc)
    models = []
    for lane in (lanes_doc.get("lanes") or {}).values():
        if not isinstance(lane, dict):
            continue
        model = lane.get("model")
        if isinstance(model, str) and model.strip() and model not in models:
            models.append(model)
    if query in models:
        return [query], ident
    qn = catalog.normalize_name(query)
    family = []
    for model in models:
        normalized = catalog.normalize_name(model)
        base, _suffix = catalog.strip_effort_suffix(normalized)
        if qn and qn in (normalized, base):
            family.append(model)
    if family:
        return family, ident
    if ident["lane_model"]:
        return [ident["lane_model"]], ident
    if ident["candidates"]:
        return list(ident["candidates"]), ident
    return [], ident


def _lanes_at(lanes_doc, model, effort):
    names = []
    for name, lane in (lanes_doc.get("lanes") or {}).items():
        if not isinstance(lane, dict):
            continue
        if lane.get("model") == model and effort_attributes(effort, lane.get("effort")):
            names.append(name)
    return sorted(names)


def _attributed(ident, effort, lanes_doc):
    if ident.get("identity") != "resolved" or not ident.get("lane_model"):
        return False
    if not effort or effort_cell_key(effort) == UNKNOWN_EFFORT:
        return False
    return bool(_lanes_at(lanes_doc, ident["lane_model"], effort))


def _record_from_effort_row(row, lanes_doc, sources=None, boards=None):
    published = row.get("model")
    effort = row.get("effort")
    ident = identity_of(published, lanes_doc, effort=effort)
    source = row.get("source") or "?"
    benchmark = row.get("benchmark") or "?"
    measured = effort_cell_key(effort)
    return {
        "source": source,
        "benchmark": benchmark,
        "version": board_version(benchmark),
        "published": published,
        "effort": measured,
        "lane_model": ident["lane_model"],
        "identity": ident["identity"],
        "identity_reason": ident["identity_reason"],
        "candidates": list(ident["candidates"]),
        "lanes": _lanes_at(lanes_doc, ident["lane_model"], measured) if ident["lane_model"] else [],
        "score": as_number(row.get("score")),
        "score_unit": row.get("score_unit"),
        "cost_usd": as_number(row.get("cost_usd")),
        "cost_basis": cost_basis(source, benchmark, sources=sources, boards=boards),
        "observed": row.get("observed"),
        "url": row.get("url"),
        "provenance": row.get("provenance"),
        "uncertain": bool(row.get("uncertain")),
        "composite": bool(row.get("composite")),
        "reasons": list(row.get("reasons") or []),
        "attributed": _attributed(ident, measured, lanes_doc),
        "direction": board_direction(source, benchmark, boards=boards),
        "methodology_fetched": (board_about(source, benchmark, boards=boards) or {}).get("fetched"),
        "absent": False,
        "row": row,
    }


def _record_from_epoch_row(row, lanes_doc, sources=None, boards=None):
    published = row.get("model") or row.get("slug")
    effort = row.get("effort")
    slug = row.get("slug") or ""
    ident = identity_of(published, lanes_doc, effort=effort)
    if ident["identity"] != "resolved":
        matched = None
        slug_candidates = []
        for lane in (lanes_doc.get("lanes") or {}).values():
            model = (lane or {}).get("model")
            if model and model_matches_slug(model, slug) and model not in slug_candidates:
                slug_candidates.append(model)
        if len(slug_candidates) == 1:
            matched = slug_candidates[0]
        elif len(slug_candidates) > 1:
            ident = {
                "lane_model": None,
                "identity": "unresolved",
                "identity_reason": "conflicting identity",
                "candidates": sorted(slug_candidates),
            }
        if matched is not None:
            ident = {
                "lane_model": matched,
                "identity": "resolved",
                "identity_reason": None,
                "candidates": [matched],
            }
    source = EPOCH_SOURCE
    benchmark = row.get("benchmark") or "?"
    measured = effort_cell_key(effort)
    return {
        "source": source,
        "benchmark": benchmark,
        "version": board_version(benchmark, extra=row.get("benchmark_release_date")),
        "published": published,
        "effort": measured,
        "lane_model": ident["lane_model"],
        "identity": ident["identity"],
        "identity_reason": ident["identity_reason"],
        "candidates": list(ident["candidates"]),
        "lanes": _lanes_at(lanes_doc, ident["lane_model"], measured) if ident["lane_model"] else [],
        "score": as_number(row.get("performance")),
        "score_unit": None,
        "cost_usd": None,
        "cost_basis": "Epoch CSV has no cost column; not comparable across sources",
        "observed": row.get("date") or None,
        "url": EPOCH_URL,
        "provenance": row.get("source") or "unlabelled",
        "uncertain": False,
        "composite": False,
        "reasons": [],
        "attributed": _attributed(ident, measured, lanes_doc),
        "direction": board_direction(source, benchmark, boards=boards),
        "methodology_fetched": (board_about(source, benchmark, boards=boards) or {}).get("fetched"),
        "absent": False,
        "row": row,
        "slug": slug,
    }


def _assign_standing(records):
    """Within-board standing over the loaded snapshot. Unknown direction stays unknown."""
    groups = defaultdict(list)
    for rec in records:
        groups[(rec.get("source"), rec.get("benchmark"), rec.get("version"))].append(rec)
    for (source, benchmark, version), group in groups.items():
        scored = [r for r in group if r.get("score") is not None]
        n = len(scored)
        board = f"{source} / {benchmark}" + (f" {version}" if version else "")
        scope = f"loaded snapshot, {board}"
        direction = group[0].get("direction") or DIRECTION_UNKNOWN if group else DIRECTION_UNKNOWN
        # one board, one metadata; a stranger board stays unknown
        if any(r.get("direction") != direction for r in group):
            direction = DIRECTION_UNKNOWN
        if direction not in (DIRECTION_HIGHER, DIRECTION_LOWER):
            standing = {
                "rank": None,
                "tied": False,
                "n": n,
                "direction": DIRECTION_UNKNOWN,
                "scope": scope,
            }
            for rec in group:
                rec["standing"] = dict(standing)
            continue
        scores = {}
        for rec in scored:
            value = rec["score"]
            scores[id(rec)] = value if direction == DIRECTION_HIGHER else -value
        ranks = rank_by_score(scores)
        by_score = defaultdict(int)
        for rec in scored:
            by_score[rec["score"]] += 1
        for rec in group:
            if rec.get("score") is None:
                rec["standing"] = {
                    "rank": None,
                    "tied": False,
                    "n": n,
                    "direction": direction,
                    "scope": scope,
                }
                continue
            rec["standing"] = {
                "rank": ranks.get(id(rec)),
                "tied": by_score[rec["score"]] > 1,
                "n": n,
                "direction": direction,
                "scope": scope,
            }


def evidence_records(effort_rows, lanes_doc):
    """One evidence record per accepted mixed-source row, standing assigned."""
    sources = load_sources()
    boards = load_boards()
    records = []
    for row in effort_rows or []:
        if not isinstance(row, dict):
            continue
        records.append(_record_from_effort_row(row, lanes_doc, sources=sources, boards=boards))
    _assign_standing(records)
    return records


def epoch_records(epoch_csv, lanes_doc):
    """Epoch CSV rows as evidence records. Requires a local path; never fetches."""
    if not epoch_csv:
        return []
    sources = load_sources()
    boards = load_boards()
    records = [
        _record_from_epoch_row(row, lanes_doc, sources=sources, boards=boards)
        for row in load_epoch(epoch_csv)
    ]
    _assign_standing(records)
    return records


def _public_record(rec):
    return {k: v for k, v in rec.items() if k != "row"}


def _record_matches_query(rec, query, targets):
    if rec.get("lane_model") and rec["lane_model"] in targets:
        return True
    if set(rec.get("candidates") or ()).intersection(targets):
        return True
    qn = catalog.normalize_name(query)
    if qn and catalog.normalize_name(rec.get("published")) == qn:
        return True
    slug = rec.get("slug")
    if slug:
        for model in targets or ():
            if model_matches_slug(model, slug):
                return True
        if query and model_matches_slug(query, slug):
            return True
    return False


def _absent_for_family(all_recs, family_recs, targets):
    """Boards present in the loaded snapshot that this family has no row on."""
    snapshot = []
    for rec in all_recs:
        key = (rec.get("source"), rec.get("benchmark"), rec.get("version"))
        if key not in snapshot:
            snapshot.append(key)
    have = {(r.get("source"), r.get("benchmark"), r.get("version")) for r in family_recs}
    absent = []
    for source, benchmark, version in snapshot:
        if (source, benchmark, version) in have:
            continue
        sample = next(r for r in all_recs
                      if r.get("source") == source and r.get("benchmark") == benchmark
                      and r.get("version") == version)
        absent.append({
            "source": source,
            "benchmark": benchmark,
            "version": version,
            "models": list(targets),
            "absent": True,
            "absent_reason": "no row for this model on this board in the loaded snapshot",
            "cost_basis": sample.get("cost_basis"),
            "direction": sample.get("direction"),
            "observed": sample.get("observed"),
            "methodology_fetched": sample.get("methodology_fetched"),
            "standing": {
                "rank": None,
                "tied": False,
                "n": (sample.get("standing") or {}).get("n"),
                "direction": sample.get("direction") or DIRECTION_UNKNOWN,
                "scope": (sample.get("standing") or {}).get("scope"),
            },
        })
    return absent


def inspect_model(query, lanes_doc, effort_rows=None, epoch_csv=None):
    """Read-only all-board inspection. Never fetches; never writes policy."""
    effort_recs = evidence_records(effort_rows, lanes_doc) if effort_rows is not None else []
    epoch_recs = epoch_records(epoch_csv, lanes_doc) if epoch_csv else []
    # standing stays per source; combining lists would mix Epoch with accepted
    # rows of the same printed board name, so they stay separate snapshots
    all_recs = effort_recs + epoch_recs
    targets, query_identity = inspect_targets(query, lanes_doc)
    family_recs = [r for r in all_recs if _record_matches_query(r, query, targets)]
    lane_view = []
    for name, lane in (lanes_doc.get("lanes") or {}).items():
        if not isinstance(lane, dict) or lane.get("model") not in targets:
            continue
        lane_effort = lane.get("effort")
        attributed = [
            _public_record(r) for r in family_recs
            if r.get("attributed")
            and r.get("lane_model") == lane.get("model")
            and effort_attributes(r.get("effort"), lane_effort)
        ]
        lane_view.append({
            "lane": name,
            "model": lane.get("model"),
            "effort": lane_effort,
            "tier": lane.get("tier"),
            "enabled": lane.get("enabled", True),
            "records": attributed,
        })
    return {
        "query": query,
        "query_identity": query_identity,
        "family": {
            "models": list(targets),
            "lanes": [row["lane"] for row in lane_view],
        },
        "lane_view": lane_view,
        "family_view": [_public_record(r) for r in family_recs],
        "unresolved": [_public_record(r) for r in family_recs if r.get("identity") != "resolved"],
        "absent": _absent_for_family(all_recs, family_recs, targets),
        "references": load_reference_notes(),
        "fetched": False,
        "inputs": {
            "effort_rows": effort_rows is not None,
            "epoch_csv": bool(epoch_csv),
        },
    }


def _fmt_standing(standing):
    if not standing:
        return "standing unknown"
    direction = standing.get("direction") or DIRECTION_UNKNOWN
    rank = standing.get("rank")
    n = standing.get("n")
    tied = " tied" if standing.get("tied") else ""
    scope = standing.get("scope") or "loaded snapshot"
    if direction == DIRECTION_UNKNOWN or rank is None:
        return f"standing unknown ({direction}; n={n}; {scope})"
    return f"rank {rank}/{n} {direction}{tied}; {scope}"


def format_inspection(doc):
    """Human-readable view of the same records `--json` prints."""
    query = doc.get("query") or ""
    family = doc.get("family") or {}
    lines = [
        f"# Model inspection: {query}",
        "",
        "Read-only. No source was fetched. Inspection does not change Tier, Order or carry.",
        "",
        "## Family",
        "",
        f"- catalog models: {', '.join(family.get('models') or []) or 'none'}",
        f"- lanes: {', '.join(family.get('lanes') or []) or 'none'}",
        f"- query identity: {(doc.get('query_identity') or {}).get('identity')}"
        + (f" ({(doc.get('query_identity') or {}).get('identity_reason')})"
           if (doc.get("query_identity") or {}).get("identity_reason") else ""),
        "",
        "## Lane view",
        "",
    ]
    lane_view = doc.get("lane_view") or []
    if not lane_view:
        lines.append("No catalog lane for this query.")
        lines.append("")
    for lane in lane_view:
        enabled = "carried" if lane.get("enabled") is not False else "off"
        lines.append(f"### {lane.get('lane')} ({lane.get('effort')}, {enabled})")
        lines.append("")
        recs = lane.get("records") or []
        if not recs:
            lines.append("No attributed row at this lane's effort.")
            lines.append("")
            continue
        headers = ["source", "board", "version", "score", "standing", "cost", "cost basis",
                   "observed", "provenance"]
        rows = []
        for rec in recs:
            rows.append([
                str(rec.get("source") or "—"),
                str(rec.get("benchmark") or "—"),
                str(rec.get("version") or "—"),
                "—" if rec.get("score") is None else str(rec.get("score")),
                _fmt_standing(rec.get("standing")),
                fmt_cost(rec.get("cost_usd")),
                str(rec.get("cost_basis") or "—"),
                str(rec.get("observed") or "—"),
                str(rec.get("provenance") or "—")
                + (" uncertain" if rec.get("uncertain") else ""),
            ])
        lines.append(md_table(headers, rows))
        lines.append("")
    lines.extend(["## Family view (every measured effort)", ""])
    family_view = doc.get("family_view") or []
    if not family_view:
        if not doc.get("inputs", {}).get("effort_rows") and not doc.get("inputs", {}).get("epoch_csv"):
            lines.append("No accepted rows or Epoch CSV given.")
        else:
            lines.append("No row in the loaded snapshot names this model.")
        lines.append("")
    else:
        headers = ["source", "board", "version", "published", "effort", "lane model",
                   "attributed", "score", "standing", "cost", "cost basis", "observed",
                   "provenance", "uncertainty", "source link"]
        rows = []
        for rec in family_view:
            ident = rec.get("lane_model") or rec.get("identity_reason") or "unresolved"
            rows.append([
                str(rec.get("source") or "—"),
                str(rec.get("benchmark") or "—"),
                str(rec.get("version") or "—"),
                str(rec.get("published") or "—"),
                str(rec.get("effort") or "—"),
                str(ident),
                "yes" if rec.get("attributed") else "no",
                "—" if rec.get("score") is None else str(rec.get("score")),
                _fmt_standing(rec.get("standing")),
                fmt_cost(rec.get("cost_usd")),
                str(rec.get("cost_basis") or "—"),
                str(rec.get("observed") or "—"),
                str(rec.get("provenance") or "—"),
                ("uncertain" if rec.get("uncertain") else "not flagged")
                + (": " + "; ".join(rec.get("reasons") or []) if rec.get("reasons") else ""),
                str(rec.get("url") or "—"),
            ])
        lines.append(md_table(headers, rows))
        lines.append("")
    unresolved = doc.get("unresolved") or []
    lines.extend(["## Unresolved identity", ""])
    if not unresolved:
        lines.append("- none")
    else:
        for rec in unresolved:
            names = ", ".join(rec.get("candidates") or [])
            extra = f" (candidates: {names})" if names else ""
            lines.append(
                f"- {rec.get('published')} on {rec.get('source')} / {rec.get('benchmark')}: "
                f"{rec.get('identity_reason')}{extra}"
            )
    lines.append("")
    absent = doc.get("absent") or []
    lines.extend(["## Absent rows", ""])
    if not absent:
        lines.append("- none")
    else:
        for rec in absent:
            version = f" {rec.get('version')}" if rec.get("version") else ""
            lines.append(
                f"- {rec.get('source')} / {rec.get('benchmark')}{version}: "
                f"{rec.get('absent_reason')}"
            )
    lines.append("")
    lines.extend(["## References (not accepted rows)", ""])
    refs = doc.get("references") or []
    if not refs:
        lines.append("- none")
    else:
        for ref in refs:
            urls = "; ".join(ref.get("urls") or [])
            suffix = f" {urls}" if urls else ""
            lines.append(f"- {ref.get('name')}: {ref.get('note')}{suffix}")
    lines.append("")
    return "\n".join(lines)


def run_model(args):
    """Inspect one model. Stdout only; does not write the catalog or fetch."""
    config_dir = os.path.expanduser(args.config_dir or catalog.CONFIG_DIR)
    cat = catalog.load_catalog(config_dir=config_dir)
    effort_rows = load_effort_rows(args.effort_rows) if args.effort_rows else None
    doc = inspect_model(
        args.model,
        {"lanes": cat["lanes"]},
        effort_rows=effort_rows,
        epoch_csv=args.epoch_csv,
    )
    if args.json:
        print(json.dumps(doc, indent=2, ensure_ascii=False))
    else:
        text = format_inspection(doc)
        sys.stdout.write(text if text.endswith("\n") else text + "\n")
    return 0


def run(args):
    config_dir = os.path.expanduser(args.config_dir or catalog.CONFIG_DIR)
    out_dir = os.path.expanduser(args.out_dir or DEFAULT_OUT_DIR)
    date = args.date or utc_today()

    cat = catalog.load_catalog(config_dir=config_dir)
    effort_rows = load_effort_rows(args.effort_rows)
    data = collect(
        {"lanes": cat["lanes"]},
        epoch_csv=args.epoch_csv,
        effort_rows=effort_rows,
    )
    text = format_collection(data, effort_rows=effort_rows, date=date)

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(os.path.abspath(out_dir), f"{date}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    return out_path


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "model":
        parser = argparse.ArgumentParser(
            prog="bench.py model",
            description=(
                "Read-only all-board inspection of one model. "
                "Never fetches; never writes Tier, Order or carry."
            ),
        )
        parser.add_argument("model", help="catalog model, published name, or family")
        parser.add_argument("--config-dir", default=None, help="directory holding lanes.json")
        parser.add_argument("--effort-rows", action="append", default=[],
                            help="rows effort.py accepted; repeat for several files")
        parser.add_argument("--epoch-csv", default=None, help="local Epoch CSV; never fetched")
        parser.add_argument("--json", action="store_true", help="print the same records as JSON")
        args = parser.parse_args(argv[1:])
        try:
            return run_model(args)
        except CatalogError as e:
            sys.stderr.write(f"bench: {e}\n")
            sys.exit(1)
        except BenchError as e:
            sys.stderr.write(f"bench: {e}\n")
            sys.exit(1)
    parser = argparse.ArgumentParser(
        prog="bench.py",
        description=(
            "Benchmark ranking report for the human's tier decisions. "
            "Never read by routing. `bench.py model MODEL` inspects one model "
            "without fetching."
        ),
    )
    parser.add_argument("--config-dir", default=None, help="directory holding lanes.json")
    parser.add_argument("--out-dir", default=None, help="directory for <date>.md")
    parser.add_argument("--date", default=None, help="report date YYYY-MM-DD (UTC today)")
    parser.add_argument("--epoch-csv", default=None, help="local Epoch CSV; skip the fetch")
    parser.add_argument("--effort-rows", action="append", default=[],
                        help="rows effort.py accepted (the aa rows are read); repeat for several files")
    args = parser.parse_args(argv)
    try:
        path = run(args)
    except CatalogError as e:
        sys.stderr.write(f"bench: {e}\n")
        sys.exit(1)
    except BenchError as e:
        sys.stderr.write(f"bench: {e}\n")
        sys.exit(1)
    print(f"bench: wrote {path}")
    return 0


if __name__ == "__main__":
    main()
