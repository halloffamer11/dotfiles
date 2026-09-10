#!/usr/bin/env python3
"""State-machine and pty smoke tests for setup_tui.py."""
import copy
import fcntl
import json
import os
import pty
import struct
import subprocess
import sys
import tempfile
import termios
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DELEGATE_DIR = os.path.abspath(os.path.join(HERE, "..", "scripts"))
FIXTURE = os.path.join(HERE, "fixture", "bench-epoch.csv")
FIXTURES = os.path.join(HERE, "fixtures")
FIXTURES_DISCOVER = os.path.join(FIXTURES, "discover")
sys.path.insert(0, DELEGATE_DIR)

import bench
import catalog
import discover
from setup_tui import Wizard

LANES = catalog.load_json(os.path.abspath(os.path.join(HERE, "..", "assets", "samples", "lanes.json")))
ROUTING = catalog.load_json(os.path.abspath(os.path.join(HERE, "..", "assets", "samples", "routing.json")))
DISCOVERED = set(catalog.HARNESSES)
fails = 0


def record(name, ok, detail=""):
    global fails
    if ok:
        print(f"PASS {name}")
    else:
        fails += 1
        print(f"FAIL {name}: {detail}")


def data():
    return bench.collect(copy.deepcopy(LANES), epoch_csv=FIXTURE, key_file=None)


def wizard(bench_data=True, message="", effort_rows=None, lanes=None, discovery=None):
    return Wizard(copy.deepcopy(lanes if lanes is not None else LANES),
                  copy.deepcopy(ROUTING),
                  data() if bench_data else None, DISCOVERED,
                  "/tmp/lanes.json", "/tmp/routing.json", message,
                  effort_rows=effort_rows, discovery=discovery)


def start(w):
    w.handle("enter")
    w.handle("enter")
    w.handle("enter")


def move_to(w, lane):
    for _ in range(len(w.view()["rows"]) + 1):
        row = next((r for r in w.view()["rows"] if r["cursor"]), None)
        if row and row["cells"][1] == lane:
            return
        w.handle("down")
    raise AssertionError(f"could not move to {lane}")


def finish(w):
    while w.screen == "tier":
        w.handle("enter")
    if w.screen == "routing":
        w.handle("enter")
    if w.screen == "confirm":
        w.handle("y")


try:
    collected = data()
    record("collect returns documented keys",
           set(collected) == {"models", "epoch_benchmarks", "aa_columns", "aa_skipped", "notes"})
except Exception as e:
    record("collect returns documented keys", False, repr(e))

try:
    w = wizard()
    start(w)
    v = w.view()
    active = [r for r in v["rows"] if not r["dimmed"]]
    models = [r["cells"][2] for r in active]
    fable = next(r for r in active if r["cells"][1] == "fable-xhigh@claude")
    sol = next(r for r in active if r["cells"][1] == "sol-high@codex")
    flash = next(r for r in active if r["cells"][1] == "flash-high@agy")
    record("1 tier 4 selection and benchmark order",
           v["tier"] == 4 and fable["marked"]
           and models[:2] == ["claude-fable-5-1", "gpt-5.6-sol"]
           and models[-1] == "gemini-3.8-flash-high"
           and "98.0" in fable["cells"] and "90.0" in sol["cells"]
           and all(x == "—" for x in flash["cells"][4:9])
           and flash["cells"][9].startswith("—"), str(v))
except Exception as e:
    record("1 tier 4 selection and benchmark order", False, repr(e))

try:
    w = wizard()
    start(w)
    finish(w)
    record("2 unchanged round trip", w.result() == (LANES, ROUTING), repr(w.result()))
except Exception as e:
    record("2 unchanged round trip", False, repr(e))

try:
    w = wizard()
    start(w)
    move_to(w, "sol-high@codex")
    w.handle("space")
    w.handle("enter")
    sol = next(r for r in w.view()["rows"] if r["cells"][1] == "sol-high@codex")
    # the tier a lane already went to is in the box, where it cannot be clipped
    dimmed = sol["dimmed"] and sol["cells"][0] == "[4]" and sol["tag"] == ""
    finish(w)
    lanes, _ = w.result()
    record("3 higher-tier lanes dim and persist",
           dimmed and lanes["lanes"]["sol-high@codex"]["tier"] == 4
           and lanes["lanes"]["terra-high@codex"]["tier"] == 2)
except Exception as e:
    record("3 higher-tier lanes dim and persist", False, repr(e))

try:
    w = wizard()
    start(w)
    w.handle("enter")
    w.handle("enter")
    move_to(w, "grok46-high@grok")
    w.handle("4")
    finish(w)
    lanes, routing = w.result()
    record("4 digit keys are inert on the tier screen",
           lanes == LANES and routing == ROUTING)
except Exception as e:
    record("4 digit keys are inert on the tier screen", False, repr(e))

try:
    w = wizard()
    start(w)
    w.handle("enter")
    w.handle("enter")
    w.handle("enter")
    move_to(w, "luna-low@codex")
    w.handle("space")
    w.handle("enter")
    blocked = w.screen == "tier" and w.tier == 1 and w.view()["message"] == "every lane needs a tier"
    w.handle("space")
    w.handle("enter")
    record("5 tier 1 requires every lane", blocked and w.screen == "routing")
except Exception as e:
    record("5 tier 1 requires every lane", False, repr(e))

