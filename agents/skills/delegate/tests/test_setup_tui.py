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

# Run from a fresh directory with no Git root above it, so that
# `catalog.find_git_root()` never finds the invoking checkout's own
# `.delegate/routing.json`. Every path this file needs comes from HERE.
_ISOLATED_CWD = tempfile.TemporaryDirectory(prefix="delegate-test-")
os.chdir(_ISOLATED_CWD.name)
DELEGATE_DIR = os.path.abspath(os.path.join(HERE, "..", "scripts"))
FIXTURE = os.path.join(HERE, "fixture", "bench-epoch.csv")
FIXTURES = os.path.join(HERE, "fixtures")
FIXTURES_DISCOVER = os.path.join(FIXTURES, "discover")
sys.path.insert(0, DELEGATE_DIR)

import bench
import catalog
import discover
import effort
import setup_tui
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
    return bench.collect(copy.deepcopy(LANES), epoch_csv=FIXTURE)


def wizard(bench_data=True, message="", effort_rows=None, lanes=None, discovery=None,
           focus=None):
    return Wizard(copy.deepcopy(lanes if lanes is not None else LANES),
                  copy.deepcopy(ROUTING),
                  data() if bench_data else None, DISCOVERED,
                  "/tmp/lanes.json", "/tmp/routing.json", message,
                  effort_rows=effort_rows, discovery=discovery, focus=focus)


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
    if w.screen == "review":
        w.handle("enter")
    if w.screen == "routing":
        w.handle("enter")
    if w.screen == "confirm":
        w.handle("y")


def mark_as(w, tiers):
    """On each tier page from the one on screen down, mark the lanes `tiers`
    gives that tier, then enter."""
    while w.screen == "tier":
        for row in w.view()["rows"]:
            name = row["cells"][1]
            if (tiers.get(name) == w.tier) != row["marked"]:
                move_to(w, name)
                w.handle("space")
        w.handle("enter")


def incoming_tiers(doc):
    return {name: lane["tier"] for name, lane in doc["lanes"].items()}


def all_tier_one(doc):
    """Return a copy in which every lane is assigned to tier 1."""
    out = copy.deepcopy(doc)
    for lane in out["lanes"].values():
        lane["tier"] = 1
    return out


def strip_order(doc):
    """A written catalog without the `order` the review page adds (ticket 28)."""
    out = copy.deepcopy(doc)
    for lane in out["lanes"].values():
        lane.pop("order", None)
    return out


def orders_are_places(doc):
    """Every carried lane has `order`, and each tier's orders are 1..n; no lane
    that is off has one."""
    by_tier = {}
    for lane in doc["lanes"].values():
        if lane.get("enabled", True):
            by_tier.setdefault(lane["tier"], []).append(lane.get("order"))
        elif "order" in lane:
            return False
    return all(sorted(o for o in orders if o is not None) == list(range(1, len(orders) + 1))
               and None not in orders for orders in by_tier.values())


def review_layout(view):
    """The review page as [(tier, [lane, ...])], 4 to 1, read off its section rows."""
    out = []
    for row in view["rows"]:
        if row.get("section"):
            out.append((int(row["section"].split()[1]), []))
        else:
            out[-1][1].append(row["cells"][1])
    return out


def review_names(view):
    return [name for _tier, names in review_layout(view) for name in names]


try:
    collected = data()
    record("collect returns documented keys",
           set(collected) == {"models", "lanes", "epoch_benchmarks", "aa_columns",
                              "aa_skipped", "notes"}, str(sorted(collected)))
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
    # a lane is ranked on its own figures: sol runs high and was measured at
    # high, so it leads; fable runs xhigh and its model was only measured at
    # max, so it has no figure here at all, the same as flash, which nobody
    # measured. The old screen showed fable the max figure (ticket 17).
    record("1 tier 4 opens with current marks, in benchmark order",
           v["tier"] == 4
           and {r["cells"][1] for r in v["rows"] if r["marked"]} == {"fable-xhigh@claude"}
           and fable["marked"]
           and models[:2] == ["gpt-5.6-sol", "gpt-5.6-terra"]
           and models[-2:] == ["claude-fable-5-1", "gemini-3.8-flash-high"]
           and "90.0" in sol["cells"] and sol["cells"][9] == "1.0 (n=5)"
           and all(x == "—" for x in fable["cells"][4:9])
           and fable["cells"][9] == "— (n=0)"
           and all(x == "—" for x in flash["cells"][4:9])
           and flash["cells"][9].startswith("—"), str(v))
except Exception as e:
    record("1 tier 4 opens with current marks, in benchmark order", False, repr(e))

try:
    w = wizard()
    start(w)
    restored = []
    while w.screen == "tier":
        expected = {
            name for name, lane in LANES["lanes"].items()
            if lane.get("enabled", True) and lane["tier"] == w.tier
        }
        marked = {row["cells"][1] for row in w.view()["rows"] if row["marked"]}
        restored.append(marked == expected)
        w.handle("enter")
    finish(w)
    record("1a the TUI restores the current catalog tiers and enter preserves them",
           restored == [True, True, True, True]
           and strip_order(w.result()[0]) == LANES
           and w.result()[1] == ROUTING,
           repr((restored, w.result())))
except Exception as e:
    record("1a the TUI restores the current catalog tiers and enter preserves them", False, repr(e))

try:
    # Whatever lanes.json holds is the editable starting state. Here every lane
    # is already tier 4, so tier 4 starts fully marked and lower pages are empty.
    every_four = copy.deepcopy(LANES)
    for lane in every_four["lanes"].values():
        lane["tier"] = 4
    w = wizard(lanes=every_four)
    start(w)
    pages = []
    while w.screen == "tier":
        rows = w.view()["rows"]
        pages.append((w.tier, len(rows), sum(1 for row in rows if row["marked"])))
        w.handle("enter")
    record("1b every tier page restores lanes.json",
           pages == [(4, len(every_four["lanes"]), len(every_four["lanes"])),
                     (3, 0, 0), (2, 0, 0), (1, 0, 0)]
           and w.screen == "review", repr(pages))
except Exception as e:
    record("1b every tier page restores lanes.json", False, repr(e))

try:
    w = wizard()
    start(w)
    mark_as(w, incoming_tiers(LANES))
    finish(w)
    # the review page adds each carried lane's place inside its tier (ticket 28)
    record("2 marking the incoming tiers writes the catalog back unchanged but for order",
           strip_order(w.result()[0]) == LANES and w.result()[1] == ROUTING
           and orders_are_places(w.result()[0]), repr(w.result()))
    w = wizard()
    start(w)
    finish(w)
    record("2b enter straight through preserves every current tier",
           strip_order(w.result()[0]) == LANES and w.result()[1] == ROUTING
           and orders_are_places(w.result()[0]), repr(w.result()))
except Exception as e:
    record("2 marking the incoming tiers writes the catalog back unchanged", False, repr(e))

try:
    w = wizard()
    start(w)
    move_to(w, "sol-high@codex")
    w.handle("space")
    w.handle("enter")
    below = []
    while w.screen == "tier":
        below.append("sol-high@codex" not in [r["cells"][1] for r in w.view()["rows"]])
        w.handle("enter")
    finish(w)
    lanes, _ = w.result()
    record("3 a lane assigned at tier N shows on no page below N, and keeps N",
           below == [True, True, True]
           and lanes["lanes"]["sol-high@codex"]["tier"] == 4
           and lanes["lanes"]["terra-high@codex"]["tier"] == 2, repr(below))
except Exception as e:
    record("3 a lane assigned at tier N shows on no page below N, and keeps N", False, repr(e))

try:
    plain, pressed = wizard(), wizard()
    for w in (plain, pressed):
        start(w)
        w.handle("enter")
        w.handle("enter")
        move_to(w, "grok46-high@grok")
    pressed.handle("4")
    same_page = pressed.view()["rows"] == plain.view()["rows"]
    finish(plain)
    finish(pressed)
    record("4 digit keys are inert on the tier screen",
           same_page and pressed.result() == plain.result())
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
    record("5 tier 1 requires every lane", blocked and w.screen == "review")
except Exception as e:
    record("5 tier 1 requires every lane", False, repr(e))

try:
    w = wizard()
    start(w)
    for _ in range(5):
        w.handle("enter")
    assert w.screen == "routing", w.screen
    for _ in range(3):
        w.handle("down")
    w.handle("plus")
    for _ in range(7):
        w.handle("down")
    w.handle("plus")
    w.handle("enter")
    w.handle("y")
    lanes, routing = w.result()
    expected = copy.deepcopy(ROUTING)
    expected["classes"]["mechanical"]["ceiling"] = 3
    expected["margin"] = 0.25
    record("6 routing edits are isolated", strip_order(lanes) == LANES and routing == expected, repr(routing))
except Exception as e:
    record("6 routing edits are isolated", False, repr(e))

try:
    w1 = wizard(); start(w1); finish(w1)
    # finish accepts, so use a fresh wizard stopped at confirm for decline.
    w1 = wizard(); start(w1)
    for _ in range(6): w1.handle("enter")
    assert w1.screen == "confirm", w1.screen
    w1.handle("n")
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
    w = wizard()
    start(w)
    w.handle("enter")
    move_to(w, "terra-high@codex")
    w.handle("space")
    w.handle("b")
    w.handle("enter")
    terra = next(row for row in w.view()["rows"] if row["cells"][1] == "terra-high@codex")
    record("8b back and forward preserve edits on a tier not yet submitted",
           w.tier == 3 and terra["marked"])
except Exception as e:
    record("8b back and forward preserve edits on a tier not yet submitted", False, repr(e))

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
    # facts only (ticket 25): the terms live in CONTEXT.md
    record("11i the start page states facts and defines no term",
           "Benchmark page: (not written)" in body and "Model discovery" in body
           and body.splitlines()[:3] == [f"Will write {w.lanes_path}", f"Will write {w.routing_path}",
                                         "Benchmark page: (not written)"]
           and not any(word in body for word in ("capability", "judgement", "floor", "ceiling",
                                                 "Tier is", "Assign each lane")),
           body)
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
           # One decision per line, so one gesture, named once. The tier screen
           # used to advertise `x: on/off` beside `space: mark`, which was the
           # carry screen's decision offered a second time.
           and "space/x: flip" in w.view()["footer"]
           and "on/off" not in footer
           and "o: bench" in footer)

    before_cursor = w.cursor
    w.handle("d")
    record("12b d is unbound on tier",
           w.screen == "tier" and w.cursor == before_cursor and w.tier == 4)

    w2 = wizard()
    w2.handle("enter")
    w2.handle("enter")
    carry_footer = w2.view()["footer"]
    record("12c one gesture flips the box, and both screens name that one",
           w2.screen == "prescreen"
           and "space/x: flip" in carry_footer
           and carry_footer.count("flip") == 1
           and w.view()["footer"].count("flip") == 1,
           repr(carry_footer) + repr(w.view()["footer"]))
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
    w.handle("enter")
    legend = w.view().get("legend") or []
    tier_map = next(line for line in legend if line.startswith("Lanes carried: "))
    counts = tier_map.removeprefix("Lanes carried: ").split(" · ")
    panels = {}
    landings = []
    for index in range(len(w._routing_settings())):
        view = w.view()
        row = next(r for r in view["rows"] if r["cursor"])
        # the cursor lands on a setting, indented under its group, never on
        # a group heading; the panel is headed by the setting's full name
        landings.append(row["cells"][0].startswith("  ") and not row.get("styles"))
        panels[view["panel"][0].split(":")[0]] = view["panel"]
        w.handle("down")
    record("13 routing legend maps this session's assignments, and a panel explains the setting",
           w.screen == "routing"
           and incoming_sol != 4
           # counts only: the session's move of sol-high to tier 4 is in them
           and "sol-high@codex" in w._lanes_at(4)
           and "sol-high@codex" not in w._lanes_at(incoming_sol)
           and counts == [f"tier {t}: {len(w._lanes_at(t))}" for t in range(1, 5)]
           and all(landings) and len(landings) == 13
           # the explanation moved beside the table: one per setting, headed by it
           and set(panels) == {f"{c} {k}" for c in catalog.CLASSES for k in ("floor", "ceiling")} | {"margin", "gate", "meters"}
           and panels["scout floor"][0] == "scout floor: 2"
           and any("lowest tier" in p for p in panels["scout floor"])
           and any("highest tier" in p for p in panels["review ceiling"])
           # the range names this session's lanes: mechanical 1-2 takes the tier-1 lanes
           and any("luna-low@codex" in p for p in panels["mechanical ceiling"])
           and not any("sol-high@codex" in p for p in panels["review ceiling"])
           and panels["margin"][0] == "margin: 0.2" and any("pace" in p.lower() for p in panels["margin"])
           and panels["gate"][0] == "gate: 0.1" and any("10% remaining" in p for p in panels["gate"])
           and panels["meters"][0] == "meters: on" and any("Tier, Order" in p for p in panels["meters"]),
           repr(panels))
    w.handle("enter")
    confirm_defs = {d["term"]: d for d in w.view().get("defs") or []}
    record("14 confirm legend explains classes, margin and gate",
           w.screen == "confirm"
           and list(confirm_defs) == ["classes", "margin", "gate", "meters", "off"]
           and confirm_defs["margin"]["value"] == "0.2"
           and confirm_defs["gate"]["value"] == "0.1"
           and confirm_defs["meters"]["value"] == "on"
           and "10%" in confirm_defs["gate"]["text"]
           and not w.view()["legend"]
           # the longest term, two spaces, the longest value, two spaces, the text
           and all(7 + 2 + 3 + 2 + len(d["text"]) <= 79 for d in confirm_defs.values()))
    w.handle("y")
    lanes, routing = w.result()
    record("15 key sequence write path is unchanged",
           lanes["lanes"]["sol-high@codex"]["tier"] == 4
           and routing == ROUTING)
