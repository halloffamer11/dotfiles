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
  5. Overflow (ticket 29, Class ranking only). If nothing is eligible and only
     subscription usage stands in the way — at least one carried lane in the
     Range is under the gate, and every veto there is gate or cli — admit the
     tier above the ceiling and rank it by the same rule. A cli-absent lane
     counts like a lane switched off: the catalog is shared across machines and
     this one cannot run that lane. Step one tier at a time while the admitted
     tier is also stopped that way; never past tier 3, which keeps tier 4
     named-only; never below the floor. The pick then carries
     `overflow: {from, to, why}` and the header says so. Any other veto in the
     Range, a Range with no carried lane, a Range whose carried lanes are all
     cli-absent with no gate veto among them, `routing.meters` off (no gate
     vetoes exist) or `routing.overflow` false all keep the stop.

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
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import catalog
from catalog import CatalogError, CLASSES, HARNESSES, load_catalog
import usage


# Compatibility export for dashboard callers. Validity lives in usage.
meter_observations = usage.observations


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
    metering = catalog.meters_enabled(routing)
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
            if r is None:
                meter_status = "unknown"
            elif metering and not usage.eligible(rec, gate):
                meter_status = "unavailable"
            else:
                meter_status = "ok"
        else:
            r = None
            pace = None
            remaining_weekly = None
            meter_status = "unknown"
            rec = None

        lane_tier = lane_def.get("tier")
        harness = lane_def.get("harness")
        model = lane_def.get("model")
        lane_effort = lane_def.get("effort")

        # One veto per lane, in this precedence: disabled, floor, ceiling,
        # gate, cli. The order is load-bearing for overflow: a lane failing
        # both the Gate and the CLI check is recorded `gate`, and
        # `gate_only_stop` accepts either kind, so neither reading changes
        # what it decides (ticket 29).
        veto_kind = None
        veto_reason = None
        if not lane_def.get("enabled", True):
            veto_kind = "disabled"
            veto_reason = f"vetoed:disabled, {lane_name}"
        elif lane_tier is not None and floor is not None and lane_tier < floor:
            veto_kind = "floor"
            veto_reason = f"vetoed:floor, {lane_name} (tier {lane_tier}) < {reason_label} floor (tier {floor})"
        elif lane_tier is not None and ceiling is not None and lane_tier > ceiling:
            veto_kind = "ceiling"
            veto_reason = f"vetoed:ceiling, {lane_name} (tier {lane_tier}) > {reason_label} ceiling (tier {ceiling})"
        elif metering and not usage.eligible(rec, gate):
            veto_kind = "gate"
            r_pct = f"{int(round(r * 100)):d}%"
            gate_pct = f"{int(round(gate * 100)):d}%"
            veto_reason = f"vetoed:gate, {lane_name}: {meter_name} meter {r_pct} left < gate {gate_pct}"
        elif harness not in present_set:
            veto_kind = "cli"
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
            # the machine-readable half of `reason`: None, or one of
            # disabled, floor, ceiling, gate, cli
            "veto": veto_kind,
            "pick": False,
            # only a Pick admitted past its Ceiling carries a record here
            "overflow": None,
            "reason": veto_reason or "",
        }

        if veto_reason is None:
            eligible_rows.append(row)
        else:
            vetoed_rows.append(row)

    def sort_key(item):
        t = item["tier"] if item["tier"] is not None else 99
        unordered = 1 if item["order"] is None else 0
        o = item["order"] if item["order"] is not None else 0
        if not metering:
            return (t, unordered, o, item["lane"])
        unknown = 1 if item["pace"] is None else 0
        p = item["pace"] if item["pace"] is not None else 0.0
        return (unknown, t, unordered, o, -p, item["lane"])

    eligible_rows.sort(key=sort_key)

    if eligible_rows:
        pick_row = eligible_rows[0]
        beaten_pace = None
        if metering:
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
                if metering and r["pace"] is None:
                    r["reason"] = "unknown meter, sorted last"
                else:
                    r["reason"] = "eligible"

        ordered_eligible = [pick_row] + [r for r in eligible_rows if r is not pick_row]
    else:
        ordered_eligible = []

    return ordered_eligible + vetoed_rows


# Overflow never admits Tier 4: the frontier Tier is reached by naming a Lane,
# never by an automatic rule (ticket 29).
OVERFLOW_TOP_TIER = 3
OVERFLOW_WHY = "all in-Range Lanes under Gate"


def gate_only_stop(rows, floor, ceiling):
    """True when subscription usage is the only thing stopping [floor, ceiling].

    Among the carried Lanes in the Range, at least one has to be under the Gate
    and every veto has to be `gate` or `cli`. A Lane whose Harness CLI is absent
    counts like a Lane switched off: the catalog is shared across machines, and
    a Lane this machine cannot run is not a Lane the Range still has. So it
    neither creates the outage nor blocks the answer to one.

    Everything else stops as it did before ticket 29: a Range with no carried
    Lane, a Range whose carried Lanes are every one of them cli-absent with no
    Gate veto among them, and any other veto kind. With ``routing.meters`` off
    no row can carry a Gate veto, so this is never true.
    """
    in_range = [
        row for row in rows
        if row.get("veto") != "disabled"
        and row["tier"] is not None
        and (floor is None or row["tier"] >= floor)
        and (ceiling is None or row["tier"] <= ceiling)
    ]
    if not any(row.get("veto") == "gate" for row in in_range):
        return False
    return all(row.get("veto") in ("gate", "cli") for row in in_range)