try:
    w = wizard()
    start(w)
    for _ in range(4):
        w.handle("enter")
    for _ in range(3):
        w.handle("down")
    w.handle("plus")
    for _ in range(2):
        w.handle("down")
    w.handle("plus")
    w.handle("enter")
    w.handle("y")
    lanes, routing = w.result()
    expected = copy.deepcopy(ROUTING)
    expected["classTier"]["review"] = 3
    expected["margin"] = 0.25
    record("6 routing edits are isolated", lanes == LANES and routing == expected, repr(routing))
except Exception as e:
    record("6 routing edits are isolated", False, repr(e))

try:
    w1 = wizard(); start(w1); finish(w1)
    # finish accepts, so use a fresh wizard stopped at confirm for decline.
    w1 = wizard(); start(w1)
    for _ in range(4): w1.handle("enter")
    w1.handle("enter"); w1.handle("n")
    w2 = wizard(); start(w2); w2.handle("q")
    record("7 decline and early quit return no result",
           w1.screen == "quit" and w1.result() is None
           and w2.screen == "quit" and w2.result() is None)
except Exception as e:
    record("7 decline and early quit return no result", False, repr(e))

try:
    w = wizard(); start(w); move_to(w, "sol-high@codex"); w.handle("space")
    w.handle("enter"); w.handle("b")
    sol = next(r for r in w.view()["rows"] if r["cells"][1] == "sol-high@codex")
    record("8 back restores prior tier marks",
           w.tier == 4 and sol["marked"] and not sol["dimmed"])
except Exception as e:
    record("8 back restores prior tier marks", False, repr(e))

try:
    w = wizard(False, "fixture unavailable")
    initial = w.view()["message"] == "fixture unavailable"
    start(w)
    row = w.view()["rows"][0]
    record("9 absent benchmarks render em dashes",
           initial and all(value == "—" for value in row["cells"][5:11]))
except Exception as e:
    record("9 absent benchmarks render em dashes", False, repr(e))

try:
    w = wizard()
    v = w.view()
    body = "\n".join(v.get("body") or [])
    record("11 start screen names both files",
           v["screen"] == "start" and v["columns"] == [] and v["rows"] == []
           and w.lanes_path in body and w.routing_path in body
           and "Nothing is written until the confirm screen" in body
           and "q leaves without writing" in body)
    w.handle("q")
    record("11b q on start quits without writing",
           w.screen == "quit" and w.result() is None)
except Exception as e:
    record("11 start screen names both files", False, repr(e))

try:
    w = wizard()
    w.handle("other")
    record("11c any unmapped key leaves start", w.screen == "discovery")
    w2 = wizard()
    w2.handle("o")
    record("11d o on start does not advance", w2.screen == "start")
except Exception as e:
    record("11c any unmapped key leaves start", False, repr(e))

disc_unmapped = {
    "harnesses": {"agy": {"status": "ok"}},
    "models": [],
    "unmapped": [{"harness": "agy", "slug": "gemini-3.8-flash-low", "display_name": "Gemini 3.8 Flash (Low)"}],
    "retired": [],
}
try:
    w = wizard(discovery=disc_unmapped)
    v = w.view()
    body = "\n".join(v.get("body") or [])
    record("11e start screen names a model with no lane",
           v["screen"] == "start"
           and "agy gemini-3.8-flash-low" in body
           and "Models with no lane" in body)
except Exception as e:
    record("11e start screen names a model with no lane", False, repr(e))

disc_retired = {
    "harnesses": {"codex": {"status": "ok"}},
    "models": [],
    "unmapped": [],
    "retired": [{"lane": "sol-high@codex", "harness": "codex", "model": "gpt-5.6-sol"}],
}
try:
    w = wizard(discovery=disc_retired)
    v = w.view()
    body = "\n".join(v.get("body") or [])
    record("11f start screen names a lane whose model is retired",
           v["screen"] == "start"
           and "sol-high@codex" in body
           and "Lanes with retired models" in body)
except Exception as e:
    record("11f start screen names a lane whose model is retired", False, repr(e))

disc_nodrift = {
    "harnesses": {"codex": {"status": "ok"}},
    "models": [],
    "unmapped": [],
    "retired": [],
}
try:
    w = wizard(discovery=disc_nodrift)
    v = w.view()
    body = "\n".join(v.get("body") or [])
    record("11g start screen shows no-drift line when there is neither",
           v["screen"] == "start"
           and "Model discovery: no drift" in body)
except Exception as e:
    record("11g start screen shows no-drift line when there is neither", False, repr(e))

try:
    # one shape: the discover() dict, or a string saying why it did not run
    w1 = wizard(discovery="subprocess timed out")
    body1 = "\n".join(w1.view().get("body") or [])
    w2 = wizard(discovery=None)
    body2 = "\n".join(w2.view().get("body") or [])
    record("11h start screen shows discovery-failed line when argument says so",
           "Model discovery: did not run: subprocess timed out" in body1
           and "Model discovery: did not run" in body2)
except Exception as e:
    record("11h start screen shows discovery-failed line when argument says so", False, repr(e))

try:
    w = wizard()
    start(w)
    # the tier definition renders as the last legend line, directly above the
    # key hints, so the two together are the footer block the human reads
    footer = w.view()["footer"] + "  " + "  ".join(w.view().get("legend") or [])
    record("12 tier footer carries the tier one-liner",
           w.screen == "tier"
           and "ceiling" in footer
           and "x: on/off" in footer
           and "o: bench" in footer)
    before_cursor = w.cursor
    w.handle("d")
    record("12b d is unbound on tier",
           w.screen == "tier" and w.cursor == before_cursor and w.tier == 4)
