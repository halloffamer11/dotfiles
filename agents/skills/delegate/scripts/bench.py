#!/usr/bin/env python3
"""bench.py — benchmark ranking report for the human who sets lane tiers.

Evidence for the human's tier decisions; never read by routing
or any other script, skill, or hook.

Sources:
  Epoch AI, Benchmarking Hub, https://epoch.ai/data/eci_benchmarks.csv, CC-BY 4.0
  Artificial Analysis, https://artificialanalysis.ai, free API (attribution required)

  python3 bench.py [--config-dir DIR] [--out-dir DIR] [--date YYYY-MM-DD]
                   [--epoch-csv FILE] [--aa-json FILE] [--key-file FILE]
"""
import argparse
import csv
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

import catalog
from catalog import CatalogError

EPOCH_URL = "https://epoch.ai/data/eci_benchmarks.csv"
AA_URL = "https://artificialanalysis.ai/api/v2/language/models/free"
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
LANE_EFFORT_ORDER = ("xhigh", "high", "medium", "low")
MODEL_EFFORT_SUFFIXES = (
    ("-xhigh", "xhigh"),
    ("-high", "high"),
    ("-medium", "medium"),
    ("-low", "low"),
)
AA_COLUMNS = (
    ("Coding Index", ("coding-index",)),
    ("Agentic Index", ("agentic-index",)),
    ("Terminal-Bench", ("terminal-bench",)),
    ("Output tokens/s", ("median-output-tokens-per-second", "output-tokens-per-second")),
)
NORM_SEP = re.compile(r"[-_. ]+")


class BenchError(Exception):
    """Fatal Epoch or catalog-adjacent failure; printed as bench: <msg>."""


def utc_today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def normalize_name(value):
    if value is None:
        return ""
    text = NORM_SEP.sub("-", str(value).strip().lower()).strip("-")
    return text


def strip_effort_suffix(model):
    for suffix, effort in MODEL_EFFORT_SUFFIXES:
        if model.endswith(suffix):
            return model[: -len(suffix)], effort
    return model, None


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
    for effort in LANE_EFFORT_ORDER:
        if effort in efforts:
            return effort
    return efforts[0]


def model_matches_slug(catalog_model, slug):
    if slug == catalog_model:
        return True
    base, _suffix_effort = strip_effort_suffix(catalog_model)
    return bool(base) and slug == base


def aa_match_info(catalog_model, aa_name):
    n_aa = normalize_name(aa_name)
    n_model = normalize_name(catalog_model)
    if not n_aa or not n_model:
        return False, False, None
    cat_base, _ = strip_effort_suffix(catalog_model)
    n_base = normalize_name(cat_base)

    if n_aa == n_model or (n_base and n_aa == n_base):
        return True, True, None

    aa_base, aa_effort = strip_effort_suffix(n_aa)
    if aa_effort is not None:
        if aa_base == n_model or (n_base and aa_base == n_base):
            return True, False, aa_effort

    return False, False, None


def aa_name_matches(catalog_model, aa_name):
    matches, _, _ = aa_match_info(catalog_model, aa_name)
    return matches


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
    if score is None:
        return "—"
    if abs(score - round(score)) < 1e-9:
        return str(int(round(score)))
    return f"{score:.1f}"


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
    for effort in LANE_EFFORT_ORDER:
        if effort in lane_efforts and effort in available:
            return effort
    for effort in lane_efforts:
        if effort in available:
            return effort
    for effort in EFFORT_FALLBACK:
        if effort in available:
            return effort
    return None


def select_epoch_cell(rows, lane_efforts):
    if not rows:
        return None
    by_effort = defaultdict(list)
    for row in rows:
        by_effort[row["effort"]].append(row)
    chosen = choose_effort(by_effort, lane_efforts)
    if chosen is None:
        best = max(rows, key=lambda r: (r["performance"], r["source"]))
        chosen = best["effort"]
        candidates = [r for r in rows if r["effort"] == chosen]
    else:
        candidates = by_effort[chosen]
    best = max(candidates, key=lambda r: r["performance"])
    scores = sorted({c["performance"] for c in candidates}, reverse=True)
    dup_pairs = None
    if len(scores) > 1:
        dup_pairs = []
        seen = set()
        for cand in sorted(candidates, key=lambda r: (-r["performance"], r["source"])):
            key = (cand["performance"], cand["source"])
            if key in seen:
                continue
            seen.add(key)
            dup_pairs.append(key)
    return {
        "performance": best["performance"],
        "effort": chosen,
        "source": best["source"],
        "duplicates": dup_pairs,
    }