except Exception as e:
    record("13 routing legend maps this session's assignments", False, repr(e))


VIEW_KEYS = {"screen", "title", "tier", "columns", "rows", "footer", "message", "body",
              "legend", "steps", "elastic", "panel", "defs", "warnings"}


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
    if w.screen == "review":
        w.handle("enter")
    if w.screen == "routing":
        w.handle("enter")


def not_carried(w, *lanes):
    """Leave `lanes` uncarried on the carry screen, then go on to tier 4.

    Carry is decided here and nowhere else, so a test that wants an off lane on
    a tier screen has to come through this screen to get one.
    """
    w.handle("enter")
    w.handle("enter")
    assert w.screen == "prescreen", w.screen
    for lane in lanes:
        move_to(w, lane)
        w.handle("x")
        assert not w._enabled[lane], lane
    w.handle("enter")
    assert w.screen == "tier" and w.tier == 4, (w.screen, w.tier)


try:
    # The tier screen makes one decision: does this lane take the tier on
    # screen. `x` used to switch the lane off here as well, which asked the
    # carry screen's question a second time and gave this line's box two
    # meanings. Both keys now do the one thing, and neither touches carry.
    w = wizard()
    start(w)
    cursor_name = next(r["cells"][1] for r in w.view()["rows"] if r["cursor"])
    enabled_before = dict(w._enabled)
    assigned_before = dict(w._assigned)
    others = {r["cells"][1]: (r["marked"], r["cells"][0], r["tag"])
              for r in w.view()["rows"] if r["cells"][1] != cursor_name}
    marked_before = row_for(w.view(), cursor_name)["marked"]
    w.handle("x")
    after_x = row_for(w.view(), cursor_name)
    others_after = {r["cells"][1]: (r["marked"], r["cells"][0], r["tag"])
                    for r in w.view()["rows"] if r["cells"][1] != cursor_name}
    w.handle("space")
    after_space = row_for(w.view(), cursor_name)
    record("16 space and x are one mark gesture, and neither switches a lane off",
           w.screen == "tier" and w.tier == 4
           and w._assigned == assigned_before
           and after_x["marked"] is not marked_before
           and after_x["cells"][0] == ("[x]" if after_x["marked"] else "[ ]")
           # space undoes what x did, so the two are the same control
           and after_space["marked"] is marked_before
           and w._enabled == enabled_before
           and after_x["tag"] == "" and after_space["tag"] == ""
           and others_after == others,
           repr((marked_before, after_x["cells"][0], after_space["cells"][0])))
except Exception as e:
    record("16 space and x are one mark gesture, and neither switches a lane off",
           False, repr(e))


try:
    # The same two keys on the carry screen flip the same box, and only the
    # cursor row's.
    w = wizard()
    w.handle("enter")
    w.handle("enter")
    cursor_name = next(r["cells"][1] for r in w.view()["rows"] if r["cursor"])
    enabled_before = dict(w._enabled)
    others = {r["cells"][1]: (r["marked"], r["cells"][0], r["tag"])
              for r in w.view()["rows"] if r["cells"][1] != cursor_name}
    w.handle("space")
    v = w.view()
    flipped = row_for(v, cursor_name)
    others_after = {r["cells"][1]: (r["marked"], r["cells"][0], r["tag"])
                    for r in v["rows"] if r["cells"][1] != cursor_name}
    w.handle("x")
    back = row_for(w.view(), cursor_name)
    record("16b on the carry screen both keys flip only the cursor row",
           w.screen == "prescreen"
           and enabled_before[cursor_name] is True
           # space flipped it, and only it
           and carry_of(flipped) == "off" and flipped["dimmed"]
           and others_after == others
           # x undid what space did, so the two are the same control here too
           and carry_of(back) == "on"
           and w._enabled == enabled_before,
           repr((flipped["cells"][0], back["cells"][0])))
except Exception as e:
    record("16b on the carry screen both keys flip only the cursor row",
           False, repr(e))


try:
    # A lane switched off on the carry page is asked about nowhere else: it is
    # on no tier page, so no key there can mark it (ticket 25).
    w = wizard()
    not_carried(w, "flash-high@agy")
    listed, marked_ever = [], False
    while w.screen == "tier":
        listed.append("flash-high@agy" in [r["cells"][1] for r in w.view()["rows"]])
        for _ in range(len(w.view()["rows"]) + 1):
            w.handle("space")
            w.handle("x")
            w.handle("space")
            w.handle("down")
        marked_ever = marked_ever or any("flash-high@agy" in marks for marks in w._marks.values())
        w.handle("enter")
    review = [r["cells"][4] for r in w.view()["rows"]]
    record("17 a lane switched off on the carry page shows on no tier page, and space cannot mark it",
           listed == [False, False, False, False] and not marked_ever
           and w.screen == "review" and "flash-high@agy" not in review
           and w._assigned["flash-high@agy"] == LANES["lanes"]["flash-high@agy"]["tier"],
           repr((listed, review)))
except Exception as e:
    record("17 a lane switched off on the carry page shows on no tier page, and space cannot mark it",
           False, repr(e))


try:
    # Nobody is asked a tier for a lane that is not carried, so it keeps the one
    # the catalog has: 3 here. Carried lanes also start with their catalog tiers.
    incoming = copy.deepcopy(LANES)
    incoming["lanes"]["flash-high@agy"]["tier"] = 3
    w = wizard(lanes=incoming)
    not_carried(w, "flash-high@agy")
    while w.tier != 1:
        w.handle("enter")
    move_to(w, "luna-low@codex")
    w.handle("space")
    w.handle("enter")
    blocked = w.screen == "tier" and w.tier == 1 and w.view()["message"] == "every lane needs a tier"
    w.handle("space")
    w.handle("enter")
    record("18 the tier-1 rule covers only the lanes still open",
           blocked and w.screen == "review")
    to_confirm(w)
    w.handle("y")
    lanes, _ = w.result()
    record("18b a lane not carried is written off, with the tier the catalog had",
           lanes["lanes"]["flash-high@agy"]["tier"] == 3
           and lanes["lanes"]["flash-high@agy"]["enabled"] is False
           and lanes["lanes"]["luna-low@codex"]["tier"] == 1)
except Exception as e:
    record("18 the tier-1 rule covers only the lanes still open", False, repr(e))


try:
    # the review page: every carried lane in a section for its tier, 4 to 1,
    # numbered in its order (ticket 28; it was one box per tier before)
    w = wizard()
    not_carried(w, "flash-high@agy")
    move_to(w, "sol-high@codex")
    w.handle("space")
    w.handle("enter")          # sol takes tier 4
    move_to(w, "terra-high@codex")
    w.handle("space")
    w.handle("enter")          # terra takes tier 3
    w.handle("enter")          # tier 2 takes nothing
    w.handle("enter")          # tier 1 takes the rest
    v = w.view()
    layout = review_layout(v)
    names = review_names(v)
    carried = [n for n in LANES["lanes"] if n != "flash-high@agy"]
    lane_rows = [r for r in v["rows"] if not r.get("section")]
    shape = (w.screen == "review" and v["columns"][:2] == ["#", "lane"]
             and [tier for tier, _ in layout] == [4, 3, 2, 1]
             and layout[0][1] == ["sol-high@codex", "fable-xhigh@claude"]
             and layout[1][1] == ["terra-high@codex"]
             and layout[2][1] == ["grok46-high@grok"]
             and sorted(names) == sorted(carried)
             and [r["cells"][0].strip() for r in lane_rows] == ["1", "2", "1", "1", "1"]
             and "[review]" in v["steps"] and "J/K: move lane" in v["footer"] and "1-4: tier" in v["footer"])
    move_to(w, "terra-high@codex")
    w.handle("2")              # terra to the end of tier 2, and the cursor with it
    move_to(w, "sol-high@codex")
    w.handle("3")              # sol to tier 3
    after = review_layout(w.view())
    w.handle("9")              # not a tier
    w.handle("enter")
    at_routing = w.screen == "routing"
    w.handle("b")
    back = w.screen == "review" and review_layout(w.view()) == after
    w.handle("enter")
    w.handle("enter")
    w.handle("y")
    lanes, _ = w.result()
    record("39 after tier 1 a review page lists every carried lane under its tier, numbered; j/k move, "
           "1-4 move a lane to that tier, enter goes to routing and b from routing returns to it",
           shape
           and dict(after)[3] == ["sol-high@codex"]
           and dict(after)[2] == ["grok46-high@grok", "terra-high@codex"]
           and at_routing and back
           and lanes["lanes"]["sol-high@codex"]["tier"] == 3 and lanes["lanes"]["sol-high@codex"]["order"] == 1
           and lanes["lanes"]["terra-high@codex"]["tier"] == 2 and lanes["lanes"]["terra-high@codex"]["order"] == 2
           and lanes["lanes"]["flash-high@agy"]["tier"] == LANES["lanes"]["flash-high@agy"]["tier"]
           and "order" not in lanes["lanes"]["flash-high@agy"]
           and orders_are_places(lanes)
           and "1 lane not carried keeps its catalog tier." in v["legend"],
           repr((layout, after, v["legend"])))
    w2 = wizard()
    start(w2)
    for _ in range(4):
        w2.handle("enter")
    w2.handle("b")
    record("39b b on the review page returns to tier 1, with every open lane ticked",
           w2.screen == "tier" and w2.tier == 1
           and all(r["marked"] for r in w2.view()["rows"]) and w2.view()["rows"])
except Exception as e:
    record("39 after tier 1 a review page lists every carried lane with its tier; j/k move, 1-4 set it, "
           "enter goes to routing and b from routing returns to it", False, repr(e))


try:
    w = wizard()
    not_carried(w, "flash-high@agy")
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
           and any("enabled: false" in d["text"] for d in (confirm.get("defs") or [])))
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
    defs = w.view()["defs"]
    record("23 ultra is proposed off with both reasons",
           w.screen == "prescreen"
           and carry_of(ultra) == "off" and ultra["tag"] == ""
           and why_of(ultra) == "ultra, never carried"
           # the phrase fits the column; the sentence it stands for is the
           # definition that only an ultra lane on screen earns
           and any(d["term"] == "ultra" and "no source scores it" in d["text"]
                   and "worker preamble" in d["text"] for d in defs))
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
           carry_of(luna) == "off" and "wins on" in why_of(luna)
           and carry_of(sol) == "on" and why_of(sol) == "not dominated"
           and carry_of(flash) == "on" and why_of(flash) == "no rows for this lane"
           and any(d["term"] == "no rows" and "not evidence against" in d["text"]
                   for d in v["defs"]))
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
           carry_of(luna) == "on" and "wins on" not in why_of(luna))
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
           and any(d["term"] == "in the catalog" and "the pre-screen leaves it" in d["text"]
                   for d in v["defs"]))
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