except Exception as e:
    record("12 tier footer carries the tier one-liner", False, repr(e))

try:
    w = wizard()
    start(w)
    incoming_sol = LANES["lanes"]["sol-high@codex"]["tier"]
    move_to(w, "sol-high@codex")
    w.handle("space")
    w.handle("enter")
    while w.screen == "tier":
        w.handle("enter")
    legend = w.view().get("legend") or []
    t4 = next(line for line in legend if line.startswith("tier 4 "))
    t_incoming = next(line for line in legend if line.startswith(f"tier {incoming_sol} "))
    prefixes = [line.split(" (", 1)[0] for line in legend if line.startswith("tier ")]
    record("13 routing legend maps this session's assignments",
           w.screen == "routing"
           and incoming_sol != 4
           and "sol-high@codex" in t4
           and "sol-high@codex" not in t_incoming
           and prefixes[:4] == ["tier 1", "tier 2", "tier 3", "tier 4"]
           # margin and gate lead, so a short window keeps them
           and legend[0].startswith("margin ")
           and any(line.startswith("margin 0.2 ") for line in legend)
           and any(line.startswith("gate 0.1 ") for line in legend)
           and any("pace" in line for line in legend)
           and any("10% remaining" in line for line in legend))
    w.handle("enter")
    confirm_legend = w.view().get("legend") or []
    record("14 confirm legend explains classTier, margin and gate",
           w.screen == "confirm"
           and any("classTier:" in line for line in confirm_legend)
           and any(line.startswith("margin 0.2 ") for line in confirm_legend)
           and any(line.startswith("gate 0.1 ") for line in confirm_legend)
           and any("10% remaining" in line for line in confirm_legend)
           and all(len(line) <= 79 for line in confirm_legend))
    w.handle("y")
    lanes, routing = w.result()
    record("15 key sequence write path is unchanged",
           lanes["lanes"]["sol-high@codex"]["tier"] == 4
           and routing == ROUTING)
except Exception as e:
    record("13 routing legend maps this session's assignments", False, repr(e))


VIEW_KEYS = {"screen", "title", "tier", "columns", "rows", "footer", "message", "body",
              "legend", "steps", "elastic"}


def row_for(view, lane):
    return next(r for r in view["rows"] if r["cells"][1] == lane)


def carry_of(row):
    """What the pre-screen box says: the box is the only carry signal now."""
    return {"[x]": "on", "[ ]": "off"}.get(row["cells"][0], row["cells"][0])


def why_of(row):
    """The pre-screen reason, which has to be whole inside its column."""
    return row["cells"][4]


def to_confirm(w):
    while w.screen == "tier":
        w.handle("enter")
    if w.screen == "routing":
        w.handle("enter")


try:
    w = wizard()
    start(w)
    cursor_name = next(r["cells"][1] for r in w.view()["rows"] if r["cursor"])
    enabled_before = dict(w._enabled)
    marks_before = {tier: set(names) for tier, names in w._marks.items()}
    assigned_before = dict(w._assigned)
    others = {r["cells"][1]: (r["marked"], r["cells"][0], r["tag"])
              for r in w.view()["rows"] if r["cells"][1] != cursor_name}
    w.handle("x")
    v = w.view()
    flipped = row_for(v, cursor_name)
    others_after = {r["cells"][1]: (r["marked"], r["cells"][0], r["tag"])
                    for r in v["rows"] if r["cells"][1] != cursor_name}
    record("16 x flips only the cursor row",
           w.screen == "tier" and w.tier == 4
           and w._assigned == assigned_before and w._marks == marks_before
           and w._enabled[cursor_name] is not enabled_before[cursor_name]
           and all(w._enabled[name] is enabled_before[name]
                   for name in enabled_before if name != cursor_name)
           and others_after == others
           and flipped["dimmed"] and flipped["tag"] == "off")
except Exception as e:
    record("16 x flips only the cursor row", False, repr(e))


try:
    w = wizard()
    start(w)
    move_to(w, "sol-high@codex")
    w.handle("space")
    w.handle("enter")
    move_to(w, "flash-high@agy")
    w.handle("x")
    v = w.view()
    names = [r["cells"][1] for r in v["rows"]]
    flash = row_for(v, "flash-high@agy")
    sol = row_for(v, "sol-high@codex")
    record("17 disabled lane stays visible and is not assigned-dimmed",
           "flash-high@agy" in names
           and flash["dimmed"] and flash["tag"] == "off" and flash["cells"][0] == "[ ]"
           and sol["dimmed"] and sol["tag"] == "" and sol["cells"][0] == "[4]")
except Exception as e:
    record("17 disabled lane stays visible and is not assigned-dimmed", False, repr(e))


try:
    w = wizard()
    start(w)
    move_to(w, "flash-high@agy")
    w.handle("x")
    while w.tier != 1:
        w.handle("enter")
    move_to(w, "flash-high@agy")
    w.handle("space")
    w.handle("enter")
    blocked = w.screen == "tier" and w.tier == 1 and w.view()["message"] == "every lane needs a tier"
    w.handle("space")
    w.handle("enter")
    record("18 disabled lane still takes a tier; tier-1 rule applies",
           blocked and w.screen == "routing")
    to_confirm(w)
    w.handle("y")
    lanes, _ = w.result()
    record("18b disabled lane is written with a tier",
           lanes["lanes"]["flash-high@agy"]["tier"] in (1, 2, 3, 4)
           and lanes["lanes"]["flash-high@agy"]["enabled"] is False)
