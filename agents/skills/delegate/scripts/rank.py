#!/usr/bin/env python3
"""
rank.py — rank the lanes that may do one class of work, best first.

    python3 rank.py <class> [author-family] [--json]

    <class>          one of the classes in ../lanes.json (lead, design, review,
                     hard-impl, impl, verify, scout, mechanical, browser, council),
                     or a workflow stage name that the "stages" map understands
                     (finder, refute, sweep, ...).
    [author-family]  for the review class: the family that wrote the code
                     (anthropic | openai | google | xai). Lanes of that family
                     are removed, so the reviewer is never the author's family.
    --json           machine-readable output instead of the table.

HOW THE RANK WORKS (the whole algorithm, in order)
  1. Take the lanes the class lists in lanes.json, in pin order. Pin order is
     the human's preference when quota is not a concern.
  2. If DELEGATE_BALANCE is not 1: print them in pin order and stop. Done.
  3. Otherwise read the live meters from usage.py (cached, zero model tokens).
     Each meter carries r = min(5h, weekly) remaining (the gate) and
     pace = weekly remaining / fraction of the weekly cycle still to run.
     pace 1.0 = spending evenly; above 1 = ahead (quota will expire unspent);
     below 1 = behind (over-spent). The 5h window is a rate cap, not a budget:
     what is lost at a reset is the unspent WEEKLY allotment, so pace is the
     thing to balance. score = pace, or r when the weekly meter is unknown.
  4. Drop lanes whose meter says "unavailable" (r below the gate in lanes.json).
  5. Sort the rest by score, highest first: the lane furthest ahead of its
     spending pace wins. One exception: two lanes that are both ABOVE the
     rebalance line (r) and within tie_band of each other on score keep pin
     order (quality preference wins a near-tie). Lower burn (list-price cost)
     breaks any remaining tie.
  6. A lane with an unknown meter is listed after every known one.
  7. A tier-1 class with no available lane prints STOP and the earliest reset,
     and exits 1. Never degrade tier-1 work.

WHAT THIS MEANS IN PRACTICE
  Worker classes (impl, verify, scout, mechanical) pin the external lanes first
  and the internal Claude lanes last or not at all. So an external lane wins
  whenever one is available; Claude only wins a worker class when every
  external lane is out. That is the load-balancing: it happens on every call,
  not only when Claude is low.

EXIT CODES: 0 ranked list · 1 STOP (no tier-1 lane) · 2 bad input.
Costs no model tokens. Reads: ../lanes.json, usage.py cache.
"""
import json
import os
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
LANES_FILE = os.path.join(HERE, "..", "lanes.json")
USAGE_SCRIPT = os.path.join(HERE, "usage.py")


def burn(lane):
    """List-price cost per million tokens, weighted for input-heavy agentic work."""
    return round(0.75 * lane["input"] + 0.25 * lane["output"], 2)


def load_registry():
    with open(LANES_FILE) as f:
        return json.load(f)


def load_meters():
    """Return {meter-name: lane-record} from usage.py, or {} if the probe fails."""
    try:
        raw = subprocess.run([sys.executable, USAGE_SCRIPT], capture_output=True, text=True, timeout=90).stdout
        doc = json.loads(raw)
        return {m["lane"]: m for m in doc["lanes"]}, doc
    except Exception:
        return {}, {}


def resolve_class(registry, name):
    """A class name, or a workflow stage name mapped through the stages table."""
    if name in registry["classes"]:
        return registry["classes"][name]
    for pattern, class_name in registry["stages"].items():
        if name in pattern.split("|"):
            return registry["classes"][class_name]
    return None