def luna_lanes():
    doc = copy.deepcopy(LANES)
    for effort in ("low", "medium", "high"):
        lane = copy.deepcopy(LANES["lanes"]["luna-low@codex"])
        lane["effort"] = effort
        doc["lanes"][f"luna-{effort}@codex"] = lane
    return doc


def board_row(effort, benchmark, score, cost, **extra):
    row = {"model": "gpt-5.6-luna", "effort": effort, "benchmark": benchmark,
           "score": score, "cost_usd": cost, "uncertain": False, "source": "aa"}
    row.update(extra)
    return row


try:
    # One source scoring each effort on several benchmarks: a lane is dominated
    # when another effort, for no more money, does at least as well on most of
    # the benchmarks the two share. One benchmark in eight is not most — on the
    # live Artificial Analysis page that reading switched twelve lanes off.
    rows = [
        board_row("medium", "b1", 0.6, 1.0), board_row("high", "b1", 0.5, 2.0),
        board_row("medium", "b2", 0.6, 1.0), board_row("high", "b2", 0.5, 2.0),
        board_row("medium", "b3", 0.4, 1.0), board_row("high", "b3", 0.5, 2.0),
        # low is ahead of medium on b1 only: one of three is not most
        board_row("low", "b1", 0.7, 0.5), board_row("low", "b2", 0.1, 0.5),
        board_row("low", "b3", 0.1, 0.5),
    ]
    w = wizard(lanes=luna_lanes(), effort_rows=rows)
    w.handle("enter")
    w.handle("enter")
    v = w.view()
    high, medium, low = (row_for(v, f"luna-{e}@codex") for e in ("high", "medium", "low"))
    record("25b dominated means beaten on most of a source's benchmarks, and the reason names the source",
           carry_of(high) == "off" and why_of(high) == "medium wins on aa"
           and carry_of(medium) == "on" and why_of(medium) == "not dominated"
           and carry_of(low) == "on" and why_of(low) == "not dominated",
           str([high["cells"], medium["cells"], low["cells"]]))
except Exception as e:
    record("25b dominated means beaten on most of a source's benchmarks, and the reason names the source",
           False, repr(e))


try:
    # Artificial Analysis publishes a composite index whose weighting it does not
    # publish. It is a row a reader can see, never a vote: here the components
    # split one each, and the index must not break the tie.
    rows = [
        board_row("medium", "b1", 0.6, 1.0), board_row("high", "b1", 0.5, 2.0),
        board_row("medium", "b2", 0.4, 1.0), board_row("high", "b2", 0.5, 2.0),
        board_row("medium", "index", 50.0, 1.0, composite=True),
        board_row("high", "index", 40.0, 2.0, composite=True),
    ]
    w = wizard(lanes=luna_lanes(), effort_rows=rows)
    w.handle("enter")
    w.handle("enter")
    high = row_for(w.view(), "luna-high@codex")
    record("25c the composite index never decides a lane",
           carry_of(high) == "on" and why_of(high) == "not dominated",
           str(high["cells"]))
except Exception as e:
    record("25c the composite index never decides a lane", False, repr(e))


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
           and why_of(xhigh) == "high wins on tbench"
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
           and any(d["term"] == "no rows" and "not evidence against" in d["text"]
                   for d in v["defs"]),
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


# --- ticket 18: the rows `effort.py aa` reads off one Artificial Analysis page --
try:
    with open(os.path.join(FIXTURES, "real_aa_model_page_sample.html"), "rb") as f:
        _packet, AA_ROWS = effort.aa_extract(f.read(), observed="2026-09-11")
    doc = astra_lanes()
    lane_models = {lane["model"] for lane in doc["lanes"].values()}
    resolved = {(r["model"], catalog.resolve_published_model(r["model"], doc)) for r in AA_ROWS}
    _rows, unmatched = setup_tui.resolve_effort_rows(doc, AA_ROWS)
    w = wizard(lanes=doc, effort_rows=AA_ROWS)
    w.handle("enter")
    w.handle("enter")
    v = w.view()
    off = {row["cells"][1]: why_of(row) for row in v["rows"] if carry_of(row) == "off"}
    record("30 every catalog variant on the AA page resolves; only the strangers go unmatched",
           {lane for _name, lane in resolved if lane} == lane_models
           and sorted(unmatched) == ["GPT-5.5", "Grok 4.3"]
           and "2 benchmarked models have no lane" in v["legend"],
           f"resolved={sorted(resolved, key=str)} unmatched={unmatched}")
    record("30b the AA rows switch off one dominated effort, and the reason names the source",
           off == {"astra-xhigh@codex": "high wins on aa"},
           str(off))
except Exception as e:
    record("30 every catalog variant on the AA page resolves; only the strangers go unmatched",
           False, repr(e))


try:
    w = wizard(lanes=astra_lanes(), effort_rows=TBENCH)
    w.handle("enter")
    w.handle("enter")
    # a note about the data, so it reads as a legend line and not as an error
    # in the message slot, where `every lane needs a tier` goes
    v = w.view()
    # Listing them by name ran thirty names off the line on the live page and
    # was noise; the count says what matters, and the names stay in
    # `_unmatched` for a `published_as` still owed to us.
    ignored = next((line for line in v["legend"]
                    if line.endswith("benchmarked models have no lane")), "")
    record("28d models that are nobody's lane are counted once, not warned per lane",
           ignored == f"{len(w._unmatched)} benchmarked models have no lane"
           and len(w._unmatched) >= 5 and "GLM-5.3" in w._unmatched
           and "gpt-6-astra" not in w._unmatched
           and v["message"] == ""
           and all("no lane" not in why_of(row) for row in v["rows"]),
           repr((ignored, w._unmatched)))
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
           carry_of(luna) == "off" and "wins on" in why_of(luna)
           and rows[0]["model"] == "gpt-5.6-luna", str(luna["cells"]))
except Exception as e:
    record("28e a slug-publishing source still matches, and rows are not mutated",
           False, repr(e))