except Exception as e:
    record("18 disabled lane still takes a tier; tier-1 rule applies", False, repr(e))


try:
    w = wizard()
    start(w)
    move_to(w, "flash-high@agy")
    w.handle("x")
    to_confirm(w)
    confirm = w.view()
    off_rows = [r for r in confirm["rows"] if r["cells"][0] == "flash-high@agy"]
    paths = [r["cells"][2] for r in confirm["rows"] if r["cells"][0] == "file"]
    record("19 confirm lists lanes written off",
           confirm["screen"] == "confirm"
           and off_rows
           and off_rows[0]["cells"][1] == "off"
           and off_rows[0]["tag"] == ""
           # `value` is elastic so a path is not cut to 24 places
           and confirm["elastic"] == "value" and paths == ["/tmp/lanes.json", "/tmp/routing.json"]
           and any("enabled: false" in line for line in (confirm.get("legend") or [])))
    w.handle("y")
    lanes, _ = w.result()
    on_lanes = [name for name in LANES["lanes"] if name != "flash-high@agy"]
    record("20 enabled false only on lanes switched off",
           lanes["lanes"]["flash-high@agy"]["enabled"] is False
           and all("enabled" not in lanes["lanes"][name] for name in on_lanes))
except Exception as e:
    record("19 confirm lists lanes written off", False, repr(e))


try:
    incoming = copy.deepcopy(LANES)
    incoming["lanes"]["sol-high@codex"]["enabled"] = False
    w = wizard(lanes=incoming)
    w.handle("enter")
    w.handle("enter")
    start_from_prescreen = w.screen == "prescreen"
    # the recorded decision stands until the human flips it
    held = carry_of(row_for(w.view(), "sol-high@codex")) == "off"
    while w.view()["rows"][w.cursor]["cells"][1] != "sol-high@codex":
        w.handle("down")
    w.handle("x")
    flipped_on = carry_of(row_for(w.view(), "sol-high@codex")) == "on"
    w.handle("enter")
    finish(w)
    lanes, _ = w.result()
    record("21 incoming enabled false switched on drops the key",
           start_from_prescreen and held and flipped_on
           and "enabled" not in lanes["lanes"]["sol-high@codex"])
except Exception as e:
    record("21 incoming enabled false switched on drops the key", False, repr(e))


try:
    w = wizard()
    w.handle("enter")
    w.handle("enter")
    v = w.view()
    record("22 pre-screen is in the key sequence",
           w.screen == "prescreen" and set(v) == VIEW_KEYS
           and [r["cells"][1] for r in v["rows"]] == list(LANES["lanes"])
           and v["message"] == "No per-effort data was supplied, so nothing else could be judged.")
    w.handle("q")
    record("22b q on pre-screen quits without writing",
           w.screen == "quit" and w.result() is None)
except Exception as e:
    record("22 pre-screen is in the key sequence", False, repr(e))


try:
    with_ultra = copy.deepcopy(LANES)
    with_ultra["lanes"]["sol-ultra@codex"] = copy.deepcopy(LANES["lanes"]["sol-high@codex"])
    with_ultra["lanes"]["sol-ultra@codex"]["effort"] = "ultra"
    w = wizard(lanes=with_ultra)
    w.handle("enter")
    w.handle("enter")
    ultra = row_for(w.view(), "sol-ultra@codex")
    legend = w.view()["legend"]
    record("23 ultra is proposed off with both reasons",
           w.screen == "prescreen"
           and carry_of(ultra) == "off" and ultra["tag"] == ""
           and why_of(ultra) == "ultra, never carried"
           # the phrase fits the column; the sentence it stands for is the legend
           # line that only an ultra lane on screen earns
           and any("no source scores it" in line and "worker preamble" in line
                   for line in legend))
except Exception as e:
    record("23 ultra is proposed off with both reasons", False, repr(e))


try:
    # medium scores higher for less money, so low is genuinely dominated by an
    # effort a lane can actually be set to
    rows = [
        {"model": "gpt-5.6-luna", "effort": "low", "score": 4.0, "cost_usd": 1.7,
         "uncertain": False, "source": "t", "benchmark": "b"},
        {"model": "gpt-5.6-luna", "effort": "medium", "score": 6.0, "cost_usd": 1.5,
         "uncertain": False, "source": "t", "benchmark": "b"},
        {"model": "gpt-5.6-sol", "effort": "high", "score": 19.0, "cost_usd": 7.7,
         "uncertain": False, "source": "t", "benchmark": "b"},
    ]
    w = wizard(effort_rows=rows)
    w.handle("enter")
    w.handle("enter")
    v = w.view()
    luna = row_for(v, "luna-low@codex")
    sol = row_for(v, "sol-high@codex")
    flash = row_for(v, "flash-high@agy")
    record("24 dominated lane proposed off; unscored proposed on",
           carry_of(luna) == "off" and "dominated" in why_of(luna)
           and carry_of(sol) == "on" and why_of(sol) == "not dominated"
           and carry_of(flash) == "on" and why_of(flash) == "no rows for this lane"
           and any("Absence of data is not evidence against" in line
                   for line in v["legend"]))
