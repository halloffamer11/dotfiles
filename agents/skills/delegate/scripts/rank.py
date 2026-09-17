#!/usr/bin/env python3
"""rank.py — deterministic Meter-aware lane ranking for delegate.

Ranks execution lanes from the JSON catalog (lanes.json and routing.json)
over an inclusive Tier range, taking into account subscription meter gate
thresholds, harness CLI availability, and pacing.  The Class-facing ``rank``
wrapper resolves its range from routing classes before calling that rule.

The selection rule:
  1. Filter eligible lanes in the supplied Tier range:
       enabled is True (defaults to True if absent),
       floor <= tier <= ceiling,
       meter gate passed: meter r is None (unknown) or r >= routing.gate,
       harness CLI is present (found in PATH or specified via --harnesses).
     Vetoed lanes fail one or more conditions (reported in precedence order:
     disabled, floor, ceiling, gate, cli).
  2. Sort eligible lanes by:
       tier ascending,
       order ascending (the lane's `order`, its place inside its tier that
         Orin sets in the setup wizard; a lane without `order` sorts after
         every lane with one),
       pace descending,
       lane name ascending,
       lanes with unknown pace (None) sorted last.
     Two lanes alike on tier, order and pace are equivalent, so the tie falls
     to lane name: an arbitrary factor, chosen only to make the pick
     deterministic. A catalog with no `order` field ranks as it did before
     ticket 28: every lane sorts as unordered, so tier and pace decide.
  3. Initial pick is eligible[0].
  4. Steal rule: evaluate remaining eligible lanes in sorted order. If a lane's
     pace exceeds the current pick's pace by at least routing.margin, it steals
     the pick:
       for L in eligible[1:]:
           if pace(L) >= pace(pick) + routing.margin: pick = L
     Lanes with unknown pace never steal and are never stolen from. Because
     `order` sorts ahead of pace, a steal can happen inside a tier: a lane
     lower in Orin's order runs when its meter is well ahead of the pick's.
     That is the load balance (ticket 28).

Reason vocabulary (exactly one per lane):
  - pick: chosen lane when it is eligible[0] (or when all meters unknown)
  - stolen by pace: <pace> >= <pick0 pace> + <margin>: steal rule moved pick
  - eligible: any other eligible lane
  - unknown meter, sorted last: eligible lane with unknown pace (overrides eligible)
  - vetoed:disabled, <lane>
  - vetoed:floor, <lane> (tier t) < <class> floor (tier f)
  - vetoed:ceiling, <lane> (tier t) > <class> ceiling (tier c)
  - vetoed:gate, <lane>: <meter> meter N% left < gate G%
  - vetoed:cli, <lane>: <harness> not on PATH

CLI forms:
  rank.py <class> [--tier N] [--cwd DIR] [--config-dir DIR] [--meters FILE] [--harnesses a,b,c] [--json]
  rank.py tiers [--cwd DIR] [--config-dir DIR] [--meters FILE] [--harnesses a,b,c] [--json]
"""
import argparse
import json
import math
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import catalog
import usage
from catalog import CatalogError, CLASSES, HARNESSES, load_catalog


def _valid_meter_number(value, *, fraction=False):
    if value is None:
        return True
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        number = float(value)
    except OverflowError:
        return False
    return math.isfinite(number) and (0 <= number <= 1 if fraction else number >= 0)


def meter_observations(document):
    """Return validated observations by Meter, or None for a malformed document.

    Accept the usage-cache envelope and the legacy bare Meter map. Invalid
    observations make the whole document unknown, consistently for every caller.
    No values are repaired and this boundary never probes a vendor.
    """
    if not isinstance(document, dict):
        return None
    if "lanes" in document:
        if not _valid_meter_number(document.get("probed_at")):
            return None
        if not isinstance(document["lanes"], list):
            return None
        observations = {}
        for entry in document["lanes"]:
            if not isinstance(entry, dict):
                return None
            name = entry.get("lane")
            if not isinstance(name, str) or not name:
                return None
            observations[name] = entry
        entries = [(entry["lane"], entry) for entry in document["lanes"]]
    else:
        observations = document
        entries = document.items()
    for name, observation in entries:
        if not isinstance(name, str) or not name or not isinstance(observation, dict):
            return None
        if not _valid_meter_number(observation.get("r"), fraction=True):
            return None
        if not _valid_meter_number(observation.get("pace")):
            return None
        if not _valid_meter_number(observation.get("remaining_weekly"), fraction=True):
            return None
        if "status" in observation and not isinstance(observation["status"], str):
            return None
    return observations