try:
    w = wizard()
    start(w)
    mark_as(w, incoming_tiers(LANES))
    finish(w)
    lanes, routing = w.result()
    # the one addition is each carried lane's place inside its tier (ticket 28)
    record("26 round-trip with nothing switched off is byte-identical",
           strip_order(lanes) == LANES and routing == ROUTING and orders_are_places(lanes)
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
            # start, then r on the harnesses page (the scrub again, from the
            # fixtures), harnesses, carry, T4, T3, T2, T1, review, routing, then y
            for key in [b"\n", b"r"] + [b"\n"] * 8 + [b"y"]:
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
    for _ in range(10):
        v = w.view()
        if v["screen"] in ("routing", "confirm", "done", "quit"):
            marks.append((v["screen"], v["steps"]))
            break
        marks.append((v["screen"], v["steps"]))
        w.handle("enter")

    expected = {"start": "[start]", "discovery": "[harnesses]", "prescreen": "[carry]",
                "review": "[review]", "routing": "[routing]"}
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
from setup_tui import (ROW_FLOOR, TIER_ONELINER, _clip, _fit_table,  # noqa: E402
                       hidden_legend, layout_lines, overlay)


def screen(view, width=80, height=24):
    """The grid a terminal of this size shows, one string per row."""
    return overlay(layout_lines(view, width, height), width, height)


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
           "why" in grid[setup_tui.TOP]
           and all(reason in body for reason in reasons)
           and "high wins on tbench" in body
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
    # A lane taken above and a lane not carried are both hidden now, and the
    # one trace they leave is a count, which has to reach the screen whole.
    w = wizard(lanes=astra_lanes())
    not_carried(w, "terra-high@codex")
    move_to(w, "sol-high@codex")
    w.handle("space")
    w.handle("enter")
    seen = []
    for width in (80, 100, 140):
        grid = screen(w.view(width), width, 30)
        seen.append(not any("sol-high@codex" in line or "terra-high@codex" in line for line in grid)
                    and hidden_legend(2, 1) in grid)
    record("31 hidden lanes are off the grid, and the page counts them in a whole line",
           all(seen) and hidden_legend(2, 1) == "Not listed: 2 taken at a higher tier, 1 not carried."
           and hidden_legend(0, 0) == "", repr(seen))
except Exception as e:
    record("31 hidden lanes are off the grid, and the page counts them in a whole line", False, repr(e))


try:
    # a window too short for the list said nothing about it
    w, grid = prescreen_at(80, 16)
    shown = [line for line in grid if line.startswith("[x]") or line.startswith("[ ]")]
    w2, tall = prescreen_at(80, 40)
    record("32 a clipped list says which rows are on screen",
           grid[2].rstrip().endswith(f"1-{len(shown)} of {len(w.view()['rows'])}")
           and len(shown) >= ROW_FLOOR
           and "of" not in tall[2].split("Lanes to carry")[1],
           repr(grid[2]) + repr(tall[2]))
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
    w.handle("enter")
    assert w.screen == "routing", w.screen
    routing_view = w.view()
    w.handle("enter")
    over = []
    for view in (routing_view, w.view()):
        for line in [view["footer"], *(view.get("legend") or []),
                     *(view.get("body") or []), view["title"]]:
            if len(line) > 79:
                over.append((view["screen"], len(line), line))
    tier_map = [line for line in routing_view["legend"] if line.startswith("Lanes carried: ")]
    record("34 a crowded tier map still fits the line",
           not over and len(tier_map) == 1 and "more)" not in tier_map[0]
           and tier_map[0].count("tier ") == 4, repr(over or tier_map))
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


try:
    # The tier screen exists to read a tier off the scores. `model` and `effort`
    # are both spelled out in the lane name, so at 80 places they were 27 places
    # of restatement drawn ahead of the scores, and the scores fell off the end.
    w = wizard()
    start(w)
    view = w.view()
    chosen, _widths = _fit_table(view, 80)
    names = [view["columns"][i] for i in chosen]
    benchmarks = [n for n in view["columns"]
                  if n in (w.bench or {}).get("epoch_benchmarks", [])]
    visible = [n for n in names if n in benchmarks]
    grid = screen(view, 80, 24)
    record("37 at 80 places the tier screen shows scores, not the lane name twice",
           visible and visible == benchmarks[:len(visible)]
           and "Epoch mean rank" in names
           and "model" not in names and "effort" not in names
           and "90.0" in grid[setup_tui.TOP + 1] and "1.0 (n=5)" in grid[setup_tui.TOP + 1],
           repr(names) + "\n" + repr(grid[setup_tui.TOP:setup_tui.TOP + 2]))
except Exception as e:
    record("37 at 80 places the tier screen shows scores, not the lane name twice",
           False, repr(e))


try:
    # `[n]` and `off` are state arriving from an earlier screen, not controls.
    # Each legend line is earned by such a row being on screen: a standing line
    # explaining a case that is not there costs the rows their room.
    w = wizard()
    start(w)
    clean = w.view()["legend"]
    w2 = wizard()
    not_carried(w2, "flash-high@agy")
    off_only = w2.view()["legend"]
    move_to(w2, "sol-high@codex")
    w2.handle("space")
    w2.handle("enter")
    both = w2.view()["legend"]
    record("38 a tier legend line appears only when its state is on screen",
           # nothing off and nothing assigned: the tier definition alone
           clean == [TIER_ONELINER]
           and off_only == [hidden_legend(0, 1), TIER_ONELINER]
           and both == [hidden_legend(2, 1), TIER_ONELINER]
           # the reference line renders last, directly above the footer
           and all(lines[-1] == TIER_ONELINER for lines in (clean, off_only, both))
           and all(len(line) <= 79 for line in both),
           repr((clean, off_only, both)))
except Exception as e:
    record("38 a tier legend line appears only when its state is on screen",
           False, repr(e))


# --- ticket 25: every page at 80x24 and at a wide terminal ---------------------
def every_page(effort_rows=None, lanes=None):
    """One view per page of a whole run, as (name, wizard at that page)."""
    w = wizard(lanes=lanes, effort_rows=effort_rows, discovery=disc_unmapped)
    w.lanes_path = "/Users/someone/dotfiles/stow/delegate/.config/delegate/lanes.json"
    w.routing_path = "/Users/someone/dotfiles/stow/delegate/.config/delegate/routing.json"
    pages = []
    while w.screen not in ("confirm", "done", "quit"):
        name = f"tier{w.tier}" if w.screen == "tier" else w.screen
        pages.append((name, copy.deepcopy(w)))
        w.handle("enter")
    pages.append(("confirm", copy.deepcopy(w)))
    return pages


try:
    faults = []
    names = []
    for width, height in ((80, 24), (200, 50)):
        for name, page in every_page(effort_rows=TBENCH, lanes=astra_lanes()):
            names.append(name)
            view = page.view(width)
            entries = layout_lines(view, width, height)
            grid = overlay(entries, width, height)
            too_long = [text for _y, text, _r, _s in entries if len(text) > width - 1]
            cursor = [text for _y, text, role, _s in entries if role.startswith("row-cursor")]
            if too_long:
                faults.append((name, width, "wider than the terminal", too_long[:1]))
            if (grid[0] != view["steps"] or not grid[2].startswith(view["title"])
                    or grid[height - 3] != view["footer"][: width - 1].rstrip()):
                faults.append((name, width, "trail, title or footer out of place"))
            if view["rows"] and any(r["cursor"] for r in view["rows"]) and not cursor:
                faults.append((name, width, "cursor row off screen"))
            if view["legend"] and not all(line[: width - 1].rstrip() in grid for line in view["legend"][:1]):
                faults.append((name, width, "first legend line not whole"))
    record("40 every page lays out at 80x24 and at 200x50",
           not faults and {"start", "discovery", "prescreen", "tier4", "tier1", "review",
                           "routing", "confirm"} <= set(names), repr(faults))
except Exception as e:
    record("40 every page lays out at 80x24 and at 200x50", False, repr(e))


try:
    # the routing panel sits beside the table at both sizes, on the rows the
    # table uses, and follows the cursor
    w = wizard()
    start(w)
    to_confirm(w)
    w.handle("b")
    assert w.screen == "routing", w.screen
    checks = []
    for width, height in ((80, 24), (200, 50)):
        grid = screen(w.view(width), width, height)
        # the class heading, then its floor indented under it; the panel's
        # head shares the header row
        group = next(line for line in grid if line.startswith("scout "))
        head = grid.index(group) - 1
        checks.append("│ scout floor: 2" in grid[head] and grid[head + 2].startswith("  floor"))
        checks.append(any("lowest tier" in line and "│" in line for line in grid))
        checks.append(all(len(line) <= width - 1 for line in grid))
    for _ in range(11):
        w.handle("down")
    gate = screen(w.view(80), 80, 24)
    # the panel follows the cursor down to gate, and the gate row stays on screen
    checks.append(any("│ gate: 0.1" in line for line in gate)
                  and any(line.startswith("  gate") for line in gate)
                  and not any("│ scout floor" in line for line in gate))
    wide = screen(w.view(200), 200, 50)
    panel_width = max(len(line.split("│ ", 1)[1]) for line in wide if "│ " in line)
    checks.append(panel_width <= setup_tui.PANEL_MAX)
    record("41 the routing page describes the highlighted setting beside the table",
           all(checks), repr(checks) + "\n" + "\n".join(gate))
except Exception as e:
    record("41 the routing page describes the highlighted setting beside the table", False, repr(e))


# --- ticket 26: lanes are grouped by model, efforts most to least, on every page ----
def sweep_lanes():
    """fable at five efforts, sol at two, flash on agy as a slug family of
    two, and an ultra sol that is never carried."""
    doc = copy.deepcopy(LANES)
    for effort in ("low", "medium", "high", "max"):
        lane = copy.deepcopy(LANES["lanes"]["fable-xhigh@claude"])
        lane["effort"] = effort
        doc["lanes"][f"fable-{effort}@claude"] = lane
    low = copy.deepcopy(LANES["lanes"]["sol-high@codex"])
    low["effort"] = "low"
    doc["lanes"]["sol-low@codex"] = low
    ultra = copy.deepcopy(LANES["lanes"]["sol-high@codex"])
    ultra["effort"] = "ultra"
    doc["lanes"]["sol-ultra@codex"] = ultra
    flash_low = copy.deepcopy(LANES["lanes"]["flash-high@agy"])
    flash_low["model"] = "gemini-3.8-flash-low"
    flash_low["effort"] = "low"
    doc["lanes"]["flash-low@agy"] = flash_low
    return doc


def groups_of(names, doc):
    """The model groups in the order they appear, each with its efforts."""
    out = []
    for name in names:
        group = setup_tui.model_group(doc["lanes"][name])
        if not out or out[-1][0] != group:
            out.append((group, []))
        out[-1][1].append(doc["lanes"][name]["effort"])
    return out


try:
    record("policy helpers on setup_tui are aliases of bench",
           setup_tui.propose_enabled is bench.propose_enabled
           and setup_tui.group_lanes is bench.group_lanes
           and setup_tui.lane_order is bench.lane_order
           and setup_tui.dominating_effort is bench.dominating_effort
           and setup_tui.model_group is bench.model_group)
except Exception as e:
    record("policy helpers on setup_tui are aliases of bench", False, repr(e))


try:
    doc = sweep_lanes()
    names = ["fable-low@claude", "sol-high@codex", "fable-max@claude", "flash-high@agy",
             "flash-low@agy", "sol-low@codex"]
    grouped = setup_tui.group_lanes(names, doc)
    record("43 group_lanes places a group where its first lane sat and runs its efforts most to least",
           grouped == ["fable-max@claude", "fable-low@claude", "sol-high@codex", "sol-low@codex",
                       "flash-high@agy", "flash-low@agy"]
           # an agy slug family is one model
           and setup_tui.model_group(doc["lanes"]["flash-low@agy"]) == setup_tui.model_group(doc["lanes"]["flash-high@agy"])
           and setup_tui.model_group(doc["lanes"]["sol-low@codex"]) != setup_tui.model_group(doc["lanes"]["luna-low@codex"])
           and [setup_tui.effort_rank(e) for e in ("ultra", "max", "xhigh", "high", "medium", "low")]
           == sorted(setup_tui.effort_rank(e) for e in ("ultra", "max", "xhigh", "high", "medium", "low")),
           repr(grouped))
except Exception as e:
    record("43 group_lanes places a group where its first lane sat and runs its efforts most to least",
           False, repr(e))


try:
    doc = sweep_lanes()
    w = wizard(lanes=doc)
    w.handle("enter")
    w.handle("enter")
    carry = [r["cells"][1] for r in w.view()["rows"]]
    carry_groups = groups_of(carry, doc)
    w.handle("enter")
    t4 = [r["cells"][1] for r in w.view()["rows"]]
    t4_groups = groups_of(t4, doc)
    # sol-high leads the benchmark order and fable's measured lane is fable-max,
    # so the sol group comes first and every group is whole, most effort first
    sol, flash, fable = (setup_tui.model_group(doc["lanes"][n])
                         for n in ("sol-high@codex", "flash-high@agy", "fable-max@claude"))
    record("44 the carry page and the tier pages group by model, efforts most to least",
           carry[:3] == ["fable-max@claude", "fable-xhigh@claude", "fable-high@claude"]
           and len({g for g, _ in carry_groups}) == len(carry_groups)
           and dict(carry_groups)[sol] == ["ultra", "high", "low"]
           and dict(carry_groups)[flash] == ["high", "low"]
           and t4[:2] == ["sol-high@codex", "sol-low@codex"]
           and len({g for g, _ in t4_groups}) == len(t4_groups)
           and dict(t4_groups)[fable] == ["max", "xhigh", "high", "medium", "low"]
           and "sol-ultra@codex" not in t4
           and all(eff == sorted(eff, key=setup_tui.effort_rank) for _g, eff in t4_groups),
           repr((carry, t4)))
    # the review page is by tier and in Orin's order, so the model grouping
    # does not apply there (ticket 28): with no lines and no catalog order a
    # tier starts in benchmark order
    move_to(w, "fable-low@claude")
    w.handle("space")            # remove its current tier-4 default
    move_to(w, "sol-high@codex")
    w.handle("space")
    w.handle("enter")            # sol-high takes tier 4
    move_to(w, "fable-low@claude")
    w.handle("space")
    w.handle("enter")            # fable-low takes tier 3
    w.handle("enter")
    w.handle("enter")            # the rest take tier 1
    review = dict(review_layout(w.view()))
    tier1 = review[1]
    record("44b the review page lists tiers 4 to 1, each starting in benchmark order without model grouping",
           w.screen == "review"
           and "sol-high@codex" in review[4] and "fable-low@claude" in review[3]
           and review[2] == sorted(review[2], key=lambda n: setup_tui.bench_order_key(w.bench, n, doc))
           and tier1 == sorted(tier1, key=lambda n: setup_tui.bench_order_key(w.bench, n, doc)),
           repr(review))
except Exception as e:
    record("44 the carry page and the tier pages group by model, efforts most to least", False, repr(e))


try:
    # bench_order_key and lane_order are what the benchmark page lists lanes
    # by, so they must agree with the tier page
    doc = sweep_lanes()
    w = wizard(lanes=doc)
    start(w)
    t4 = [r["cells"][1] for r in w.view()["rows"]]
    listed = [n for n in setup_tui.lane_order(doc, w.bench) if w._enabled[n]]
    record("45 lane_order is the tier page's order over the whole catalog",
           listed == t4 and setup_tui.bench_order_key(None, "x") == (True, 0, "x")
           # with no benchmark, the order is by name, still grouped
           and setup_tui.lane_order(doc, None)[:3] == ["fable-max@claude", "fable-xhigh@claude", "fable-high@claude"],
           repr((listed, t4)))
except Exception as e:
    record("45 lane_order is the tier page's order over the whole catalog", False, repr(e))


try:
    # a wide terminal shows what 80 places cut: the whole path on the start page
    w = wizard()
    w.lanes_path = "/Users/someone/" + "deep/" * 18 + "lanes.json"
    narrow = "\n".join(w.view(80)["body"])
    wide = "\n".join(w.view(200)["body"])
    record("42 prose is fitted to the terminal's width, not to 80",
           w.lanes_path not in narrow and "..." in narrow
           and f"Will write {w.lanes_path}" in wide,
           narrow + "\n" + wide)
except Exception as e:
    record("42 prose is fitted to the terminal's width, not to 80", False, repr(e))


try:
    doc = {"lanes": {name: {"model": model, "effort": effort}
           for name, model, effort in [("a-high", "a", "high"), ("a-low", "a", "low"),
                                        ("b-high", "b", "high"), ("c-high", "c", "high"),
                                        ("d-high", "d", "high")]}}
    ranks = {"lanes": {"a-high": {"mean": None, "aa": {"mean": 6}},
                        "a-low": {"mean": None, "aa": {"mean": 2}},
                        "b-high": {"mean": 3}, "c-high": {"mean": None, "aa": {"mean": 4}},
                        "d-high": {"mean": None, "aa": None}}}
    fallback = setup_tui.lane_order(doc, ranks)
    ranks["lanes"]["a-high"]["mean"] = 5
    ranks["lanes"]["a-low"]["aa"]["mean"] = 1
    record("46 groups without Epoch use their best AA rank and keep efforts descending",
           fallback == ["a-high", "a-low", "b-high", "c-high", "d-high"]
           and setup_tui.lane_order(doc, ranks) == ["b-high", "c-high", "a-high", "a-low", "d-high"])
except Exception as e:
    record("46 groups without Epoch use their best AA rank and keep efforts descending", False, repr(e))


# --- ticket 27: the page's lines, pasted into the review page ---------------------------
try:
    doc = sweep_lanes()
    text = ("\n"
            "sol-high@codex 4\n"
            "   \n"
            "terra-high@codex 2\n"
            "nobody@codex 3\n"
            "luna-low@codex 5\n"          # a tier out of range
            "flash-high@agy\n"            # no tier
            "grok46-high@grok 1 2\n"      # a field too many
            "fable-low@claude x\n"        # not a tier
            "terra-high@codex OFF\n"      # named again: the last line wins
            "sol-ultra@codex 3\n"         # an ultra lane is never carried
            "nobody@codex off\n"
            "fable-max@claude 1\n")
    parsed = setup_tui.parse_tier_lines(text, doc)
    carried = ["sol-high@codex", "luna-low@codex", "terra-high@codex", "grok46-high@grok", "flash-low@agy"]
    dropped = setup_tui.unnamed_carried(parsed, carried)
    summary = setup_tui.tier_lines_summary(parsed, dropped)
    nothing = setup_tui.parse_tier_lines("nobody@codex 2\nnot a line\n", doc)
    record("47 one parser reads tier lines: blank lines skipped, the last line for a lane wins, unknown "
           "lanes, bad tiers and ultra lanes ignored, and one summary line says each",
           parsed["decided"] == {"sol-high@codex": 4, "terra-high@codex": "off", "fable-max@claude": 1}
           and list(parsed["decided"]) == ["sol-high@codex", "terra-high@codex", "fable-max@claude"]
           and parsed["repeated"] == ["terra-high@codex"]
           and parsed["unknown"] == ["nobody@codex"]
           and parsed["bad"] == [6, 7, 8, 9]
           and parsed["refused"] == ["sol-ultra@codex"]
           # a carried lane no line names goes off, and the summary counts it (ticket 28)
           and dropped == ["luna-low@codex", "grok46-high@grok", "flash-low@agy"]
           and summary == ("Lines: 2 took a tier; 1 went off; 3 not named, so off; "
                           "named twice, last line kept: terra-high@codex; unknown, ignored: nobody@codex; "
                           "ultra, never carried, ignored: sol-ultra@codex; "
                           "not <lane> <1-4|off>, ignored: line 6, 7, 8, 9.")
           and setup_tui.parse_tier_lines("", doc)["decided"] == {}
           # lines that name no lane decide nothing, so nothing goes off
           and setup_tui.unnamed_carried(nothing, carried) == []
           and setup_tui.tier_lines_summary(nothing, []) == (
               "Lines: no line names a lane in this catalog, so nothing changed; "
               "unknown, ignored: nobody@codex; not <lane> <1-4|off>, ignored: line 2."),
           repr((parsed, dropped, summary)))
except Exception as e:
    record("47 one parser reads tier lines", False, repr(e))


def at_review(clipboard, lanes=None):
    w = Wizard(copy.deepcopy(lanes or LANES), copy.deepcopy(ROUTING), data(), DISCOVERED,
               "/tmp/lanes.json", "/tmp/routing.json", clipboard=clipboard)
    start(w)
    while w.screen == "tier":
        w.handle("enter")
    assert w.screen == "review", w.screen
    return w


try:
    calls = []

    def clipboard():
        calls.append(1)
        return "fable-xhigh@claude 4\nsol-high@codex off\nterra-high@codex 3\nnobody@x 2\n"

    w = at_review(clipboard)
    # the cursor on terra-high, which a line names and moves to tier 3
    w.cursor = review_names(w.view()).index("terra-high@codex")
    for key in ("up", "down", "o", "x", "space"):
        w.handle(key)
    before = len(calls)
    w.handle("v")
    view = w.view(200)
    layout = dict(review_layout(view))
    cursor = next(r["cells"][1] for r in view["rows"] if r["cursor"])
    grid = overlay(layout_lines(view, 200, 50), 200, 50)
    finish(w)
    lanes, _routing = w.result()
    record("48 v on the review page applies the clipboard's lines: a tier line carries and tiers, off sets "
           "not carried, a carried lane with no line goes off, and one line says so",
           before == 0 and len(calls) == 1
           and layout == {4: ["fable-xhigh@claude"], 3: ["terra-high@codex"], 2: [], 1: []}
           and cursor == "terra-high@codex"
           and view["message"] == "Lines: 2 took a tier; 1 went off; 3 not named, so off; unknown, ignored: nobody@x."
           and view["message"] in grid
           and "4 lanes not carried keep their catalog tier." in grid
           and "v: paste" in view["footer"]
           and lanes["lanes"]["fable-xhigh@claude"]["tier"] == 4 and "enabled" not in lanes["lanes"]["fable-xhigh@claude"]
           and lanes["lanes"]["fable-xhigh@claude"]["order"] == 1
           and lanes["lanes"]["terra-high@codex"]["tier"] == 3 and lanes["lanes"]["terra-high@codex"]["order"] == 1
           and lanes["lanes"]["sol-high@codex"]["enabled"] is False
           and lanes["lanes"]["sol-high@codex"]["tier"] == LANES["lanes"]["sol-high@codex"]["tier"]
           and lanes["lanes"]["luna-low@codex"]["enabled"] is False
           and lanes["lanes"]["luna-low@codex"]["tier"] == LANES["lanes"]["luna-low@codex"]["tier"]
           and orders_are_places(lanes),
           repr((calls, layout, cursor, view["message"])))
except Exception as e:
    record("48 v on the review page applies the clipboard's lines", False, repr(e))


try:
    current_lines = "\n".join(
        f"{name} {lane['tier'] if lane.get('enabled', True) else 'off'}"
        for name, lane in LANES["lanes"].items()
    ) + "\n"
    first = at_review(lambda: current_lines)
    first.handle("v")
    finish(first)
    pasted, _routing = first.result()

    second = wizard(lanes=pasted)
    start(second)
    restored = []
    while second.screen == "tier":
        expected = {
            name for name, lane in pasted["lanes"].items()
            if lane.get("enabled", True) and lane["tier"] == second.tier
        }
        marked = {row["cells"][1] for row in second.view()["rows"] if row["marked"]}
        restored.append(marked == expected)
        second.handle("enter")
    finish(second)
    record("48b a catalog first created with v restores its tiers and order on the next run",
           restored == [True, True, True, True]
           and second.result()[0] == pasted,
           repr((restored, second.result()[0])))
except Exception as e:
    record("48b a catalog first created with v restores its tiers and order on the next run",
           False, repr(e))


try:
    def missing():
        raise setup_tui.ClipboardError("pbpaste not found")

    outcomes = []
    for reader, said in ((missing, "v: pbpaste not found; nothing changed"),
                         (lambda: "  \n\n", "v: the clipboard holds no lines; nothing changed")):
        w = at_review(reader)
        state = (dict(w._assigned), dict(w._enabled), list(w._review_order))
        w.handle("v")
        outcomes.append(w.message == said and state == (dict(w._assigned), dict(w._enabled), list(w._review_order)))
    # the real reader with no pbpaste on PATH raises, never runs anything else
    saved_path = os.environ.get("PATH", "")
    with tempfile.TemporaryDirectory() as empty:
        os.environ["PATH"] = empty
        try:
            setup_tui.read_clipboard()
            outcomes.append(False)
        except setup_tui.ClipboardError as e:
            outcomes.append("pbpaste" in str(e))
        finally:
            os.environ["PATH"] = saved_path
    # pbpaste that fails says its exit status
    with tempfile.TemporaryDirectory() as fake:
        script = os.path.join(fake, "pbpaste")
        with open(script, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\nexit 3\n")
        os.chmod(script, 0o755)
        os.environ["PATH"] = fake + os.pathsep + saved_path
        try:
            setup_tui.read_clipboard()
            outcomes.append(False)
        except setup_tui.ClipboardError as e:
            outcomes.append("exit 3" in str(e))
        finally:
            os.environ["PATH"] = saved_path
    record("49 where pbpaste is missing, fails or the clipboard is empty, v says so and changes nothing",
           outcomes == [True, True, True, True], repr(outcomes))
except Exception as e:
    record("49 where pbpaste is missing, fails or the clipboard is empty, v says so and changes nothing", False, repr(e))


try:
    # --tiers-from applies the lines at start as editable defaults.
    w = wizard()
    summary = w.apply_tier_lines("fable-xhigh@claude 4\nsol-high@codex off\n")
    start_message = w.view()["message"]
    start(w)
    t4 = [r["cells"][1] for r in w.view()["rows"]]
    t4_marked = [r["cells"][1] for r in w.view()["rows"] if r["marked"]]
    legend = w.view()["legend"]
    while w.screen == "tier":
        w.handle("enter")
    record("50 lines applied at start become editable tier defaults and say so on the start page",
           start_message == summary == "Lines: 1 took a tier; 1 went off; 4 not named, so off."
           and t4 == ["fable-xhigh@claude"] and t4_marked == t4
           and legend[0] == "Not listed: 5 not carried."
           and w.screen == "review" and review_layout(w.view())[0] == (4, ["fable-xhigh@claude"]),
           repr((start_message, t4, legend)))
except Exception as e:
    record("50 lines applied at start become editable tier defaults", False, repr(e))


# --- ticket 28: an order inside each tier -------------------------------------------
def through_lines(text, lanes=None):
    """A wizard with `text` applied at start, walked to the review page."""
    w = wizard(lanes=lanes)
    w.apply_tier_lines(text)
    start(w)
    while w.screen == "tier":
        w.handle("enter")
    assert w.screen == "review", w.screen
    return w


try:
    w = through_lines("terra-high@codex 2\nsol-high@codex 2\nluna-low@codex 1\ngrok46-high@grok 2\n")
    record("51 the lines' order inside a tier is the review page's starting order",
           review_layout(w.view()) == [(4, []), (3, []),
                                       (2, ["terra-high@codex", "sol-high@codex", "grok46-high@grok"]),
                                       (1, ["luna-low@codex"])]
           and not w._enabled["fable-xhigh@claude"] and not w._enabled["flash-high@agy"],
           repr(review_layout(w.view())))
except Exception as e:
    record("51 the lines' order inside a tier is the review page's starting order", False, repr(e))


try:
    w = through_lines("terra-high@codex 2\nsol-high@codex 2\nluna-low@codex 1\ngrok46-high@grok 2\n")
    steps = []

    def tier(n):
        return dict(review_layout(w.view()))[n]

    def at():
        return next(r["cells"][1] for r in w.view()["rows"] if r["cursor"])

    w.handle("lane-down")                 # J: terra below sol, the cursor with it
    steps.append((tier(2), at()) == (["sol-high@codex", "terra-high@codex", "grok46-high@grok"], "terra-high@codex"))
    w.handle("lane-down")
    w.handle("lane-down")                 # at the bottom of tier 2: never into tier 1
    steps.append((tier(2), tier(1), at()) == (["sol-high@codex", "grok46-high@grok", "terra-high@codex"],
                                               ["luna-low@codex"], "terra-high@codex"))
    for _ in range(3):
        w.handle("lane-up")               # K, and once more at the top of the tier
    steps.append(tier(2) == ["terra-high@codex", "sol-high@codex", "grok46-high@grok"])
    w.handle("down")                      # j moves the cursor only
    steps.append((at(), tier(2)[1]) == ("sol-high@codex", "sol-high@codex"))
    w.handle("4")                         # 1-4: to that tier's end
    steps.append((tier(4), tier(2), at()) == (["sol-high@codex"], ["terra-high@codex", "grok46-high@grok"],
                                               "sol-high@codex"))
    w.handle("2")
    steps.append((tier(4), tier(2), at()) == ([], ["terra-high@codex", "grok46-high@grok", "sol-high@codex"],
                                               "sol-high@codex"))
    w.handle("2")                         # its own tier: to the end, where it already is
    steps.append(tier(2)[-1] == "sol-high@codex")
    before = review_layout(w.view())
    w.handle("enter")
    w.handle("b")                         # routing and back keep every move
    steps.append(w.screen == "review" and review_layout(w.view()) == before)
    w.handle("enter")
    w.handle("enter")
    w.handle("y")
    lanes, _routing = w.result()
    written = {name: (lane["tier"], lane.get("order"), lane.get("enabled", True))
               for name, lane in lanes["lanes"].items()}
    catalog.validate_lanes(lanes)
    record("52 J/K move a lane inside its tier and never across, 1-4 move it to that tier's end, "
           "and enter writes each carried lane's place as order",
           steps == [True] * 8
           and written["terra-high@codex"] == (2, 1, True)
           and written["grok46-high@grok"] == (2, 2, True)
           and written["sol-high@codex"] == (2, 3, True)
           and written["luna-low@codex"] == (1, 1, True)
           and written["fable-xhigh@claude"][1:] == (None, False)
           and written["flash-high@agy"][1:] == (None, False),
           repr((steps, written)))
except Exception as e:
    record("52 J/K move a lane inside its tier and never across", False, repr(e))


try:
    # with no lines, an order the catalog already gives a lane at its tier is the
    # starting order; a lane without one follows in benchmark order
    doc = all_tier_one(LANES)
    doc["lanes"]["luna-low@codex"]["order"] = 1
    doc["lanes"]["grok46-high@grok"]["order"] = 2
    doc["lanes"]["sol-high@codex"]["order"] = 7   # a gap in the catalog closes up when written
    w = wizard(lanes=doc)
    start(w)
    while w.screen == "tier":
        w.handle("enter")
    tier1 = dict(review_layout(w.view()))[1]
    rest = tier1[3:]
    finish(w)
    lanes, _routing = w.result()
    record("53 with no lines a catalog's order starts the review page, the rest in benchmark order",
           tier1[:3] == ["luna-low@codex", "grok46-high@grok", "sol-high@codex"]
           and rest == sorted(rest, key=lambda n: setup_tui.bench_order_key(w.bench, n, doc))
           and lanes["lanes"]["sol-high@codex"]["order"] == 3 and orders_are_places(lanes),
           repr(tier1))
except Exception as e:
    record("53 with no lines a catalog's order starts the review page", False, repr(e))


try:
    w = through_lines("terra-high@codex 2\nsol-high@codex 2\nluna-low@codex 1\ngrok46-high@grok 2\n")
    w.handle("lane-down")
    faults = []
    for width, height in ((80, 24), (200, 50)):
        view = w.view(width)
        entries = layout_lines(view, width, height)
        grid = overlay(entries, width, height)
        sections = [text for _y, text, role, _s in entries if role == "section"]
        cursor = [text for _y, text, role, _s in entries if role == "row-cursor"]
        if sections != ["Tier 4 (no lanes)", "Tier 3 (no lanes)", "Tier 2 (3 lanes)", "Tier 1 (1 lane)"]:
            faults.append((width, "sections", sections))
        if not (len(cursor) == 1 and cursor[0].startswith(" 2  terra-high@codex")):
            faults.append((width, "cursor", cursor))
        if any(len(line) > width - 1 for line in grid):
            faults.append((width, "too wide"))
        if not any(line.startswith(" 1  sol-high@codex") for line in grid):
            faults.append((width, "numbering"))
        keys_spelled = [line for line in grid
                        if line.startswith(("J/K, shift-↑/↓", "1-4"))
                        and ("inside its tier" in line or "end of that tier" in line)]
        if len(keys_spelled) != 2 or setup_tui.REVIEW_ORDER_LEGEND not in grid:
            faults.append((width, "legend", keys_spelled))
    record("54 the review page renders a section per tier, numbered, with the moved lane under the cursor",
           not faults and grid[2].startswith("Order each tier"), repr(faults))
except Exception as e:
    record("54 the review page renders a section per tier", False, repr(e))

try:
    model = LANES["lanes"]["sol-high@codex"]["model"]
    lanes = copy.deepcopy(LANES)
    extra = copy.deepcopy(lanes["lanes"]["sol-high@codex"])
    extra["effort"] = "low"
    extra["tier"] = 2
    extra.pop("enabled", None)
    lanes["lanes"]["sol-low@codex"] = extra
    rows = [
        {"source": "t", "model": model, "effort": "high", "benchmark": "b",
         "score": 9.0, "cost_usd": 1.0, "uncertain": False, "composite": False},
        {"source": "t", "model": model, "effort": "low", "benchmark": "b",
         "score": 1.0, "cost_usd": 1.0, "uncertain": False, "composite": False},
    ]
    full = wizard(lanes=lanes, effort_rows=rows)
    focused = wizard(lanes=lanes, effort_rows=rows, focus="carry")
    record(
        "55 focused carry starts from catalog decisions and does not apply unseen proposals",
        focused.screen == "prescreen"
        and focused._enabled["sol-low@codex"] is True
        and full._enabled["sol-low@codex"] is False
        and focused._enabled["sol-high@codex"] is True,
        repr((full._enabled.get("sol-low@codex"), focused._enabled.get("sol-low@codex"))),
    )
    focused.handle("enter")
    record("55b focused carry enter reviews chosen edits on confirm",
           focused.screen == "confirm", focused.screen)
    focused.handle("y")
    written, routing = focused.result()
    record(
        "55c focused enter without edits preserves carry and does not write meters",
        written["lanes"]["sol-low@codex"].get("enabled", True) is True
        and written["lanes"]["sol-high@codex"]["tier"] == LANES["lanes"]["sol-high@codex"]["tier"]
        and "meters" not in routing
        and routing["gate"] == ROUTING["gate"]
        and routing["margin"] == ROUTING["margin"],
        repr(written["lanes"]["sol-low@codex"]),
    )
except Exception as e:
    record("55 focused carry starts from catalog decisions", False, repr(e))

try:
    w = wizard(focus="tier3")
    record("56 focused tier3 opens that page on current assignments",
           w.screen == "tier" and w.tier == 3, (w.screen, w.tier))
    before = dict(w._assigned)
    w.handle("enter")
    record("56b focused tier enter goes to confirm", w.screen == "confirm", w.screen)
    w.handle("y")
    lanes, _routing = w.result()
    record(
        "56c focused untouched tier choices keep catalog tiers",
        all(lanes["lanes"][name]["tier"] == LANES["lanes"][name]["tier"]
            for name in LANES["lanes"]),
        repr({n: lanes["lanes"][n]["tier"] for n in LANES["lanes"]}),
    )
    _ = before
except Exception as e:
    record("56 focused tier3 opens that page on current assignments", False, repr(e))

try:
    w = wizard(focus="routing")
    record("57 focused routing starts on the routing screen",
           w.screen == "routing", w.screen)
    for _ in range(len(catalog.CLASSES) * 2 + 2):
        w.handle("down")
    w.handle("space")
    record("57b space/x flips meters with the established marker",
           not w._meters_on() and w.routing_doc.get("meters") is False, w.routing_doc.get("meters"))
    w.handle("enter")
    w.handle("y")
    _lanes, routing = w.result()
    record("57c focused routing writes meters false and keeps Gate/Margin",
           routing.get("meters") is False
           and routing["gate"] == ROUTING["gate"]
           and routing["margin"] == ROUTING["margin"],
           repr(routing.get("meters")),
    )
except Exception as e:
    record("57 focused routing starts on the routing screen", False, repr(e))

try:
    w = wizard(focus="review")
    w.handle("enter")
    record("58 focused review skips routing and confirms chosen edits",
           w.screen == "confirm", w.screen)
    w.handle("b")
    record("58b confirm back returns to the focused review screen",
           w.screen == "review", w.screen)
except Exception as e:
    record("58 focused review skips routing", False, repr(e))

for focus in ("carry", "tier1", "tier2", "tier3", "tier4", "review", "routing"):
    try:
        source = copy.deepcopy(LANES)
        first = next(iter(source["lanes"]))
        source["lanes"][first]["enabled"] = True
        w = wizard(lanes=source, focus=focus)
        w.handle("enter")
        record(f"59 {focus} no-op confirmation says nothing will be written",
               any("Nothing will be written" in str(row["cells"]) for row in w.view()["rows"]))
        w.handle("y")
        record(f"59 {focus} no-op preserves all Lane fields and routing",
               w.result() == (source, ROUTING), w.result())
    except Exception as e:
        record(f"59 {focus} focused no-op", False, repr(e))
try:
    w = wizard(focus="routing")
    w.cursor = len(catalog.CLASSES) * 2 + 2
    w.handle("space")
    w.handle("enter")
    preview = w.view()
    w.handle("y")
    record("60 routing-only focused save leaves every Lane field unchanged",
           w.result()[0] == LANES and all(row["cells"][0] in ("meters", "file", "target")
                                        for row in preview["rows"]), preview)
    w = wizard(focus="tier3")
    name = next(n for n, lane in LANES["lanes"].items()
                if lane["tier"] == 3 and lane.get("enabled", True))
    move_to(w, name)
    w.handle("space")
    w.handle("enter")
    w.handle("y")
    result = w.result()[0]
    record("61 focused Tier unmark demotes one Tier and appends at its end",
           result["lanes"][name]["tier"] == 2
           and catalog._carried_in_tier(result["lanes"], 2)[-1] == name, result)
    record("61 untouched Tiers keep their original records",
           all(result["lanes"][n] == lane for n, lane in LANES["lanes"].items()
               if lane["tier"] not in (2, 3)))
except Exception as e:
    record("focused edit preservation regressions", False, repr(e))


try:
    # Ticket 29 A: the review page names a Tier whose carried Lanes all drain
    # one Meter. It is coverage, not a judgment of the Tier, and it reads the
    # carry and Tier this session holds, not the ones the catalog came with.
    w = wizard()
    not_carried(w, "grok46-high@grok")
    mark_as(w, {"fable-xhigh@claude": 4, "sol-high@codex": 3,
                "terra-high@codex": 2, "luna-low@codex": 1, "flash-high@agy": 1})
    warnings = w.view()["warnings"]
    record("62 the review page names a Tier one Meter serves, and only such a Tier",
           w.screen == "review"
           and any(line.startswith("Tier 2 depends on Meter codex") for line in warnings)
           and not any(line.startswith("Tier 1 depends") for line in warnings)
           and not any("depends on Meter" in line for line in w.view()["legend"])
           and all(len(line) <= 79 for line in warnings),
           repr(warnings))
except Exception as e:
    record("62 the review page names a Tier one Meter serves", False, repr(e))


try:
    # Ticket 33: the start page states the refresh, one line per model, and
    # where the benchmark rows came from.
    REFRESH_DIR = os.path.join(FIXTURES, "refresh-2026-09-22")
    frozen = catalog.load_json(os.path.join(REFRESH_DIR, "lanes.json"))
    rows = catalog.load_json(os.path.join(REFRESH_DIR, "aa-accepted.json"))
    found = discover.discover(frozen, fixture_dir=REFRESH_DIR)
    refreshed, plan = discover.refresh_catalog(
        frozen, found,
        published_models=sorted({r["model"] for r in rows if r.get("source") == "aa"}),
    )
    lines = setup_tui.refresh_lines(plan, 10_000)
    record("63 the refresh reads one line per model, old to new",
           lines[0] == "gpt-5.6-sol → gpt-6-sol: sol6-*@codex replace sol-*@codex (6 Lanes)"
           and "new gemini-3.1-pro: pro31-*@agy (2 Lanes)" in lines
           and "grok-4.6 → grok-4.7: grok47-*@grok replace grok46-*@grok (1 Lane)" in lines,
           repr(lines))

    record("63b a refresh that did not run states no change of its own",
           setup_tui.refresh_lines(None, 80) == []
           and setup_tui.refresh_lines({"models": [], "new": [], "removed": []}, 80)
           == ["Catalog refresh: every model is the current generation"],
           repr(setup_tui.refresh_lines({"models": [], "new": [], "removed": []}, 80)))

    w = Wizard(copy.deepcopy(refreshed), copy.deepcopy(ROUTING), None, DISCOVERED,
               "/tmp/lanes.json", "/tmp/routing.json", "",
               discovery=discover.map_lanes(found, refreshed), refresh=plan,
               rows_note="Benchmark rows: Artificial Analysis fetched just now")
    body = w.view(10_000)["body"]
    record("63c the start page carries the change lines and the rows note",
           w.screen == "start"
           and "Benchmark rows: Artificial Analysis fetched just now" in body
           and all(line in body for line in lines),
           repr(body))
except Exception as e:
    record("63 the start page states the refresh", False, repr(e))


try:
    # Ticket 35: `o` writes the page again from the catalog as the session holds
    # it, so a lane carried on the carry page reaches the page, and the page's
    # catalog key does not move, so tiers drawn in the browser survive.
    import bench_page
    with tempfile.TemporaryDirectory() as td:
        page_path = os.path.join(td, "bench.html")
        # the page embeds its data, and its catalog key, only with rows to plot
        page_rows = [
            {"model": "grok-4.6", "effort": "high", "score": 5.0, "cost_usd": 2.0,
             "uncertain": False, "source": "t", "benchmark": "b"},
            {"model": "gpt-5.6-sol", "effort": "high", "score": 9.0, "cost_usd": 4.0,
             "uncertain": False, "source": "t", "benchmark": "b"},
        ]
        doc = copy.deepcopy(LANES)
        doc["lanes"]["grok46-high@grok"]["enabled"] = False
        bench_page.write(page_path, None, doc, page_rows)
        first = open(page_path, encoding="utf-8").read()
        w = Wizard(doc, copy.deepcopy(ROUTING), None, DISCOVERED,
                   "/tmp/lanes.json", "/tmp/routing.json", "",
                   bench_page_path=page_path, effort_rows=page_rows)
        key_before = bench_page.catalog_key(w.current_lanes())
        carried_before = [l["name"] for l in bench_page.plot_data(page_rows, w.current_lanes())["lanes"]
                          if l["carried"]]
        # carry it here, as the carry page's space does
        w._enter_prescreen()
        w._toggle_enabled("grok46-high@grok")
        message = w.rewrite_bench_page()
        after = open(page_path, encoding="utf-8").read()
        key_after = bench_page.catalog_key(w.current_lanes())
        carried_after = [l["name"] for l in bench_page.plot_data(page_rows, w.current_lanes())["lanes"]
                         if l["carried"]]
        record("64 o writes the page again from this session's carry decisions",
               message == ""
               and "grok46-high@grok" not in carried_before
               and "grok46-high@grok" in carried_after
               and first != after,
               repr((message, carried_before, carried_after)))
        record("64b the page's catalog key does not move, so tiers drawn in the browser survive",
               key_before == key_after == bench_page.catalog_key(LANES)
               and f'"catalogKey":"{key_after}"' in after and key_after in first,
               repr((key_before, key_after)))
        record("64c a tier taken on a tier page reaches the page the same way",
               w.current_lanes()["lanes"]["grok46-high@grok"]["tier"]
               == LANES["lanes"]["grok46-high@grok"]["tier"]
               and w.current_lanes() is not w.lanes_doc,
               repr(w.current_lanes()["lanes"]["grok46-high@grok"]))
        # a page that cannot be written is a message, never a stop
        w.bench_page_path = os.path.join(td, "no-such-directory", "bench.html")
        record("64d a page that cannot be written says so and changes nothing else",
               w.rewrite_bench_page().startswith("benchmark page:"),
               repr(w.rewrite_bench_page()))
except Exception as e:
    record("64 o writes the page again from this session's carry decisions", False, repr(e))


# --- the trail on top, the bottom in zones, and the styles that carry meaning ---
# The bottom of a page ran the legend, the trail and the keys together with
# nothing between them, and the trail is where you are in the run, which is
# read first, not last. Every fault below is read off the grid and the spans.
try:
    faults = []
    for name, page in every_page(effort_rows=TBENCH, lanes=astra_lanes()):
        view = page.view(80)
        entries = layout_lines(view, 80, 24)
        grid = overlay(entries, 80, 24)
        y, text, _role, spans = next(e for e in entries if e[2] == "steps")
        labels = view["steps"].split(" · ")
        current = next(i for i, label in enumerate(labels) if label.startswith("["))
        here = [text[s:e] for s, e, style in spans if style == "step-here"]
        done = [text[s:e] for s, e, style in spans if style == "step-done"]
        if ((y, grid[0], grid[1], grid[3]) != (0, view["steps"], "", "")
                or not grid[2].startswith(view["title"])):
            faults.append((name, "rows", grid[:4]))
        if here != [labels[current]] or done != labels[:current]:
            faults.append((name, "spans", here, done))
    record("65 the trail is the top row of every page: the step this page is stands out, "
           "the steps behind it are done, and a blank row parts it from the title",
           not faults, repr(faults))
except Exception as e:
    record("65 the trail is the top row of every page", False, repr(e))


try:
    # the bottom is three zones: the rows, a blank row, the legend, a blank row,
    # the keys. The counter says what the rows' budget leaves on screen, and a
    # long list still scrolls the cursor into view.
    faults = []
    for width, height in ((80, 24), (80, 20)):
        w, grid = prescreen_at(width, height)
        view = w.view(width)
        zone = setup_tui._legend_zone(view)
        shown = [line for line in grid if line.startswith("[x]") or line.startswith("[ ]")]
        budget = height - 3 - 1 - len(zone) - 1 - (setup_tui.TOP + 1)
        first_legend = grid.index(zone[0][0])
        if len(shown) != min(budget, len(view["rows"])):
            faults.append((width, height, "budget", len(shown), budget))
        if (grid[first_legend - 1] != "" or grid[first_legend + len(zone)] != ""
                or grid[height - 3] != view["footer"]):
            faults.append((width, height, "zones", grid[first_legend - 1:height - 2]))
        if (len(shown) < len(view["rows"])
                and not grid[2].endswith(f"1-{len(shown)} of {len(view['rows'])}")):
            faults.append((width, height, "counter", grid[2]))
    w, _grid = prescreen_at(80, 20)
    rows = w.view()["rows"]
    for _ in range(len(rows) - 1):
        w.handle("down")
    entries = layout_lines(w.view(80), 80, 20)
    grid = overlay(entries, 80, 20)
    cursor = [text for _y, text, role, _s in entries if role.startswith("row-cursor")]
    shown = [line for line in grid if line.startswith("[x]") or line.startswith("[ ]")]
    if not (len(cursor) == 1 and rows[-1]["cells"][1] in cursor[0] and len(shown) < len(rows)
            and grid[2].endswith(f"{len(rows) - len(shown) + 1}-{len(rows)} of {len(rows)}")):
        faults.append(("scroll", cursor, grid[2]))
    record("66 the rows, the legend and the keys are three zones with a blank row between, "
           "and the counter follows the rows' budget and the cursor",
           not faults, repr(faults))
except Exception as e:
    record("66 the rows, the legend and the keys are three zones", False, repr(e))


try:
    w, _grid = prescreen_at(80, 24)
    view = w.view(80)
    entries = layout_lines(view, 80, 24)

    def styled(lane):
        _y, text, role, spans = next(e for e in entries
                                     if e[2].startswith("row") and f" {lane} " in e[1])
        return role, [(text[s:e], style) for s, e, style in spans]

    _y, footer, _role, spans = next(e for e in entries if e[2] == "footer")
    keys = [footer[s:e] for s, e, style in spans if style == "key"]
    _y, title, _role, spans = next(e for e in layout_lines(view, 80, 16) if e[2] == "title")
    note = [title[s:e] for s, e, style in spans if style == "title-note"]
    record("67 a ticked box, a reason the data gave, a key and the counter are drawn in their "
           "own style, and the cursor row is one bar",
           styled("astra-high@codex") == ("row", [("[x]", "mark-on")])
           and styled("astra-xhigh@codex") == ("row-dim", [("high wins on tbench", "why-data")])
           and styled("fable-xhigh@claude") == ("row-cursor", [])
           and keys == ["↑/↓ or j/k", "space/x", "enter", "b", "q"]
           and note == ["1-7 of 11"],
           repr((styled("astra-high@codex"), styled("astra-xhigh@codex"),
                 styled("fable-xhigh@claude"), keys, note)))
except Exception as e:
    record("67 a ticked box, a reason the data gave, a key and the counter are drawn in their own style",
           False, repr(e))


try:
    # every role and style a page emits is in the one table, and the table
    # resolves with and without colour: without, each style keeps its weight;
    # with, the three colours sit on the terminal's own background
    class FakeCurses:
        A_BOLD, A_DIM, A_REVERSE, A_UNDERLINE = 1, 2, 4, 8
        COLOR_GREEN, COLOR_CYAN, COLOR_YELLOW = 2, 6, 3

        class error(Exception):
            pass

        def __init__(self, colours, refuse=False):
            self.colours, self.refuse, self.pairs = colours, refuse, {}
            self.COLORS = 256 if colours else 0

        def has_colors(self):
            return self.colours

        def use_default_colors(self):
            if self.refuse:
                raise self.error("no default colours")

        def init_pair(self, n, fg, bg):
            self.pairs[n] = (fg, bg)

        def color_pair(self, n):
            return n << 8

    used = set()
    for _name, page in every_page(effort_rows=TBENCH, lanes=astra_lanes()):
        for _y, _text, role, spans in layout_lines(page.view(80), 80, 24):
            used.add(role)
            used.update(style for _s, _e, style in spans)
    mono = setup_tui._palette(FakeCurses(False))
    rich = FakeCurses(True)
    colour = setup_tui._palette(rich)
    refused = setup_tui._palette(FakeCurses(True, refuse=True))

    def pair_of(style):
        return rich.pairs.get(colour[style] >> 8)

    record("68 every role a page emits is in the style table, which resolves without colour "
           "and with the three colours on the terminal's own background",
           used <= set(setup_tui.STYLES) and set(mono) == set(setup_tui.STYLES)
           and mono["key"] == 1 and mono["mark-on"] == 1 and mono["header"] == 1 | 8
           and mono["step-here"] == 1 | 4 and mono["step-done"] == 0 and mono["steps"] == 2
           and mono["legend"] == 2 and mono["row-cursor"] == 4 and mono["row-cursor-dim"] == 4
           and mono["why-data"] == 0
           and refused == mono
           and pair_of("key") == (6, -1) and pair_of("mark-on") == (2, -1)
           and pair_of("step-done") == (2, -1) and pair_of("why-data") == (3, -1)
           # round 2: a warning is bold and, in colour, attention-yellow; a
           # value is settled-green; a term is bold; a description is dim
           and mono["warning"] == 1 and pair_of("warning") == (3, -1)
           and mono["value"] == 1 and pair_of("value") == (2, -1)
           and mono["term"] == 1 and mono["desc"] == 2 and colour["desc"] == 2
           and colour["key"] & 0xff == 1 and colour["title"] == mono["title"]
           and len(rich.pairs) == 3,
           repr((sorted(used - set(setup_tui.STYLES)), mono, rich.pairs)))
except Exception as e:
    record("68 every role a page emits is in the style table", False, repr(e))


# --- round 2: the harnesses page says what the scrub found, and r runs it again ---
def scanned_wizard(rescan=None, tier_lines=None):
    """A wizard on the refresh fixture, as launch builds one: the refreshed
    catalog, the plan, the discovery mapped against it, and the rows note."""
    frozen = catalog.load_json(os.path.join(REFRESH_DIR, "lanes.json"))
    rows = catalog.load_json(os.path.join(REFRESH_DIR, "aa-accepted.json"))
    found = discover.discover(frozen, fixture_dir=REFRESH_DIR)
    refreshed, plan = discover.refresh_catalog(
        frozen, found, published_models=sorted({r["model"] for r in rows if r.get("source") == "aa"}))
    w = Wizard(copy.deepcopy(refreshed), copy.deepcopy(ROUTING), None, DISCOVERED,
               "/tmp/lanes.json", "/tmp/routing.json", "",
               discovery=discover.map_lanes(found, refreshed), refresh=plan, effort_rows=rows,
               rows_note="Benchmark rows: Artificial Analysis fetched 3h ago, still fresh",
               rescan=rescan, tier_lines=tier_lines, clock=lambda: "14:07")
    return w, refreshed, plan


try:
    w, refreshed, plan = scanned_wizard()
    w.handle("enter")
    v = w.view(80)
    by_name = {row["cells"][0]: row["cells"] for row in v["rows"]}
    per_harness = lambda names: {h: sum(1 for n in names if n.endswith("@" + h)) for h in catalog.HARNESSES}
    new, removed = per_harness(plan["new"]), per_harness(plan["removed"])
    grid = screen(v, 80, 24)
    # a wizard built without a scrub result: the harnesses only, no counts
    bare = wizard(discovery="subprocess timed out")
    bare.handle("enter")
    bare_rows = {row["cells"][0]: row["cells"] for row in bare.view()["rows"]}
    record("69 the harnesses page says what the launch scrub found: per harness its status, the "
           "models it listed and the Lanes the refresh adds and removes, plus the rows note",
           v["screen"] == "discovery"
           and v["columns"] == ["harness", "status", "models", "new lanes", "removed lanes"]
           and by_name["codex"] == ["codex", "found", "7", str(new["codex"]), str(removed["codex"])]
           and by_name["agy"] == ["agy", "found", "7", str(new["agy"]), str(removed["agy"])]
           and by_name["grok"] == ["grok", "found", "4", str(new["grok"]), str(removed["grok"])]
           and by_name["claude"][2] == "4" and new["codex"] == 11 and removed["codex"] == 11
           and v["body"][0].startswith("Scanned at launch: ")
           and v["body"][1] == "Benchmark rows: Artificial Analysis fetched 3h ago, still fresh"
           and v["legend"] == [setup_tui.CLAUDE_COUNT_LEGEND]
           # r is offered only when there is a scrub to run
           and v["footer"] == setup_tui.DISCOVERY_FOOTER and "r: rescan" not in v["footer"]
           and grid[setup_tui.TOP].startswith("Scanned at launch")
           and all(len(line) <= 79 for line in grid)
           and bare_rows["codex"] == ["codex", "found", "—", "—", "—"]
           and bare.view()["legend"] == [],
           repr((by_name, v["body"], v["footer"], bare_rows)))
except Exception as e:
    record("69 the harnesses page says what the launch scrub found", False, repr(e))


try:
    # r: the scrub again, and every later page starts over from what it found;
    # the page comes before any decision, so nothing is thrown away
    calls = []
    frozen = catalog.load_json(os.path.join(REFRESH_DIR, "lanes.json"))

    def again():
        calls.append(1)
        doc = copy.deepcopy(frozen)
        doc["lanes"]["extra-high@grok"] = copy.deepcopy(doc["lanes"]["grok46-high@grok"])
        return {"lanes_doc": doc, "discovered": {"grok"}, "discovery": "probe failed",
                "refresh": {"models": [], "new": ["extra-high@grok"], "removed": []},
                "rows_note": "Benchmark rows: Artificial Analysis fetched just now",
                "effort_rows": None, "bench": None, "message": "bench: no rows"}

    w, refreshed, _plan = scanned_wizard(rescan=again, tier_lines="extra-high@grok 4\n")
    w.handle("enter")
    before = w.view(100)
    w.handle("r")
    after = w.view(100)
    ready_after = w.rescan_ready()
    rows = {row["cells"][0]: row["cells"] for row in after["rows"]}
    w.handle("enter")
    carry = w.view()
    carried = [r["cells"][1] for r in carry["rows"] if r["marked"]]
    w.handle("enter")
    tier4 = [r["cells"][1] for r in w.view()["rows"] if r["marked"]]
    # a scrub that fails is a message and changes nothing
    def broken():
        raise RuntimeError("codex would not answer")
    w2, refreshed2, _plan2 = scanned_wizard(rescan=broken)
    w2.handle("enter")
    w2.handle("r")
    unchanged = w2.lanes_doc == refreshed2 and w2.scanned == "at launch" and w2.screen == "discovery"
    # without a scrub to run, r is any key and continues; on a later page it is nothing
    w3, _r, _p = scanned_wizard()
    w3.handle("enter"); w3.handle("r")
    w4, _r, _p = scanned_wizard(rescan=again)
    w4.handle("enter"); w4.handle("enter")
    calls_before = len(calls)
    w4.handle("r")
    record("70 r on the harnesses page runs the scrub again, restarts the later pages from its "
           "result, applies the tiers-from lines again, and a failure is a message",
           before["footer"] == setup_tui.DISCOVERY_RESCAN_FOOTER
           and len(calls) == 1 and after["screen"] == "discovery"
           and after["body"][0].startswith("Scanned at 14:07: ")
           and after["body"][1] == "Benchmark rows: Artificial Analysis fetched just now"
           and rows["grok"] == ["grok", "found", "—", "1", "0"]
           and rows["codex"] == ["codex", "missing", "—", "0", "0"]
           and after["legend"] == []
           and after["message"].startswith("Rescanned at 14:07: 1 new Lane, 0 removed; bench: no rows; "
                                           "Lines: 1 took a tier;")
           and "not named, so off" in after["message"]
           # still the harnesses page, so r is still on offer
           and w.scanned == "at 14:07" and ready_after is True
           and "extra-high@grok" in w.lanes_doc["lanes"] and carried == ["extra-high@grok"]
           and tier4 == ["extra-high@grok"] and w.tier == 4
           and w2.message == "rescan failed: codex would not answer" and unchanged
           and w3.screen == "prescreen"
           and w4.screen == "prescreen" and len(calls) == calls_before,
           repr((calls, after["message"], rows, carried, tier4, w2.message, w3.screen)))
except Exception as e:
    record("70 r on the harnesses page runs the scrub again", False, repr(e))


try:
    # the carry legend defines only the reasons on the page, as a definition
    # list whose one coloured term is the one coloured cell, and counts the
    # benchmarked models no lane runs instead of naming them
    w = wizard(lanes=astra_lanes(), effort_rows=TBENCH)
    w.handle("enter"); w.handle("enter")
    v = w.view(80)
    entries = layout_lines(v, 80, 24)
    def_lines = [(text, [(text[s:e], st) for s, e, st in spans])
                 for _y, text, role, spans in entries
                 if role == "legend" and spans]
    plain = wizard()
    plain.handle("enter"); plain.handle("enter")
    record("71 the carry page defines the reasons on it, the dominated term in the data's colour, "
           "and counts the benchmarked models that are nobody's lane",
           [d["term"] for d in v["defs"]] == ["X wins on S", "not dominated", "no rows"]
           and v["defs"][0] == setup_tui.DOMINATED_DEF and v["defs"][0]["style"] == "why-data"
           and v["legend"] == [f"{len(w._unmatched)} benchmarked models have no lane"]
           and def_lines[0][1] == [("X wins on S", "why-data")]
           and def_lines[1][1] == [("not dominated", "term")]
           and def_lines[0][0].startswith("X wins on S    effort X scores")
           and all(len(text) <= 79 for text, _s in def_lines)
           # no rows at all: the one definition that case earns, and no count
           and plain.view()["defs"] == [setup_tui.ABSENCE_DEF] and plain.view()["legend"] == [],
           repr((v["defs"], v["legend"], def_lines)))
except Exception as e:
    record("71 the carry page defines the reasons on it", False, repr(e))


try:
    # the review page's bottom: the keys spelled out, the rule, the count, then
    # the warning in its own style, last in the zone and above the keys' blank row
    w = wizard()
    not_carried(w, "grok46-high@grok")
    mark_as(w, {"fable-xhigh@claude": 4, "sol-high@codex": 3,
                "terra-high@codex": 2, "luna-low@codex": 1, "flash-high@agy": 1})
    v = w.view(80)
    entries = layout_lines(v, 80, 24)
    grid = overlay(entries, 80, 24)
    zone = [(y, text, role) for y, text, role, _s in sorted(entries) if role in ("legend", "warning")]
    warning_rows = [y for y, _t, role in zone if role == "warning"]
    key_spans = [text[s:e] for _y, text, role, spans in entries if role == "legend"
                 for s, e, st in spans if st == "key"]
    # Tiers 4, 3 and 2 each hold one lane here, so each drains one Meter
    record("72 the review page separates the key help, the rule and the warning, and the "
           "warning is drawn as one",
           v["defs"] == list(setup_tui.REVIEW_MOVE_DEFS)
           and v["legend"] == [setup_tui.REVIEW_ORDER_LEGEND, "1 lane not carried keeps its catalog tier."]
           and v["warnings"] == ["Tier 2 depends on Meter codex; a Gate stop there stops the Tier.",
                                 "Tier 3 depends on Meter codex; a Gate stop there stops the Tier.",
                                 "Tier 4 depends on Meter claude-fable; a Gate stop there stops the Tier."]
           and key_spans == ["J/K, shift-↑/↓", "1-4"]
           and [role for _y, _t, role in zone] == ["legend"] * 4 + ["warning"] * 3
           # the warnings are the last of the zone, above the keys' blank row
           and warning_rows == [24 - 3 - 4, 24 - 3 - 3, 24 - 3 - 2] and grid[24 - 3 - 1] == ""
           and grid[warning_rows[0]].startswith("Tier 2 depends on Meter codex"),
           repr((v["defs"], v["legend"], v["warnings"], zone)))
except Exception as e:
    record("72 the review page separates the key help, the rule and the warning", False, repr(e))


try:
    # the routing page groups each class under its heading and its sentence
    # from the Class guide, then ranking; the cursor never lands on a heading
    guide = setup_tui.class_descriptions()
    w = wizard()
    start(w)
    to_confirm(w)
    w.handle("b")
    assert w.screen == "routing", w.screen
    v = w.view(80)
    headings = [(r["cells"][0], r["cells"][1]) for r in v["rows"] if r.get("styles")]
    settings = [r["cells"][0] for r in v["rows"] if not r.get("styles")]
    landed = []
    for _ in range(len(w._routing_settings()) + 1):
        landed.append(next(r["cells"][0] for r in w.view()["rows"] if r["cursor"]))
        w.handle("down")
    entries = layout_lines(w.view(80), 80, 24)
    heading_spans = [[(text[s:e], st) for s, e, st in spans]
                     for _y, text, role, spans in entries if role == "row" and spans
                     and any(st == "section" for _s, _e, st in spans)]
    narrow = screen(w.view(80), 80, 24)
    wide = screen(w.view(120), 120, 30)
    lost = setup_tui.class_descriptions("/no/such/guide.md")
    record("73 the routing page groups each class with its sentence from the Class guide and "
           "ranking with the pick's settings; only a setting takes the cursor",
           guide["scout"] == "Find and explain facts about the software"
           and guide["impl"] == "Turn a supplied specification into code changes with executable checks"
           and [name for name, _d in headings] == [*catalog.CLASSES, "ranking"]
           and all(desc == setup_tui._clip(guide[name], len(desc)) for name, desc in headings[:5])
           and settings == ["  floor", "  ceiling"] * 5 + ["  margin", "  gate", "  meters"]
           and all(name.startswith("  ") for name in landed) and landed[0] == "  floor"
           and landed[13] == "  floor" and v["elastic"] == "value"
           and heading_spans and heading_spans[0][0] == ("scout", "section")
           and heading_spans[0][1][1] == "desc"
           # at 80 the sentence gives way to the panel; at 120 it is whole
           and any("│ scout floor" in line or "│ " in line for line in narrow)
           and any(line.startswith("scout       Find and explain facts about the") for line in narrow)
           and any("impl        Turn a supplied specification into code changes with executable checks"
                   in line for line in wide)
           and all(len(line) <= 79 for line in narrow)
           and lost == {name: "" for name in catalog.CLASSES},
           repr((headings, landed, heading_spans[:1], [l for l in narrow if l.startswith("scout")])))
except Exception as e:
    record("73 the routing page groups each class with its sentence from the Class guide", False, repr(e))


try:
    # the confirm page's definition list: each term bold, its value in the
    # value style, the meaning beside; metering off changes the three texts
    w = wizard()
    start(w)
    to_confirm(w)
    assert w.screen == "confirm", w.screen
    entries = layout_lines(w.view(80), 80, 24)
    styled = [(text, [(text[s:e], st) for s, e, st in spans])
              for _y, text, role, spans in sorted(entries) if role == "legend" and spans]
    w.routing_doc["meters"] = False
    off = {d["term"]: d for d in w.view()["defs"]}
    focused = wizard(focus="routing")
    focused.handle("enter")
    record("74 the confirm page's definitions align term, value and meaning, and say what "
           "metering off leaves stored",
           [text.split("  ")[0] for text, _s in styled] == ["classes", "margin", "gate", "meters", "off"]
           and styled[1][1] == [("margin", "term"), ("0.2", "value")]
           and styled[2][1] == [("gate", "term"), ("0.1", "value")]
           and styled[3][1] == [("meters", "term"), ("on", "value")]
           and styled[0][1] == [("classes", "term")] and styled[4][1] == [("off", "term")]
           and styled[1][0].startswith("margin   0.2  the pace lead")
           and all(len(text) <= 79 for text, _s in styled)
           and off["meters"]["value"] == "off" and "stay stored" in off["meters"]["text"]
           and off["margin"]["text"] == "stored; metering is off"
           and focused.screen == "confirm" and focused.view()["defs"] == []
           and focused.view()["legend"] == ["Only the listed changes will be written."],
           repr((styled, off)))
except Exception as e:
    record("74 the confirm page's definitions align term, value and meaning", False, repr(e))

sys.exit(1 if fails else 0)