except Exception as e:
    record("24 dominated lane proposed off; unscored proposed on", False, repr(e))


try:
    # Every published sweep carries a `none` row, and no lane can be set to
    # `none`. A row at an effort no lane can select must never switch a real lane
    # off: this is what proposed luna-low@codex off on its first run.
    rows = [
        {"model": "gpt-5.6-luna", "effort": "low", "score": 4.0, "cost_usd": 1.7,
         "uncertain": False, "source": "t", "benchmark": "b"},
        {"model": "gpt-5.6-luna", "effort": "none", "score": 4.0, "cost_usd": 1.6,
         "uncertain": False, "source": "t", "benchmark": "b"},
    ]
    w = wizard(effort_rows=rows)
    w.handle("enter")
    w.handle("enter")
    luna = row_for(w.view(), "luna-low@codex")
    record("24b an effort no lane can select never dominates",
           carry_of(luna) == "on" and "dominated by" not in why_of(luna))
except Exception as e:
    record("24b an effort no lane can select never dominates", False, repr(e))


try:
    # An explicit `enabled` in the catalog is a decision the human recorded. The
    # pre-screen must not quietly undo it and hand the lane back to the ranker.
    recorded = copy.deepcopy(LANES)
    recorded["lanes"]["flash-high@agy"]["enabled"] = False
    recorded["lanes"]["luna-low@codex"]["enabled"] = True
    rows = [
        {"model": "gpt-5.6-luna", "effort": "low", "score": 4.0, "cost_usd": 1.7,
         "uncertain": False, "source": "t", "benchmark": "b"},
        {"model": "gpt-5.6-luna", "effort": "medium", "score": 6.0, "cost_usd": 1.5,
         "uncertain": False, "source": "t", "benchmark": "b"},
    ]
    w = wizard(lanes=recorded, effort_rows=rows)
    w.handle("enter")
    w.handle("enter")
    v = w.view()
    flash = row_for(v, "flash-high@agy")
    luna = row_for(v, "luna-low@codex")
    record("24c an explicit enabled is respected, not overwritten",
           carry_of(flash) == "off" and why_of(flash) == "off in the catalog"
           # luna would be dominated by medium, but the human said on
           and carry_of(luna) == "on" and why_of(luna) == "on in the catalog"
           and any("the pre-screen leaves it" in line for line in v["legend"]))
except Exception as e:
    record("24c an explicit enabled is respected, not overwritten", False, repr(e))


try:
    rows = [
        {"model": "gpt-5.6-luna", "effort": "low", "score": 4.0, "cost_usd": 1.7,
         "uncertain": False, "source": "t", "benchmark": "b"},
        {"model": "gpt-5.6-luna", "effort": "none", "score": 10.0, "cost_usd": 0.1,
         "uncertain": True, "source": "t", "benchmark": "b"},
    ]
    w = wizard(effort_rows=rows)
    w.handle("enter")
    w.handle("enter")
    luna = row_for(w.view(), "luna-low@codex")
    record("25 uncertain rows do not dominate",
           carry_of(luna) == "on" and why_of(luna) == "not dominated")
except Exception as e:
    record("25 uncertain rows do not dominate", False, repr(e))


# --- ticket 16: rows that name a model the way a leaderboard prints it -------
# The real Terminal-Bench extraction, 18 rows, `check` accepted 18 and rejected
# 0. Every model in it is a display name, so before this the pre-screen matched
# none of them and read "no rows for this lane" against a full effort sweep.
with open(os.path.join(FIXTURES, "tbench-accepted.json"), encoding="utf-8") as f:
    TBENCH = json.load(f)


def astra_lanes():
    doc = copy.deepcopy(LANES)
    for effort in ("low", "medium", "high", "xhigh", "max"):
        lane = copy.deepcopy(doc["lanes"]["sol-high@codex"])
        lane["model"] = "gpt-6-astra"
        lane["effort"] = effort
        doc["lanes"][f"astra-{effort}@codex"] = lane
    return doc


try:
    w = wizard(lanes=astra_lanes(), effort_rows=TBENCH)
    w.handle("enter")
    w.handle("enter")
    v = w.view()
    xhigh = row_for(v, "astra-xhigh@codex")
    high = row_for(v, "astra-high@codex")
    low = row_for(v, "astra-low@codex")
    record("28 a display-name sweep switches off the dominated lane",
           w.screen == "prescreen"
           and carry_of(xhigh) == "off"
           and why_of(xhigh) == "dominated by high"
           and carry_of(high) == "on" and why_of(high) == "not dominated"
           and carry_of(low) == "on" and why_of(low) == "not dominated",
           str([xhigh["cells"], high["cells"], low["cells"]]))
except Exception as e:
    record("28 a display-name sweep switches off the dominated lane", False, repr(e))


try:
    w = wizard(lanes=astra_lanes(), effort_rows=TBENCH)
    w.handle("enter")
    w.handle("enter")
    v = w.view()
    grok = row_for(v, "grok46-high@grok")
    flash = row_for(v, "flash-high@agy")
    fable = row_for(v, "fable-xhigh@claude")
    record("28b a matched lane with one row is not dominated; an unmatched one keeps absence",
           why_of(grok) == "not dominated"
           and why_of(flash) == "not dominated"
           # Terminal-Bench prints "Fable 5.1"; no published_as says that is ours
           and why_of(fable) == "no rows for this lane"
           and any("Absence of data is not evidence against" in line
                   for line in v["legend"]),
           str([grok["cells"], flash["cells"], fable["cells"]]))
