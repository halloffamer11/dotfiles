#!/usr/bin/env python3
"""rank.py <class>  — lanes eligible for a class, best first. Deterministic:
   1. rows of lanes.tsv whose classes include <class>, in table order
   2. drop a lane whose meter is unavailable (r below GATE) or whose CLI is absent
   3. sort by pace, highest first; table order breaks ties. pace = weekly remaining
      / fraction of the weekly cycle still to run (usage.py). 1.0 = spending evenly,
      above 1 = ahead (quota will expire unspent, use it), below 1 = behind. A meter
      with no reset time falls back to its weekly remaining fraction.
Meters come from usage.py (cached; zero model tokens). Unknown meter sorts last."""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); GATE = 0.10
METER = {"agy": {"gemini": "agy-gemini", "claude": "agy-claude-gpt"}, "codex": "codex", "grok": "grok"}

def meter_for(harness, slug):
    m = METER[harness]
    return m if isinstance(m, str) else m["gemini" if slug.startswith("gemini") else "claude"]

def lanes():
    for line in open(os.path.join(HERE, "lanes.tsv")):
        if line.startswith("#") or not line.strip(): continue
        lane, harness, slug, classes, *note = line.rstrip("\n").split("\t")
        yield lane, harness, slug, classes.split(","), (note or [""])[0]

def meters():
    try:
        doc = json.loads(subprocess.run([sys.executable, os.path.join(HERE, "usage.py")], capture_output=True, text=True, timeout=90).stdout)
        return {m["lane"]: m for m in doc["lanes"]}
    except Exception:
        return {}

def main():
    if len(sys.argv) < 2: print(__doc__); sys.exit(2)
    cls = sys.argv[1]; ms = meters(); rows = []
    for i, (lane, harness, slug, classes, note) in enumerate(lanes()):
        if cls not in classes: continue
        m = ms.get(meter_for(harness, slug), {})
        wk, r, status = m.get("remaining_weekly"), m.get("r"), m.get("status", "unknown")
        pace = m.get("pace") if m.get("pace") is not None else wk
        if status == "unavailable": continue
        rows.append((-(pace if pace is not None else -1), i, lane, harness, slug, pace, wk, r, status, note))
    if not rows: print(f"STOP: no lane available for {cls}"); sys.exit(1)
    print(f"# {cls}")
    for n, (_, _, lane, harness, slug, pace, wk, r, status, note) in enumerate(sorted(rows), 1):
        f = lambda x: "  ?" if x is None else f"{int(round(x*100)):3d}%"
        p = "   ?" if pace is None else f"{pace:4.2f}"
        print(f"{n}. {lane:<18} pace={p} weekly={f(wk)} r={f(r)} {status:<8} {slug:<26} {note}")

if __name__ == "__main__": main()