def rank_range(cat, meters, present, floor=None, ceiling=None, *, reason_label="tier"):
    """Apply the canonical selection rule to an inclusive Tier range.

    ``floor`` and ``ceiling`` are range bounds, not a Class lookup.  The
    optional ``reason_label`` keeps the existing Class-facing veto text while
    allowing another caller to describe the same range in its own terms.

    cat: dict from catalog.load_catalog
    meters: usage document dict (or {})
    present: set of harness names
    """
    if floor is not None and ceiling is not None and floor > ceiling:
        raise ValueError(f"invalid tier range [{floor}, {ceiling}]")

    routing = cat.get("routing", {})
    margin = routing.get("margin", 0.2)
    gate = routing.get("gate", 0.1)
    reason_label = reason_label or "tier"

    meter_map = meter_observations(meters) or {}

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

        lane_tier = lane_def.get("tier")
        harness = lane_def.get("harness")
        model = lane_def.get("model")
        lane_effort = lane_def.get("effort")

        veto_reason = None
        if not lane_def.get("enabled", True):
            veto_reason = f"vetoed:disabled, {lane_name}"
        elif lane_tier is not None and floor is not None and lane_tier < floor:
            veto_reason = f"vetoed:floor, {lane_name} (tier {lane_tier}) < {reason_label} floor (tier {floor})"
        elif lane_tier is not None and ceiling is not None and lane_tier > ceiling:
            veto_reason = f"vetoed:ceiling, {lane_name} (tier {lane_tier}) > {reason_label} ceiling (tier {ceiling})"
        elif r is not None and r < gate:
            r_pct = f"{int(round(r * 100)):d}%"
            gate_pct = f"{int(round(gate * 100)):d}%"
            veto_reason = f"vetoed:gate, {lane_name}: {meter_name} meter {r_pct} left < gate {gate_pct}"
        elif harness not in present_set:
            veto_reason = f"vetoed:cli, {lane_name}: {harness} not on PATH"

        row = {
            "lane": lane_name,
            "harness": harness,
            "model": model,
            "effort": lane_effort,
            "tier": lane_tier,
            "order": lane_def.get("order"),
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
        unordered = 1 if item["order"] is None else 0
        o = item["order"] if item["order"] is not None else 0
        return (unknown, t, unordered, o, -p, item["lane"])

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


def rank(cls, cat, meters, present, tier=None):
    """Rank catalog lanes for a given class.

    cat: dict from catalog.load_catalog
    meters: usage document dict (or {})
    present: set of harness names
    tier: optional floor override (must be between class floor and ceiling)
    """
    routing = cat.get("routing", {})
    classes = routing.get("classes", {})
    if cls not in classes and cls not in CLASSES:
        raise ValueError(f"unknown class '{cls}'; must be one of {', '.join(CLASSES)}")

    cls_config = classes.get(cls, {})
    floor = cls_config.get("floor")
    ceiling = cls_config.get("ceiling")

    if tier is not None:
        if floor is not None and ceiling is not None and (tier < floor or tier > ceiling):
            raise ValueError(f"tier {tier} outside [{floor}, {ceiling}] for class '{cls}'")
        floor = tier

    return rank_range(
        cat,
        meters,
        present,
        floor=floor,
        ceiling=ceiling,
        reason_label=cls,
    )


def tier_leaders(cat, meters, present):
    """Return the leader and ranked rows for each exact Tier from 1 to 4.

    Each preview delegates selection to ``rank_range`` with equal floor and
    ceiling bounds, then projects away rows from other Tiers. A leader is the
    exact-Tier preview, not the Pick for any Class range.
    """
    previews = []
    for tier in range(1, 5):
        rows = rank_range(
            cat,
            meters,
            present,
            floor=tier,
            ceiling=tier,
            reason_label=f"Tier {tier}",
        )
        rows = [row for row in rows if row["tier"] == tier]
        leader = next((row["lane"] for row in rows if row["pick"]), None)
        previews.append({"tier": tier, "leader": leader, "rows": rows})
    return previews


def format_rows(rows):
    if not rows:
        return []
    max_lane_w = max(len(r["lane"]) for r in rows)
    max_model_w = max(len(r["model"]) for r in rows)
    # the order column appears only when some lane has an order, so a catalog
    # without one prints exactly as before ticket 28
    show_order = any(r.get("order") is not None for r in rows)
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
            + (f"order={'-' if r.get('order') is None else r['order']} " if show_order else "")
            + f"pace={pace_str} "
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


def load_cached_usage(cache_path=None):
    """Read the usage cache without invoking usage.py or any vendor probe."""
    path = cache_path
    if path is None:
        path = usage.get_cache_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
        return doc if isinstance(doc, dict) else {}
    except (OSError, ValueError):
        return {}


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="rank.py",
        description="Rank execution lanes for a Class or preview all four exact Tiers."
    )
    parser.add_argument("target", metavar="class|tiers", help=f"class to rank ({', '.join(CLASSES)}) or tiers")
    parser.add_argument("--tier", type=int, default=None, help="override floor tier for this job")
    parser.add_argument("--cwd", default=None, help="working directory to find git root from")
    parser.add_argument("--config-dir", default=None, help="config directory containing lanes.json and routing.json")
    parser.add_argument("--meters", default=None, help="path to usage document JSON file")
    parser.add_argument("--harnesses", default=None, help="comma-separated list of present harnesses")
    parser.add_argument("--json", action="store_true", help="output as JSON")

    args = parser.parse_args(argv)
    tiers_mode = args.target == "tiers"

    if not tiers_mode and args.target not in CLASSES:
        sys.stderr.write(f"rank: unknown class '{args.target}'; must be one of {', '.join(CLASSES)}\n")
        sys.exit(2)
    if tiers_mode and args.tier is not None:
        parser.error("--tier is only valid with a Class")

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
        meters_doc = load_cached_usage() if tiers_mode else run_usage()

    if args.harnesses is not None:
        present = set(h.strip() for h in args.harnesses.split(",") if h.strip())
    else:
        present = {h for h in HARNESSES if shutil.which(h)}

    if tiers_mode:
        previews = tier_leaders(cat, meters_doc, present)
        routing = cat["routing"]
        margin = routing["margin"]
        gate = routing["gate"]

        if args.json:
            out = {
                "margin": margin,
                "gate": gate,
                "tiers": previews,
            }
            sys.stdout.write(json.dumps(out, indent=2) + "\n")
            sys.exit(0)

        gate_pct = f"{int(round(gate * 100))}%"
        for preview in previews:
            leader = preview["leader"] or "none"
            print(
                f"# Tier {preview['tier']} preview; not a Class Pick  "
                f"leader={leader}  margin={margin}  gate={gate_pct}"
            )
            for line in format_rows(preview["rows"]):
                print(line)
        sys.exit(0)

    try:
        rows = rank(args.target, cat, meters_doc, present, tier=args.tier)
    except ValueError as e:
        sys.stderr.write(f"rank: {e}\n")
        sys.exit(2)
    has_pick = bool(rows and rows[0]["pick"])

    routing = cat["routing"]
    cls_config = routing.get("classes", {}).get(args.target, {})
    floor = args.tier if args.tier is not None else cls_config.get("floor")
    ceiling = cls_config.get("ceiling")
    margin = routing["margin"]
    gate = routing["gate"]

    if args.json:
        out = {
            "class": args.target,
            "floor": floor,
            "ceiling": ceiling,
            "margin": margin,
            "gate": gate,
            "pick": rows[0]["lane"] if has_pick else None,
            "rows": rows,
        }
        sys.stdout.write(json.dumps(out, indent=2) + "\n")
        sys.exit(0 if has_pick else 1)

    if not has_pick:
        print(f"STOP: no lane eligible for {args.target}")
        for line in format_rows(rows):
            print(line)
        sys.exit(1)

    project_file = cat.get("files", {}).get("project")
    override_str = project_file if project_file else "none"
    gate_pct = f"{int(round(gate * 100))}%"
    print(f"# {args.target}  floor={floor} ceiling={ceiling}  margin={margin}  gate={gate_pct}  (routing: global; project override: {override_str})")
    for line in format_rows(rows):
        print(line)
    sys.exit(0)


if __name__ == "__main__":
    main()