except Exception as e:
    record("28b a matched lane with one row is not dominated; an unmatched one keeps absence",
           False, repr(e))


try:
    # Terminal-Bench prints "Fable 5.1" and the lane model is
    # `claude-fable-5-1`; no formatting rule may bridge a vendor prefix, so the
    # catalog says it. The one Fable row is at max, so a max lane is what it
    # informs — an xhigh lane still has no row of its own.
    named = astra_lanes()
    named["lanes"]["fable-max@claude"] = copy.deepcopy(named["lanes"]["fable-xhigh@claude"])
    named["lanes"]["fable-max@claude"]["effort"] = "max"
    named["lanes"]["fable-max@claude"]["published_as"] = ["Fable 5.1"]
    w = wizard(lanes=named, effort_rows=TBENCH)
    w.handle("enter")
    w.handle("enter")
    v = w.view()
    fable_max = row_for(v, "fable-max@claude")
    record("28c published_as connects a name the derived rule cannot",
           why_of(fable_max) == "not dominated"
           and not any("Fable 5.1" in line for line in v["legend"]),
           str(fable_max["cells"]) + repr(v["legend"]))
except Exception as e:
    record("28c published_as connects a name the derived rule cannot", False, repr(e))


try:
    w = wizard(lanes=astra_lanes(), effort_rows=TBENCH)
    w.handle("enter")
    w.handle("enter")
    # a note about the data, so it reads as a legend line and not as an error
    # in the message slot, where `every lane needs a tier` goes
    v = w.view()
    ignored = next((line for line in v["legend"]
                    if line.startswith("no lane runs these, ignored: ")), "")
    record("28d models that are nobody's lane are listed once, not warned per lane",
           ignored
           and "GLM-5.3" in ignored and "+4 more" in ignored
           and "gpt-6-astra" not in ignored and len(ignored) <= 79
           and v["message"] == ""
           and all("no lane" not in why_of(row) for row in v["rows"]),
           repr(ignored))
except Exception as e:
    record("28d models that are nobody's lane are listed once, not warned per lane",
           False, repr(e))


try:
    from setup_tui import unmatched_message
    short = unmatched_message(["GLM-5.3", "Opus 4.8"])
    long = unmatched_message([f"A Very Long Model Name {n}" for n in range(9)])
    record("28f the ignored line lists what fits and counts the rest",
           short == "no lane runs these, ignored: GLM-5.3, Opus 4.8"
           and unmatched_message([]) == ""
           and len(long) <= 79 and long.endswith("more"),
           repr(short) + repr(long))
except Exception as e:
    record("28f the ignored line lists what fits and counts the rest", False, repr(e))


try:
    # A source that publishes slugs must go on working unchanged.
    rows = [
        {"model": "gpt-5.6-luna", "effort": "low", "score": 4.0, "cost_usd": 1.7,
         "uncertain": False, "source": "swerb", "benchmark": "b"},
        {"model": "gpt-5.6-luna", "effort": "medium", "score": 6.0, "cost_usd": 1.5,
         "uncertain": False, "source": "swerb", "benchmark": "b"},
    ]
    w = wizard(effort_rows=rows)
    w.handle("enter")
    w.handle("enter")
    luna = row_for(w.view(), "luna-low@codex")
    record("28e a slug-publishing source still matches, and rows are not mutated",
           carry_of(luna) == "off" and "dominated" in why_of(luna)
           and rows[0]["model"] == "gpt-5.6-luna", str(luna["cells"]))
except Exception as e:
    record("28e a slug-publishing source still matches, and rows are not mutated",
           False, repr(e))



try:
    w = wizard()
    start(w)
    finish(w)
    lanes, routing = w.result()
    record("26 round-trip with nothing switched off is byte-identical",
           lanes == LANES and routing == ROUTING
           and all("enabled" not in lane for lane in lanes["lanes"].values()))
except Exception as e:
    record("26 round-trip with nothing switched off is byte-identical", False, repr(e))


try:
    over = []
    w = wizard()
    screens = []
    v = w.view()
    screens.append(v)
    w.handle("enter")
    screens.append(w.view())
    w.handle("enter")
    screens.append(w.view())
    w.handle("enter")
    screens.append(w.view())
    while w.screen == "tier":
        w.handle("enter")
    screens.append(w.view())
    w.handle("enter")
    screens.append(w.view())
    extra_screens = [
        wizard(discovery=disc_unmapped).view(),
        wizard(discovery=disc_retired).view(),
        wizard(discovery=disc_nodrift).view(),
        wizard(discovery={"error": "subprocess timed out"}).view(),
        wizard(discovery={"error": "x" * 120}).view(),
        wizard(discovery=discover.discover(LANES, fixture_dir=FIXTURES_DISCOVER)).view(),
    ]
    for v in screens + extra_screens:
        for line in [v["footer"], *(v.get("legend") or []), *(v.get("body") or [])]:
            if len(line) > 80:
                over.append((v["screen"], len(line), line))
    record("27 legend and footer stay under 80", not over, repr(over))
except Exception as e:
    record("27 legend and footer stay under 80", False, repr(e))