def rank(cls, cat, meters, present, tier=None):
    """Rank catalog lanes for a given class.

    cat: dict from catalog.load_catalog
    meters: usage document dict (or {})
    present: set of harness names
    tier: optional floor override (must be between class floor and ceiling)

    When the Range stops and every carried Lane in it is under the Gate, the
    next Tier above the Ceiling is admitted and ranked by the normal rule, one
    Tier at a time and never Tier 4 (ticket 29). The Pick then carries an
    ``overflow`` record saying which Ceiling was raised, to which Tier and why;
    no other row carries one. ``routing.overflow`` false keeps the stop.
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

    rows = rank_range(
        cat,
        meters,
        present,
        floor=floor,
        ceiling=ceiling,
        reason_label=cls,
    )
    if rows and rows[0]["pick"]:
        return rows
    if ceiling is None or not catalog.overflow_enabled(routing):
        return rows

    # The Range's own rows are what a stop reports, so keep them: a widened
    # range that also fails would otherwise explain the stop against a Ceiling
    # the Class does not have.
    stopped = rows
    admitted = ceiling
    while admitted < OVERFLOW_TOP_TIER and gate_only_stop(rows, floor, admitted):
        admitted += 1
        rows = rank_range(
            cat,
            meters,
            present,
            floor=floor,
            ceiling=admitted,
            reason_label=cls,
        )
        if rows and rows[0]["pick"]:
            rows[0]["overflow"] = {
                "from": ceiling,
                "to": admitted,
                "why": OVERFLOW_WHY,
            }
            return rows
    return stopped


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


def print_rank_output(cls, cat, rows, tier=None):
    """Print the Class header (or STOP) and ranked rows. Returns whether a Pick exists."""
    has_pick = bool(rows and rows[0].get("pick"))
    if not has_pick:
        print(f"STOP: no lane eligible for {cls}")
        for line in format_rows(rows):
            print(line)
        return False
    routing = cat["routing"]
    cls_config = routing.get("classes", {}).get(cls, {})
    floor = tier if tier is not None else cls_config.get("floor")
    ceiling = cls_config.get("ceiling")
    margin = routing["margin"]
    gate = routing["gate"]
    project_file = cat.get("files", {}).get("project")
    override_str = project_file if project_file else "none"
    gate_pct = f"{int(round(gate * 100))}%"
    meters_bit = "" if catalog.meters_enabled(routing) else "  meters=off"
    print(f"# {cls}  floor={floor} ceiling={ceiling}{meters_bit}  margin={margin}  gate={gate_pct}  (routing: global; project override: {override_str})")
    # A project may set a Lane's Tier (ticket 32). The rows carry only the
    # effective Tier, so the header says which Lanes run on a project one.
    project_tiers = cat.get("project_tiers") or {}
    if project_tiers:
        moved = ", ".join(
            f"{name} {change['from']} -> {change['to']}"
            for name, change in sorted(project_tiers.items())
        )
        print(f"# project tier: {moved}  ({cat.get('files', {}).get('project_lanes')})")
    # The Ceiling above stays the Class's own, which is the value `--tier` is
    # bounded by; this second header line says the job went past it and why.
    overflow = rows[0].get("overflow")
    if overflow:
        print(f"# overflow: ceiling {overflow['from']} -> {overflow['to']}, {overflow['why']}")
    for line in format_rows(rows):
        print(line)
    return True


def run_usage():
    """Refresh path: probe vendors when the cache is missing or stale."""
    try:
        return usage.acquire(timeout=90)
    except Exception:
        return {}


def load_cached_usage(cache_path=None):
    """Read the usage cache without invoking any vendor probe."""
    return usage.load_cached(cache_path=cache_path)


def load_usage(cat, meters_path=None, *, refresh=False):
    """Observations for ranking. routing.meters off never probes vendors.

    ``meters_path`` is an explicit document and is loaded even when metering
    is off. ``refresh=True`` is the class-rank path (acquire); False is cache.
    """
    if meters_path:
        try:
            with open(meters_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    if not catalog.meters_enabled(cat.get("routing", {})):
        return load_cached_usage()
    if refresh:
        return run_usage()
    return load_cached_usage()


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

    meters_doc = load_usage(cat, args.meters, refresh=not tiers_mode)

    if args.harnesses is not None:
        present = set(h.strip() for h in args.harnesses.split(",") if h.strip())
    else:
        present = {h for h in HARNESSES if shutil.which(h)}

    if tiers_mode:
        previews = tier_leaders(cat, meters_doc, present)
        routing = cat["routing"]
        margin = routing["margin"]
        gate = routing["gate"]
        metering = catalog.meters_enabled(routing)

        if args.json:
            out = {
                "margin": margin,
                "gate": gate,
                "meters": metering,
                "tiers": previews,
            }
            sys.stdout.write(json.dumps(out, indent=2) + "\n")
            sys.exit(0)

        gate_pct = f"{int(round(gate * 100))}%"
        meters_bit = "" if metering else "  meters=off"
        for preview in previews:
            leader = preview["leader"] or "none"
            print(
                f"# Tier {preview['tier']} preview; not a Class Pick  "
                f"leader={leader}{meters_bit}  margin={margin}  gate={gate_pct}"
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
    metering = catalog.meters_enabled(routing)

    if args.json:
        out = {
            "class": args.target,
            "floor": floor,
            "ceiling": ceiling,
            "margin": margin,
            "gate": gate,
            "meters": metering,
            "overflow": rows[0].get("overflow") if has_pick else None,
            "pick": rows[0]["lane"] if has_pick else None,
            "rows": rows,
        }
        sys.stdout.write(json.dumps(out, indent=2) + "\n")
        sys.exit(0 if has_pick else 1)

    print_rank_output(args.target, cat, rows, tier=args.tier)
    sys.exit(0 if has_pick else 1)


if __name__ == "__main__":
    main()