def effort_used_label(cells, lane_effort):
    used = [(bench, cells[bench]["effort"]) for bench in EPOCH_BENCHMARKS if cells.get(bench)]
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
    for model, rec in models.items():
        lane_efforts = rec["efforts"]
        cells = {}
        for bench in EPOCH_BENCHMARKS:
            selected = select_epoch_cell(matched.get((model, bench), []), lane_efforts)
            if selected:
                cells[bench] = selected
                scores_by_bench[bench][model] = selected["performance"]
        cells_by_model[model] = cells
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
                "mean": mean,
                "mean_s": mean_s,
                "gap": mean is None,
            }
        )
    items = sort_report_rows(items)
    headers = [
        "Lane(s)",
        "Model",
        "Effort used",
        *EPOCH_BENCHMARKS,
        "Mean rank",
    ]
    rows = []
    for item in items:
        cells = item["cells"]
        rows.append(
            [
                item["lanes"],
                item["model"],
                effort_used_label(cells, item["lane_effort"]),
                *[fmt_pct(cells[b]["performance"] if b in cells else None) for b in EPOCH_BENCHMARKS],
                item["mean_s"],
            ]
        )
    return items, md_table(headers, rows)


def load_key(key_file):
    if not key_file:
        return None, "key file missing"
    path = os.path.abspath(os.path.expanduser(key_file))
    if not os.path.isfile(path):
        return None, "key file missing"
    try:
        with open(path, "r", encoding="utf-8") as f:
            line = f.readline()
    except OSError as e:
        return None, f"cannot read key file: {e}"
    key = line.strip()
    if not key:
        return None, "empty key file"
    return key, None


def extract_aa_models(doc):
    if isinstance(doc, list) and all(isinstance(x, dict) for x in doc):
        return doc
    if isinstance(doc, dict):
        for key in ("data", "models"):
            value = doc.get(key)
            if isinstance(value, list) and all(isinstance(x, dict) for x in value):
                return value
    return []


def aa_model_name(obj):
    for key in ("slug", "id", "name"):
        if key in obj and obj[key] not in (None, ""):
            return str(obj[key])
    return ""


def iter_aa_fields(obj):
    if not isinstance(obj, dict):
        return
    for item in obj.items():
        yield item
    for value in obj.values():
        if isinstance(value, dict):
            yield from value.items()


def key_matches_needles(norm_key, needles):
    return any(needle in norm_key for needle in needles)


def extract_aa_columns(obj):
    found = {}
    keys_used = {}
    for key, value in iter_aa_fields(obj):
        number = as_number(value)
        if number is None:
            continue
        norm = normalize_name(key)
        for col, needles in AA_COLUMNS:
            if col in found:
                continue
            if key_matches_needles(norm, needles):
                found[col] = number
                keys_used[col] = str(key)
    return found, keys_used