def pty_smoke():
    with tempfile.TemporaryDirectory() as td:
        config_dir = os.path.join(td, "config")
        discover_path = os.path.join(td, "discover.json")
        discover = {
            "version": "delegate-discover.v1",
            "discovered": [{"key": key, "binary": key, "version": "test",
                            "authenticated": True} for key in catalog.HARNESSES],
            "missing": [],
        }
        with open(discover_path, "w", encoding="utf-8") as f:
            json.dump(discover, f)
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 140, 0, 0))
        env = dict(os.environ, TERM="xterm-256color", LINES="40", COLUMNS="140")
        proc = subprocess.Popen(
            [sys.executable, os.path.join(DELEGATE_DIR, "setup.py"),
             "--config-dir", config_dir, "--discover-json", discover_path,
             "--epoch-csv", FIXTURE,
             "--fixture-dir", FIXTURES_DISCOVER],
            stdin=slave, stdout=slave, stderr=slave, cwd=DELEGATE_DIR, env=env,
            close_fds=True,
        )
        os.close(slave)
        output = bytearray()
        deadline = time.monotonic() + 30
        try:
            os.set_blocking(master, False)
            for key in [b"\n"] * 8 + [b"y"]:
                try:
                    while chunk := os.read(master, 65536):
                        output.extend(chunk)
                except BlockingIOError:
                    pass
                os.write(master, key)
                time.sleep(0.3)
            while proc.poll() is None and time.monotonic() < deadline:
                try:
                    while chunk := os.read(master, 65536):
                        output.extend(chunk)
                except BlockingIOError:
                    pass
                time.sleep(0.05)
        finally:
            os.close(master)
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        lanes_path = os.path.join(config_dir, "lanes.json")
        routing_path = os.path.join(config_dir, "routing.json")
        if proc.returncode != 0 or not os.path.isfile(lanes_path) or not os.path.isfile(routing_path):
            return False, (f"exit={proc.returncode} lanes={os.path.isfile(lanes_path)} "
                           f"routing={os.path.isfile(routing_path)} output={bytes(output[-1000:])!r}")
        catalog.check_file(lanes_path)
        catalog.check_file(routing_path)
        return True, ""


try:
    ok, detail = pty_smoke()
    record("10 pty smoke", ok, detail)
except OSError as e:
    print(f"SKIP pty smoke: {e}")
except Exception as e:
    record("10 pty smoke", False, repr(e))

try:
    # every screen with a predecessor can reach it. discovery advanced on any key,
    # so `b` there moved FORWARD, which is the one thing a back key must not do.
    w = wizard()
    w.handle("enter")
    assert w.screen == "discovery", w.screen
    w.handle("b")
    back_to_start = w.screen == "start"

    w.handle("enter"); w.handle("enter")
    assert w.screen == "prescreen", w.screen
    w.handle("b")
    back_to_discovery = w.screen == "discovery"

    w.handle("enter"); w.handle("enter")
    assert w.screen == "tier" and w.tier == 4, (w.screen, w.tier)
    w.handle("b")
    back_to_prescreen = w.screen == "prescreen"

    record("every screen with a predecessor has a working back key",
           back_to_start and back_to_discovery and back_to_prescreen,
           f"start={back_to_start} discovery={back_to_discovery} prescreen={back_to_prescreen}")
except Exception as e:
    record("every screen with a predecessor has a working back key", False, repr(e))


try:
    # the step marker brackets exactly the screen you are on, and fits 80 columns
    w = wizard()
    marks = []
    for _ in range(9):
        v = w.view()
        if v["screen"] in ("routing", "confirm", "done", "quit"):
            marks.append((v["screen"], v["steps"]))
            break
        marks.append((v["screen"], v["steps"]))
        w.handle("enter")

    expected = {"start": "[start]", "discovery": "[harnesses]", "prescreen": "[carry]",
                "routing": "[routing]"}
    ok = all(len(m) <= 79 for _, m in marks)
    ok = ok and all(m.count("[") == 1 and m.count("]") == 1 for _, m in marks)
    for screen, m in marks:
        if screen in expected:
            ok = ok and expected[screen] in m
    tier_marks = [m for sc, m in marks if sc == "tier"]
    ok = ok and ["[T4]" in tier_marks[0], "[T3]" in tier_marks[1]] == [True, True]
    # the terminal screens have no step to be at
    w2 = wizard(); w2.handle("q")
    ok = ok and w2.view()["steps"] == ""
    record("step marker brackets the current screen and fits 80 columns", ok,
           f"marks={marks[:3]}")
except Exception as e:
    record("step marker brackets the current screen and fits 80 columns", False, repr(e))


# --- what the screen actually says ------------------------------------------
# Every fault below was invisible to a test that read only the frame dict. The
# pre-screen at 80 places dropped its reason column outright, a tier tag reached
# the eye as `ti`, and eight of eleven lanes could scroll away in silence.
from setup_tui import ROW_FLOOR, _clip, _fit_table, layout_lines  # noqa: E402


def screen(view, width=80, height=24):
    """The grid a terminal of this size shows, one string per row."""
    grid = [""] * height
    for y, text, _role in layout_lines(view, width, height):
        if 0 <= y < height:
            grid[y] = text[: width - 1]
    return grid


def prescreen_at(width, height=24):
    w = wizard(lanes=astra_lanes(), effort_rows=TBENCH)
    w.handle("enter")
    w.handle("enter")
    return w, screen(w.view(), width, height)


try:
    w, grid = prescreen_at(80)
    reasons = [why_of(row) for row in w.view()["rows"]]
    body = "\n".join(grid)
    record("29 every pre-screen reason is whole at 80 columns",
           "why" in grid[2]
           and all(reason in body for reason in reasons)
           and "dominated by high" in body
           and "…" not in body,
           repr([r for r in reasons if r not in body]) + "\n" + body)