def build_rows(registry, cls, meters, author_family, balanced):
    """One row per eligible lane, still in pin order."""
    lanes_by_name = {lane["lane"]: lane for lane in registry["lanes"]}
    rows = []
    for pin_index, lane_name in enumerate(cls["pins"]):
        lane = lanes_by_name[lane_name]
        if author_family and lane["family"] == author_family:
            continue  # reviewer family must differ from author family
        meter = meters.get(lane["meter"], {})
        rows.append({
            "lane": lane_name,
            "tier": lane["tier"],
            "pin": pin_index,
            "r": meter.get("r"),
            "pace": meter.get("pace"),
            "score": meter.get("score", meter.get("r")),
            "status": meter.get("status", "unknown" if balanced else "pinned"),
            "burn": burn(lane),
            "courier": lane["courier"],
            "model": lane.get("model") or lane.get("role"),
            "reset": meter.get("reset_binding"),
        })
    return rows


def order_rows(rows, registry):
    """Steps 4-6 of the algorithm."""
    known_ok = [row for row in rows if row["status"] == "ok" and row["score"] is not None]
    unknown = [row for row in rows if row["score"] is None]
    unavailable = [row for row in rows if row["score"] is not None and row["status"] != "ok"]
    leader = max((row["score"] for row in known_ok), default=None)

    def sort_key(row):
        near_leader = (
            leader is not None
            and (leader - row["score"]) <= registry["tie_band"]
            and (row["r"] or 0) >= registry["rebalance"]
        )
        # Near the leader and healthy: sort as if tied with the leader, then by pin.
        # Otherwise: strictly by score (pace, or r when the weekly meter is unknown).
        effective = leader if near_leader else row["score"]
        return (-effective, row["pin"] if near_leader else 0, row["burn"])

    return sorted(known_ok, key=sort_key) + unknown + unavailable


def print_table(class_name, cls, rows, balanced, usage_doc):
    if usage_doc:
        age_min = int((datetime.now().timestamp() - usage_doc.get("probed_at", 0)) / 60)
        mode = f"balanced; usage age {age_min} min"
    else:
        mode = "optimal: pin order"
    print(f"# {class_name} (tier {cls['tier']}; {mode})")
    for n, row in enumerate(rows, 1):
        r_text = "  ?" if row["r"] is None else f"{int(round(row['r'] * 100)):3d}%"
        pace_text = "   ?" if row.get("pace") is None else f"{row['pace']:4.2f}"
        via = row["courier"] or f"Agent model:{row['model']}"
        print(f"{n}. {row['lane']:<18} pace={pace_text}  r={r_text}  burn=${row['burn']:<5} {row['status']:<11} via {via}")


def main():
    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not positional:
        print(__doc__)
        sys.exit(2)
    class_name = positional[0]
    author_family = positional[1] if len(positional) > 1 else None
    as_json = "--json" in sys.argv

    registry = load_registry()
    cls = resolve_class(registry, class_name)
    if cls is None:
        print(f"unknown class {class_name!r}; classes: {', '.join(registry['classes'])}", file=sys.stderr)
        sys.exit(2)
    if not cls["pins"]:
        print(cls["shape"])  # browser and council route elsewhere
        sys.exit(0)

    balanced = (os.environ.get("DELEGATE_BALANCE") or os.environ.get("CONSULT_BALANCE")) == "1"  # CONSULT_* is a deprecated alias
    meters, usage_doc = load_meters() if balanced else ({}, {})
    rows = build_rows(registry, cls, meters, author_family, balanced)
    ranked = order_rows(rows, registry) if balanced else rows

    if balanced and cls["tier"] == 1 and not any(row["status"] == "ok" for row in ranked):
        resets = [row["reset"] for row in rows if row.get("reset")]
        soonest = datetime.fromtimestamp(min(resets)).strftime("%b %d %H:%M") if resets else "unknown"
        print(f"STOP: no tier-1 lane available for {class_name}; earliest reset {soonest}")
        sys.exit(1)

    if as_json:
        print(json.dumps({"class": class_name, "tier": cls["tier"], "balanced": balanced, "ranked": ranked}, indent=1))
    else:
        print_table(class_name, cls, ranked, balanced, usage_doc)


if __name__ == "__main__":
    main()