def load_aa_json_text(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON: {e}") from e


def load_aa(aa_json, key_file):
    if aa_json:
        path = os.path.abspath(os.path.expanduser(aa_json))
        try:
            text = read_text_file(path)
            doc = load_aa_json_text(text)
        except OSError as e:
            return None, f"cannot read AA JSON: {e}"
        except ValueError as e:
            return None, str(e)
        return doc, None
    key, err = load_key(key_file)
    if err:
        return None, err
    try:
        raw = fetch_bytes(AA_URL, headers={"x-api-key": key})
        doc = json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return None, "HTTP 401"
        return None, f"HTTP {e.code}"
    except Exception as e:
        return None, str(e)
    return doc, None


def build_aa_section(models, doc):
    aa_models = extract_aa_models(doc)
    first_keys = list(aa_models[0].keys()) if aa_models else []
    keys_used = {}
    candidates_by_model = defaultdict(list)
    for idx, obj in enumerate(aa_models):
        name = aa_model_name(obj)
        cols, used = extract_aa_columns(obj)
        for col, key in used.items():
            keys_used.setdefault(col, key)
        for model in models:
            matches, is_exact, effort = aa_match_info(model, name)
            if matches:
                candidates_by_model[model].append(
                    {
                        "obj": obj,
                        "name": name,
                        "cols": cols,
                        "is_exact": is_exact,
                        "effort": effort,
                        "index": idx,
                    }
                )

    matched = {}
    matched_effort = {}
    for model, rec in models.items():
        cands = candidates_by_model.get(model, [])
        if not cands:
            continue
        lane_effort = lane_effort_of(rec)
        lane_idx = (
            LANE_EFFORT_ORDER.index(lane_effort)
            if lane_effort in LANE_EFFORT_ORDER
            else 0
        )

        def cand_key(c):
            if c["is_exact"]:
                return (0, 0, 0, c["name"], c["index"])
            e = c["effort"]
            e_idx = (
                LANE_EFFORT_ORDER.index(e)
                if e in LANE_EFFORT_ORDER
                else 99
            )
            dist = abs(e_idx - lane_idx)
            return (1, dist, e_idx, c["name"], c["index"])

        best = min(cands, key=cand_key)
        matched[model] = best["cols"]
        matched_effort[model] = best["effort"]

    col_names = [c[0] for c in AA_COLUMNS]
    scores_by_col = {c: {} for c in col_names}
    for model, cols in matched.items():
        for col in col_names:
            if col in cols:
                scores_by_col[col][model] = cols[col]
    ranks_by_col = {c: rank_by_score(scores_by_col[c]) for c in col_names}
    items = []
    for model, rec in models.items():
        cols = matched.get(model, {})
        mean, mean_s = mean_rank_display(ranks_by_col, model)
        items.append(
            {
                "model": model,
                "lanes": ", ".join(sorted(rec["lanes"])),
                "lane_effort": lane_effort_of(rec),
                "lane_efforts": rec["efforts"],
                "cols": cols,
                "mean": mean,
                "mean_s": mean_s,
                "present": model in matched,
                "effort": matched_effort.get(model),
            }
        )
    items = sort_report_rows(items)
    headers = ["Lane(s)", "Model", *col_names, "Mean rank"]
    rows = []
    for item in items:
        cols = item["cols"]
        rows.append(
            [
                item["lanes"],
                item["model"],
                *[fmt_aa_value(cols.get(c)) for c in col_names],
                item["mean_s"],
            ]
        )
    used_names = [keys_used[c] for c in col_names if c in keys_used]
    return items, md_table(headers, rows), used_names, first_keys


def build_notes(models, epoch_items, aa_items, aa_skipped, aa_keys_used, aa_first_keys):
    notes = []
    epoch_by_model = {item["model"]: item for item in epoch_items}
    aa_by_model = {item["model"]: item for item in (aa_items or [])}
    for model in models:
        if epoch_by_model[model]["gap"]:
            notes.append(f"{model} absent from Epoch AI")
        if aa_skipped is None and not aa_by_model[model]["present"]:
            notes.append(f"{model} absent from Artificial Analysis")
    for item in epoch_items:
        model = item["model"]
        lane_efforts = set(item["lane_efforts"])
        lane_effort = item["lane_effort"]
        for bench in EPOCH_BENCHMARKS:
            cell = item["cells"].get(bench)
            if not cell:
                continue
            if cell["effort"] not in lane_efforts:
                notes.append(
                    f"{model} {bench} used effort {cell['effort']} (lane effort {lane_effort})"
                )
            if cell["duplicates"]:
                shown = ", ".join(
                    f"{perf:.2f} ({source or 'unknown'})" for perf, source in cell["duplicates"]
                )
                notes.append(f"{model} {bench} duplicate scores: {shown}")
    if aa_skipped is None:
        for item in (aa_items or []):
            if not item.get("present"):
                continue
            model = item["model"]
            lane_efforts = set(item.get("lane_efforts") or [item["lane_effort"]])
            lane_effort = item["lane_effort"]
            used_effort = item.get("effort")
            if used_effort is not None and used_effort not in lane_efforts:
                notes.append(
                    f"{model} Artificial Analysis used effort {used_effort} (lane effort {lane_effort})"
                )
        if aa_keys_used:
            notes.append("AA keys used: " + ", ".join(aa_keys_used))
        else:
            key_list = ", ".join(aa_first_keys) if aa_first_keys else "(none)"
            notes.append(
                "AA keys used: none; first model object keys: " + key_list
            )
    return notes


def render_report(
    date,
    epoch_table,
    aa_table,
    aa_skipped,
    notes,
):
    lines = [
        f"# Lane benchmark ranking {date}",
        "",
        "This report is evidence for the human's tier edits and is read by no script.",
        "",
        f"Source: Epoch AI, Benchmarking Hub, {EPOCH_URL}, CC-BY 4.0, fetched {date}",
    ]
    if aa_skipped is None:
        lines.append(
            f"Source: Artificial Analysis, https://artificialanalysis.ai, free API, fetched {date}"
        )
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


def collect(lanes_doc, epoch_csv=None, aa_json=None, key_file=None):
    """Collect benchmark data for the report and interactive consumers."""
    models = catalog_models(lanes_doc["lanes"])
    epoch_rows = load_epoch(epoch_csv)
    matched = match_epoch_rows(epoch_rows, models)
    epoch_items, _epoch_table = build_epoch_section(models, matched)

    aa_doc, aa_skipped = load_aa(aa_json, key_file)
    aa_items = None
    aa_keys_used = []
    aa_first_keys = []
    if aa_skipped is None:
        aa_items, _aa_table, aa_keys_used, aa_first_keys = build_aa_section(
            models, aa_doc
        )

    notes = build_notes(
        models, epoch_items, aa_items, aa_skipped, aa_keys_used, aa_first_keys
    )
    epoch_by_model = {item["model"]: item for item in epoch_items}
    aa_by_model = {
        item["model"]: item for item in (aa_items or [])
    }
    collected_models = {}
    for model, rec in models.items():
        epoch = epoch_by_model[model]
        aa = aa_by_model.get(model)
        collected_models[model] = {
            "lanes": sorted(rec["lanes"]),
            "lane_effort": epoch["lane_effort"],
            "epoch": {
                "cells": epoch["cells"],
                "mean": epoch["mean"],
                "mean_s": epoch["mean_s"],
            },
            "aa": None
            if aa is None
            else {
                "cols": aa["cols"],
                "mean": aa["mean"],
                "mean_s": aa["mean_s"],
            },
        }
    return {
        "models": collected_models,
        "epoch_benchmarks": list(EPOCH_BENCHMARKS),
        "aa_columns": [name for name, _needles in AA_COLUMNS],
        "aa_skipped": aa_skipped,
        "notes": notes,
    }


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
        cells = rec["epoch"]["cells"]
        rows.append(
            [
                ", ".join(rec["lanes"]),
                model,
                effort_used_label(cells, rec["lane_effort"]),
                *[
                    fmt_pct(cells[b]["performance"] if b in cells else None)
                    for b in data["epoch_benchmarks"]
                ],
                rec["epoch"]["mean_s"],
            ]
        )
    return md_table(headers, rows)


def aa_table_from_collection(data):
    headers = ["Lane(s)", "Model", *data["aa_columns"], "Mean rank"]
    items = []
    for model, rec in data["models"].items():
        aa = rec["aa"]
        items.append({"model": model, "mean": aa["mean"], "rec": rec})
    rows = []
    for item in sort_report_rows(items):
        model = item["model"]
        rec = item["rec"]
        aa = rec["aa"]
        rows.append(
            [
                ", ".join(rec["lanes"]),
                model,
                *[fmt_aa_value(aa["cols"].get(c)) for c in data["aa_columns"]],
                aa["mean_s"],
            ]
        )
    return md_table(headers, rows)


def run(args):
    config_dir = os.path.expanduser(args.config_dir or catalog.CONFIG_DIR)
    out_dir = os.path.expanduser(args.out_dir or DEFAULT_OUT_DIR)
    date = args.date or utc_today()
    key_file = args.key_file or os.path.join(config_dir, "aa-key")

    cat = catalog.load_catalog(config_dir=config_dir)
    data = collect(
        {"lanes": cat["lanes"]},
        epoch_csv=args.epoch_csv,
        aa_json=args.aa_json,
        key_file=key_file,
    )
    epoch_table = epoch_table_from_collection(data)
    aa_table = (
        aa_table_from_collection(data) if data["aa_skipped"] is None else None
    )
    text = render_report(
        date, epoch_table, aa_table, data["aa_skipped"], data["notes"]
    )

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(os.path.abspath(out_dir), f"{date}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    return out_path


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="bench.py",
        description=(
            "Benchmark ranking report for the human's tier decisions. "
            "Never read by routing."
        ),
    )
    parser.add_argument("--config-dir", default=None, help="directory holding lanes.json")
    parser.add_argument("--out-dir", default=None, help="directory for <date>.md")
    parser.add_argument("--date", default=None, help="report date YYYY-MM-DD (UTC today)")
    parser.add_argument("--epoch-csv", default=None, help="local Epoch CSV; skip the fetch")
    parser.add_argument("--aa-json", default=None, help="local AA JSON; skip the fetch and key")
    parser.add_argument("--key-file", default=None, help="AA API key file (first line)")
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