except Exception as e:
    record("29 every pre-screen reason is whole at 80 columns", False, repr(e))


try:
    # 80 columns is the documented minimum, so the reason column has to survive
    # there. It is elastic: narrowed, never dropped.
    v = wizard(lanes=astra_lanes(), effort_rows=TBENCH)
    v.handle("enter")
    v.handle("enter")
    view = v.view()
    kept = []
    for width in (80, 90, 100, 140):
        chosen, widths = _fit_table(view, width)
        kept.append(view["columns"].index("why") in chosen)
    record("30 the reason column is narrowed, never dropped",
           all(kept) and view["elastic"] == "why", repr(kept))
except Exception as e:
    record("30 the reason column is narrowed, never dropped", False, repr(e))


try:
    # `tier 3` used to be written after the last column and clipped with the
    # line, so it arrived as `ti`. The tier is in the box now and `off` is the
    # only tag; the renderer keeps room for it at any width.
    w = wizard(lanes=astra_lanes())
    start(w)
    move_to(w, "sol-high@codex")
    w.handle("space")
    w.handle("enter")
    move_to(w, "terra-high@codex")
    w.handle("x")
    tagged = []
    for width in (80, 100, 140):
        grid = screen(w.view(), width, 30)
        sol = next(line for line in grid if line.startswith("[4]   sol-high@codex"))
        terra = next(line for line in grid if "terra-high@codex" in line)
        tagged.append(sol.strip().endswith("(n=5)") and terra.rstrip().endswith("off"))
    record("31 an assigned tier reads from the box and no tag is clipped",
           all(tagged), repr(tagged))
except Exception as e:
    record("31 an assigned tier reads from the box and no tag is clipped", False, repr(e))


try:
    # a window too short for the list said nothing about it
    w, grid = prescreen_at(80, 16)
    shown = [line for line in grid if line.startswith("[x]") or line.startswith("[ ]")]
    w2, tall = prescreen_at(80, 40)
    record("32 a clipped list says which rows are on screen",
           grid[0].rstrip().endswith(f"1-{len(shown)} of {len(w.view()['rows'])}")
           and len(shown) >= ROW_FLOOR
           and "of" not in tall[0].split("Lanes to carry")[1],
           repr(grid[0]) + repr(tall[0]))
except Exception as e:
    record("32 a clipped list says which rows are on screen", False, repr(e))


try:
    # the confirm screen is the last look at what will be written, and at 80x24
    # nine of its twenty items were out of sight with no key that reached them
    w = wizard(lanes=astra_lanes())
    start(w)
    to_confirm(w)
    assert w.screen == "confirm", w.screen
    rows = w.view()["rows"]
    for _ in range(len(rows) - 1):
        w.handle("down")
    grid = screen(w.view(), 80, 24)
    text = "\n".join(grid)
    still_confirm = w.screen == "confirm"
    w.handle("y")
    record("33 the confirm list can be read to its end",
           still_confirm and w.result() is not None
           and "/tmp/lanes.json" in text and "/tmp/routing.json" in text
           and "margin" in text and "gate" in text, text)
except Exception as e:
    record("33 the confirm list can be read to its end", False, repr(e))


try:
    # test 27 walks the sample catalog, where no tier holds enough lanes to
    # overflow a line. Six astra lanes on one tier ran the tier map past column
    # 80, where it was cut after a comma.
    w = wizard(lanes=astra_lanes())
    start(w)
    for _ in range(len(w.view()["rows"])):
        if not next(r for r in w.view()["rows"] if r["cursor"])["marked"]:
            w.handle("space")
        w.handle("down")
    while w.screen == "tier":
        w.handle("enter")
    routing_view = w.view()
    w.handle("enter")
    over = []
    for view in (routing_view, w.view()):
        for line in [view["footer"], *(view.get("legend") or []),
                     *(view.get("body") or []), view["title"]]:
            if len(line) > 79:
                over.append((view["screen"], len(line), line))
    tier_map = [line for line in routing_view["legend"] if line.startswith("tier ")]
    record("34 a crowded tier map still fits the line",
           not over and any("more)" in line for line in tier_map), repr(over or tier_map))
except Exception as e:
    record("34 a crowded tier map still fits the line", False, repr(e))


try:
    record("35 a shortened cell says it was shortened",
           _clip("dominated by medium", 19) == "dominated by medium"
           and _clip("dominated by medium", 12) == "dominated b…"
           and _clip("x", 0) == "" and _clip("abc", 1) == "…")
except Exception as e:
    record("35 a shortened cell says it was shortened", False, repr(e))


try:
    # a column skipped over while a narrower one behind it is drawn reads as
    # data nobody gathered
    w = wizard()
    start(w)
    view = w.view()
    chosen, _widths = _fit_table(view, 100)
    names = [view["columns"][i] for i in chosen]
    benchmarks = [n for n in view["columns"] if n in (w.bench or {}).get("epoch_benchmarks", [])]
    visible = [n for n in names if n in benchmarks]
    record("36 the benchmark columns shown are a prefix of the ones asked for",
           visible == benchmarks[:len(visible)] and visible, repr(names))
except Exception as e:
    record("36 the benchmark columns shown are a prefix of the ones asked for", False, repr(e))


sys.exit(1 if fails else 0)
