#!/usr/bin/env python3
"""rank.py — deterministic quota-aware lane ranking for delegate.

Ranks execution lanes from the JSON catalog (lanes.json and routing.json)
for a given task class, taking into account model tier requirements,
subscription meter gate thresholds, harness CLI availability, and pacing.

The selection rule:
  1. Determine task tier requirement: need = routing.classTier[class].
  2. Filter eligible lanes:
       tier >= need,
       meter gate passed: meter r is None (unknown) or r >= routing.gate,
       harness CLI is present (found in PATH or specified via --harnesses).
     Vetoed lanes fail one or more conditions (reported in precedence order:
     ceiling, gate, cli).
  3. Sort eligible lanes by:
       tier ascending,
       pace descending,
       lane name ascending,
       lanes with unknown pace (None) sorted last.
     Two lanes alike on tier and pace are equivalent, so the tie falls to lane
     name: an arbitrary factor, chosen only to make the pick deterministic.
  4. Initial pick is eligible[0].
  5. Steal rule: evaluate remaining eligible lanes in sorted order. If a lane's
     pace exceeds the current pick's pace by at least routing.margin, it steals
     the pick:
       for L in eligible[1:]:
           if pace(L) >= pace(pick) + routing.margin: pick = L
     Lanes with unknown pace never steal and are never stolen from.

Reason vocabulary (exactly one per lane):
  - pick: chosen lane when it is eligible[0] (or when all meters unknown)
  - stolen by pace: <pace> >= <pick0 pace> + <margin>: steal rule moved pick
  - eligible: any other eligible lane
  - unknown meter, sorted last: eligible lane with unknown pace (overrides eligible)
  - vetoed: ceiling (tier <t> < need <n>)
  - vetoed: gate (r <pct> < <gate pct>)
  - vetoed: cli absent (<harness>)

CLI forms:
  rank.py <class> [--cwd DIR] [--config-dir DIR] [--meters FILE] [--harnesses a,b,c] [--json]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import catalog
from catalog import CatalogError, CLASSES, HARNESSES, load_catalog


def rank(cls, cat, meters, present, effort=None):
    """Rank catalog lanes for a given class.

    cat: dict from catalog.load_catalog
    meters: usage document dict (or {})
    present: set of harness names
    effort: optional effort override (unused in base ranking rule)
    """
    routing = cat.get("routing", {})
    class_tier = routing.get("classTier", {})
    if cls not in class_tier and cls not in CLASSES:
        raise ValueError(f"unknown class '{cls}'; must be one of {', '.join(CLASSES)}")

    need = class_tier.get(cls)
    margin = routing.get("margin", 0.2)
    gate = routing.get("gate", 0.1)

    meter_map = {}
    if isinstance(meters, dict):
        lanes_list = meters.get("lanes")
        if isinstance(lanes_list, list):
            for entry in lanes_list:
                if isinstance(entry, dict) and "lane" in entry:
                    meter_map[entry["lane"]] = entry
        else:
            meter_map = meters

    present_set = set(present) if present else set()
    lanes = cat.get("lanes", {})

    eligible_rows = []
    vetoed_rows = []

    for lane_name, lane_def in lanes.items():
        meter_name = lane_def.get("meter")
        rec = meter_map.get(meter_name) if meter_name else None
        if rec and isinstance(rec, dict):
            r = rec.get("r")
            pace = rec.get("pace")
            remaining_weekly = rec.get("remaining_weekly")
            meter_status = rec.get("status", "unknown")
        else:
            r = None
            pace = None
            remaining_weekly = None
            meter_status = "unknown"

        tier = lane_def.get("tier")
        harness = lane_def.get("harness")
        model = lane_def.get("model")
        lane_effort = lane_def.get("effort")

        veto_reason = None
        if tier is not None and need is not None and tier < need:
            veto_reason = f"vetoed: ceiling (tier {tier} < need {need})"
        elif r is not None and r < gate:
            r_pct = f"{int(round(r * 100)):d}%"
            gate_pct = f"{int(round(gate * 100)):d}%"
            veto_reason = f"vetoed: gate (r {r_pct} < {gate_pct})"
        elif harness not in present_set:
            veto_reason = f"vetoed: cli absent ({harness})"

        row = {
            "lane": lane_name,
            "harness": harness,
            "model": model,
            "effort": lane_effort,
            "tier": tier,
            "meter": meter_name,
            "pace": pace,
            "r": r,
            "remaining_weekly": remaining_weekly,
            "meter_status": meter_status,
            "eligible": veto_reason is None,
            "pick": False,
            "reason": veto_reason or "",
        }

        if veto_reason is None:
            eligible_rows.append(row)
        else:
            vetoed_rows.append(row)

    def sort_key(item):
        unknown = 1 if item["pace"] is None else 0
        t = item["tier"] if item["tier"] is not None else 99
        p = item["pace"] if item["pace"] is not None else 0.0
        return (unknown, t, -p, item["lane"])

    eligible_rows.sort(key=sort_key)

    if eligible_rows:
        pick_row = eligible_rows[0]
        beaten_pace = None
        for r in eligible_rows[1:]:
            if r["pace"] is not None and pick_row["pace"] is not None:
                if r["pace"] >= pick_row["pace"] + margin:
                    beaten_pace = pick_row["pace"]
                    pick_row = r

        for r in eligible_rows:
            if r is pick_row:
                r["pick"] = True
                if beaten_pace is not None:
                    r["reason"] = f"stolen by pace: {r['pace']} >= {beaten_pace} + {margin}"
                else:
                    r["reason"] = "pick"
            else:
                r["pick"] = False
                if r["pace"] is None:
                    r["reason"] = "unknown meter, sorted last"
                else:
                    r["reason"] = "eligible"

        ordered_eligible = [pick_row] + [r for r in eligible_rows if r is not pick_row]
    else:
        ordered_eligible = []

    return ordered_eligible + vetoed_rows


def format_rows(rows):
    if not rows:
        return []
    max_lane_w = max(len(r["lane"]) for r in rows)
    max_model_w = max(len(r["model"]) for r in rows)
    lines = []
    for idx, r in enumerate(rows, 1):
        pace_str = "   ?" if r["pace"] is None else f"{r['pace']:.2f}"
        r_str = "  ?" if r["r"] is None else f"{int(round(r['r'] * 100)):3d}%"
        status_str = f"{r['meter_status']:<8}"
        lane_padded = f"{r['lane']:<{max_lane_w}}"
        model_padded = f"{r['model']:<{max_model_w}}"
        line = (
            f"{idx}. {lane_padded} "
            f"tier={r['tier']} "
            f"pace={pace_str} "
            f"r={r_str} "
            f"{status_str} "
            f"{model_padded}   "
            f"{r['reason']}"
        )
        lines.append(line)
    return lines


def run_usage():
    try:
        res = subprocess.run(
            [sys.executable, os.path.join(HERE, "usage.py")],
            capture_output=True,
            text=True,
            timeout=90,
        )
        return json.loads(res.stdout)
    except Exception:
        return {}


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="rank.py",
        description="Rank execution lanes for a class."
    )
    parser.add_argument("cls", metavar="class", help=f"class to rank: {', '.join(CLASSES)}")
    parser.add_argument("--cwd", default=None, help="working directory to find git root from")
    parser.add_argument("--config-dir", default=None, help="config directory containing lanes.json and routing.json")
    parser.add_argument("--meters", default=None, help="path to usage document JSON file")
    parser.add_argument("--harnesses", default=None, help="comma-separated list of present harnesses")
    parser.add_argument("--json", action="store_true", help="output as JSON")

    args = parser.parse_args(argv)

    if args.cls not in CLASSES:
        sys.stderr.write(f"rank: unknown class '{args.cls}'; must be one of {', '.join(CLASSES)}\n")
        sys.exit(2)

    try:
        cat = load_catalog(cwd=args.cwd, config_dir=args.config_dir)
    except CatalogError as e:
        sys.stderr.write(f"rank: {e}\n")
        sys.exit(1)

    if args.meters:
        try:
            with open(args.meters, "r", encoding="utf-8") as f:
                meters_doc = json.load(f)
        except Exception:
            meters_doc = {}
    else:
        meters_doc = run_usage()

    if args.harnesses is not None:
        present = set(h.strip() for h in args.harnesses.split(",") if h.strip())
    else:
        present = {h for h in HARNESSES if shutil.which(h)}

    rows = rank(args.cls, cat, meters_doc, present)
    has_pick = bool(rows and rows[0]["pick"])

    routing = cat["routing"]
    need = routing["classTier"][args.cls]
    margin = routing["margin"]
    gate = routing["gate"]

    if args.json:
        out = {
            "class": args.cls,
            "need": need,
            "margin": margin,
            "gate": gate,
            "pick": rows[0]["lane"] if has_pick else None,
            "rows": rows,
        }
        sys.stdout.write(json.dumps(out, indent=2) + "\n")
        sys.exit(0 if has_pick else 1)

    if not has_pick:
        print(f"STOP: no lane eligible for {args.cls}")
        for line in format_rows(rows):
            print(line)
        sys.exit(1)

    project_file = cat.get("files", {}).get("project")
    override_str = project_file if project_file else "none"
    gate_pct = f"{int(round(gate * 100))}%"
    print(f"# {args.cls}  need=tier {need}  margin={margin}  gate={gate_pct}  (routing: global; project override: {override_str})")
    for line in format_rows(rows):
        print(line)
    sys.exit(0)


if __name__ == "__main__":
    main()
