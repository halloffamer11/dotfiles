#!/usr/bin/env python3
"""Tests for bench_page.py. Run: python3 tests/test_bench_page.py"""
import copy
import json
import os
import re
import sys
import tempfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
DELEGATE_DIR = os.path.abspath(os.path.join(HERE, "..", "scripts"))
FIXTURE = os.path.join(HERE, "fixture", "bench-epoch.csv")
REAL_DATA = os.path.abspath(os.path.join(HERE, "..", "..", "..", "..",
                                         ".scratch", "delegate-redesign", "_data"))
sys.path.insert(0, DELEGATE_DIR)

import bench
import bench_page
import catalog
import setup_tui

LANES = catalog.load_json(os.path.abspath(os.path.join(HERE, "..", "assets", "samples", "lanes.json")))
fails = 0


def record(name, ok, detail=""):
    global fails
    if ok:
        print(f"PASS {name}")
    else:
        fails += 1
        print(f"FAIL {name}: {detail}")


def remote_resource(html):
    return re.search(r"""(?:src|href)\s*=\s*['"]https?://[^'"]*\.(?:js|css)""", html, re.I)


def svgs_of(html):
    return re.findall(r"<svg viewBox.*?</svg>", html, re.S)


def label_boxes(svg):
    """Label boxes as the placer sees them, to test that none overprint."""
    boxes = []
    for lx, ly, anchor, text in re.findall(
            r'<text x="([\d.-]+)" y="([\d.-]+)" class="(?:effort|name)[^"]*" '
            r'text-anchor="(\w+)">([^<]*)<', svg):
        lx, ly, w = float(lx), float(ly), len(text) * 6.5 + 3
        x0 = lx if anchor == "start" else (lx - w if anchor == "end" else lx - w / 2)
        boxes.append((x0, ly - 9, x0 + w, ly + 3, text))
    return boxes


def overlaps(boxes):
    return [(a[4], b[4]) for i, a in enumerate(boxes) for b in boxes[i + 1:]
            if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]]


def marks(svg):
    """[(kind classes, first mark tag)] for every point on a chart."""
    return re.findall(r'<g class="pt ([^"]*)"><title>[^<]*</title>'
                      r'<circle[^>]*fill="transparent" />(<(?:circle|path)[^>]*>)', svg)


EFFORT_ROWS = [
    {"source": "swerb", "url": "https://example.invalid/leaderboard/", "model": "gpt-5.6-sol",
     "effort": "high", "benchmark": "SWE Refactor Bench", "score": 19.0, "cost_usd": 9.1,
     "observed": "2026-09-10", "provenance": "unlabelled", "uncertain": False},
    {"source": "aa", "url": "https://example.invalid/models/", "model": "gpt-5.6-sol",
     "effort": "low", "benchmark": "SWE-Bench verified", "score": 4.0, "cost_usd": 1.2,
     "observed": "2026-09-10", "provenance": "unlabelled", "uncertain": True},
]

# The catalog with the astra sweep the wizard's own test uses, and a sweep of
# published rows in which exactly one lane is dominated, plus comparators.
ASTRA = copy.deepcopy(LANES)
for effort in ("low", "medium", "high", "xhigh", "max"):
    lane = copy.deepcopy(ASTRA["lanes"]["sol-high@codex"])
    lane["model"] = "gpt-6-astra"
    lane["effort"] = effort
    ASTRA["lanes"][f"astra-{effort}@codex"] = lane
SWEEP = []
for effort, score, cost in (("low", 50.61, 1557.3), ("medium", 54.24, 1914.8),
                            ("high", 57.88, 2269.42), ("xhigh", 57.88, 2350.51),
                            ("max", 58.18, 3267.18)):
    SWEEP.append({"source": "tbench", "model": "GPT-6 Astra", "effort": effort,
                  "benchmark": "Terminal-Bench 4.0", "score": score, "score_unit": "%",
                  "cost_usd": cost, "uncertain": False, "observed": "2026-09-03",
                  "provenance": "unlabelled"})
SWEEP += [
    {"source": "tbench", "model": "GLM-5.3", "effort": "max", "benchmark": "Terminal-Bench 4.0",
     "score": 41.82, "score_unit": "%", "cost_usd": 2727.63, "uncertain": False,
     "observed": "2026-08-14", "provenance": "unlabelled"},
    {"source": "tbench", "model": "Opus 5", "effort": "max", "benchmark": "Terminal-Bench 4.0",
     "score": 51.82, "score_unit": "%", "cost_usd": 5969.11, "uncertain": False,
     "observed": "2026-07-24", "provenance": "unlabelled"},
    # our model, at an effort no lane runs: context, not a lane's figure
    {"source": "tbench", "model": "GPT-5.6 Sol", "effort": "max", "benchmark": "Terminal-Bench 4.0",
     "score": 37.27, "score_unit": "%", "cost_usd": 2541.7, "uncertain": False,
     "observed": "2026-06-26", "provenance": "unlabelled"},
]


# --- the basics ------------------------------------------------------------------
try:
    collected = bench.collect(LANES, epoch_csv=FIXTURE, key_file=None)
    html = bench_page.render(collected, LANES)
    record("page from epoch fixture",
           "claude-fable-5-1" in html and "DeepSWE" in html and "98.0" in html
           and "<table" in html and "Read-only" in html,
           html[:400])
    record("fixture page has no remote stylesheet or script",
           remote_resource(html) is None and "<style>" in html
           and "<script" not in html.lower() and "<link" not in html.lower(),
           html[:200])
except Exception as e:
    record("page from epoch fixture", False, repr(e))

try:
    html = bench_page.render(None, LANES)
    record("page with bench=None names missing data",
           "Benchmark collection data is missing" in html
           and "Per-effort data is missing" in html
           and "<svg viewBox" not in html,
           html[:400])
except Exception as e:
    record("page with bench=None names missing data", False, repr(e))

try:
    collected = bench.collect(LANES, epoch_csv=FIXTURE, key_file=None)
    html = bench_page.render(collected, LANES, EFFORT_ROWS)
    record("page with per-effort rows carries every number and its provenance",
           "unlabelled" in html and "SWE Refactor Bench" in html and "uncertain" in html
           and "19.0" in html and "$9.1" in html and "2026-09-10" in html
           and "example.invalid/leaderboard" in html and "gpt-5.6-sol" in html,
           html[:400])
    record("effort page has no remote stylesheet or script", remote_resource(html) is None)
except Exception as e:
    record("page with per-effort rows carries every number and its provenance", False, repr(e))

try:
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "bench.html")
        collected = bench.collect(LANES, epoch_csv=FIXTURE, key_file=None)
        returned = bench_page.write(path, collected, LANES, EFFORT_ROWS)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        record("write returns path and persists HTML",
               returned == path and os.path.isfile(path) and "DeepSWE" in text)
except Exception as e:
    record("write returns path and persists HTML", False, repr(e))

try:
    record("light and dark are both defined, and the toggle wins both ways",
           "prefers-color-scheme: dark" in bench_page.STYLE
           and ':root:not([data-theme="light"])' in bench_page.STYLE
           and ':root[data-theme="dark"]' in bench_page.STYLE
           and bench_page.STYLE.count("--surface:") >= 3)
except Exception as e:
    record("light and dark are both defined, and the toggle wins both ways", False, repr(e))


# --- the chart ---------------------------------------------------------------------
try:
    rows = [
        {"source": "t", "model": "m-a", "effort": "low", "benchmark": "B1",
         "score": 10.0, "cost_usd": 1.0, "uncertain": False},
        {"source": "t", "model": "m-a", "effort": "high", "benchmark": "B1",
         "score": 20.0, "cost_usd": 2.0, "uncertain": False},
        {"source": "t", "model": "m-b", "effort": "low", "benchmark": "B2",
         "score": 5.0, "cost_usd": 3.0, "uncertain": False},
        {"source": "u", "model": "gpt-5.6-sol", "effort": "high", "benchmark": "B1",
         "score": 7.0, "cost_usd": 4.0, "uncertain": False},
        # drawn dashed and hollow, and named weak in the table
        {"source": "t", "model": "m-c", "effort": "low", "benchmark": "B1",
         "score": 9.0, "cost_usd": 9.0, "uncertain": True},
        # cannot be placed on a log axis; listed as not drawn
        {"source": "t", "model": "m-d", "effort": "low", "benchmark": "B1",
         "score": 9.0, "cost_usd": 0, "uncertain": False},
    ]
    page = bench_page.render(None, LANES, rows)
    svgs = svgs_of(page)
    for svg in svgs:
        ET.fromstring(svg)          # raises if the markup is malformed
    boards = {(r["source"], r["benchmark"]) for r in rows}
    weak = [m for m in marks(page) if "weak" in m[0]]
    record("one well-formed chart per source and benchmark, never two sources on one cost axis",
           len(svgs) == len(boards)
           and "Not drawn" in page and "m-d low" in page
           and len(weak) == 1 and "stroke-dasharray" in weak[0][1]
           and 'fill="var(--surface' in weak[0][1]
           and "a dollar on one board is not a dollar on another" in page,
           f"svgs={len(svgs)} boards={len(boards)} weak={weak}")
except Exception as e:
    record("one well-formed chart per source and benchmark, never two sources on one cost axis",
           False, repr(e))

try:
    page = bench_page.render(None, LANES, [])
    record("the chart section says so when there are no rows",
           "No per-effort rows" in page and "<svg viewBox" not in page)
    page = bench_page.render(None, LANES, [{"source": "t", "model": "m", "effort": "low",
                                            "benchmark": "B", "score": 1, "cost_usd": 0}])
    record("a board with nothing drawable says so and still tables the row",
           "nothing to draw" in page and "<svg viewBox" not in page and "<td>low</td>" in page)
except Exception as e:
    record("the chart section says so when there are no rows", False, repr(e))

try:
    page = bench_page.render(None, ASTRA, SWEEP)
    svg = svgs_of(page)[0]
    kinds = {}
    for cls, tag in marks(svg):
        kinds.setdefault(cls.split()[0], []).append(tag)
    lane_ok = all("<circle" in t and 'fill="var(--accent' in t for t in kinds.get("lane", []))
    off_ok = all("<circle" in t and 'fill="var(--off' in t for t in kinds.get("lane_off", []))
    own_ok = all("<circle" in t and 'fill="var(--surface' in t and 'stroke="var(--accent'
                 in t for t in kinds.get("own_other", []))
    cmp_ok = all("<path" in t and 'fill="var(--surface' in t and 'stroke="var(--muted'
                 in t for t in kinds.get("comparator", []))
    record("a lane, a proposed-off lane, our model at another effort and a comparator "
           "each have their own mark, by shape and fill, not hue alone",
           set(kinds) == {"lane", "lane_off", "own_other", "comparator"}
           and len(kinds["lane"]) == 4 and len(kinds["lane_off"]) == 1
           and len(kinds["own_other"]) == 1 and len(kinds["comparator"]) == 2
           and lane_ok and off_ok and own_ok and cmp_ok
           and bench_page.NO_LANE in page,
           f"kinds={ {k: len(v) for k, v in kinds.items()} } lane={lane_ok} off={off_ok} own={own_ok} cmp={cmp_ok}")
except Exception as e:
    record("a lane, a proposed-off lane, our model at another effort and a comparator "
           "each have their own mark, by shape and fill, not hue alone", False, repr(e))

# --- the page is the evidence for the pre-screen, so it has to say the same -----
try:
    page = bench_page.render(None, ASTRA, SWEEP)
    proposals = setup_tui.propose_enabled(ASTRA, SWEEP)
    off = sorted(name for name, (on, _why) in proposals.items()
                 if not on and _why.startswith("dominated by"))
    struck = re.findall(r'<g class="pt lane_off"><title>([^<]*)</title>', page)
    verdict = re.search(r'<p class="verdict">(.*?)</p>', page, re.S).group(1)
    caption = re.search(r"<figcaption>(.*?)</figcaption>", page, re.S).group(1)
    body = page[page.find('<table class="sweep">'):]
    order = re.findall(r"<td>(low|medium|high|xhigh|max)</td><td>", body)
    record("the page marks what the wizard marks, names it at the top, and shows the arithmetic",
           off == ["astra-xhigh@codex"] and len(struck) == 1 and "xhigh" in struck[0]
           and "astra-xhigh@codex" in verdict and "dominated by high" in verdict
           and "scores the same as high" in caption and "$81.1 more (+4%)" in caption
           and "off: dominated by high" in body
           and order[:5] == ["low", "medium", "high", "xhigh", "max"]
           and "GPT-6 Astra" in page and "gpt-6-astra" in page,
           f"off={off} struck={struck} verdict={verdict[:120]!r} order={order[:6]}")
except Exception as e:
    record("the page marks what the wizard marks, names it at the top, and shows the arithmetic",
           False, repr(e))

try:
    page = bench_page.render(None, ASTRA, SWEEP)
    body = page[page.find('<table class="sweep">'):page.find("</table>")]
    cells = re.findall(r'<td class="num step">([^<]*)</td>', body)
    record("the sweep table gives each step's score and cost delta",
           "+3.6%" in cells and "0.0%" in cells
           and any(c.startswith("+$81.1") and "(+4%)" in c for c in cells)
           and any(c.startswith("+$917") and "(+39%)" in c for c in cells),
           f"cells={cells}")
except Exception as e:
    record("the sweep table gives each step's score and cost delta", False, repr(e))

try:
    page = bench_page.render(None, ASTRA, SWEEP)
    svg = svgs_of(page)[0]
    circles = [(float(a), float(b)) for a, b in
               re.findall(r'<circle cx="([\d.]+)" cy="([\d.]+)" r="(?:5|6)', svg)]
    closest = min(((cx - dx) ** 2 + (cy - dy) ** 2) ** 0.5
                  for i, (cx, cy) in enumerate(circles) for dx, dy in circles[i + 1:])
    clash = overlaps(label_boxes(svg))
    inside = all(2 <= cx <= bench_page.CHART_W - 2 and 2 <= cy for cx, cy in circles)
    ticks = re.findall(r'class="tick" text-anchor="middle">([^<]+)<', svg)
    record("no two labels overprint, every point is inside the frame, and a tick is a dollar",
           not clash and inside and closest >= 8
           and ticks and all(t.startswith("$") and "e+" not in t for t in ticks),
           f"closest={closest:.1f} clash={clash} inside={inside} ticks={ticks}")
except Exception as e:
    record("no two labels overprint, every point is inside the frame, and a tick is a dollar",
           False, repr(e))

try:
    page = bench_page.render(None, ASTRA, SWEEP)
    svg = svgs_of(page)[0]
    ground = re.search(r'<rect[^>]*fill="([^"]*)"', svg)
    first_child = svg.split(">", 1)[1].lstrip().startswith("<rect")
    label = re.search(r'aria-label="([^"]*)"', svg).group(1)
    record("the panel ground is in the document, hollow interiors are that ground, "
           "and the image label carries the finding",
           ground and ground.group(1) == bench_page.GROUND and first_child
           and ground.group(1).startswith("var(--surface, #")
           and "Proposed off: astra-xhigh@codex" in label and "table that follows" in label,
           f"ground={ground and ground.group(1)} first={first_child} label={label!r}")
except Exception as e:
    record("the panel ground is in the document, hollow interiors are that ground, "
           "and the image label carries the finding", False, repr(e))

try:
    # self-reported rows still count in the wizard's rule; uncertain never do.
    # Either way the figure must not look verified.
    rows = [dict(SWEEP[2], provenance="self-reported"), dict(SWEEP[3])]
    page = bench_page.render(None, ASTRA, rows)
    svg = svgs_of(page)[0]
    weak = [m for m in marks(svg) if "weak" in m[0]]
    body = page[page.find('<table class="sweep">'):]
    record("a weakly-sourced figure is drawn dashed and hollow and flagged in the table",
           len(weak) == 1 and "stroke-dasharray" in weak[0][1]
           and 'fill="var(--surface' in weak[0][1]
           and 'class="flag">self-reported' in body
           and 'class="lane weak' in body
           and "self-reported rows still count" in page,
           f"weak={weak}")
except Exception as e:
    record("a weakly-sourced figure is drawn dashed and hollow and flagged in the table",
           False, repr(e))

try:
    # a board where a carried lane is measured at its own effort comes before
    # one that only has our models at efforts no lane runs
    other = [{"source": "swerb", "model": "gpt-5.6-sol", "effort": e, "benchmark": "SWE Refactor Bench",
              "score": s, "cost_usd": c, "uncertain": False}
             for e, s, c in (("low", 7.0, 5.9), ("medium", 6.5, 6.0), ("xhigh", 9.5, 19.1), ("max", 28.5, 143.5))]
    page = bench_page.render(None, ASTRA, other + SWEEP)
    record("the board with carried lanes measured at their effort comes first",
           page.find("Terminal-Bench 4.0</h2>") < page.find("SWE Refactor Bench</h2>")
           and page.find("SWE Refactor Bench</h2>") != -1)
except Exception as e:
    record("the board with carried lanes measured at their effort comes first", False, repr(e))


# --- the trap: a per-model score is never a lane's score by default --------------
try:
    collected = bench.collect(copy.deepcopy(ASTRA), epoch_csv=FIXTURE, key_file=None)
    # the fixture measures fable at max; the only fable lane runs xhigh
    page = bench_page.render(collected, ASTRA, SWEEP)
    table = page[page.find('<table class="scores">'):page.find("</table>", page.find('<table class="scores">'))]
    fable = table[table.find("claude-fable-5-1"):table.find("</tr>", table.find("claude-fable-5-1"))]
    sol = table[table.find("gpt-5.6-sol"):table.find("</tr>", table.find("gpt-5.6-sol"))]
    heads = re.findall(r"<th[^>]*>([^<]*)</th>", table)
    record("a figure measured at an effort no lane runs is shown grey and unattributed; "
           "one at the lane's effort names the lane; no column claims a lane effort",
           fable.count('class="fig unattributed"') == 5 and "at max, not carried" in fable
           and sol.count('class="fig attributed"') == 5 and 'title="sol-high@codex"' in sol
           and "at high" in sol
           and not any(h.lower().startswith("effort") or "lane effort" in h.lower() for h in heads)
           and "Mean rank" not in page and "mean rank" not in page,
           f"heads={heads} fable={fable[:300]!r}")
    # the rank's job, without the rank: a bar per figure scaled to the column's
    # largest, so the fixture's 98.0 fills the column and the 60.0 is 61% of it
    widths = re.findall(r'style="width:(\d+)%"', fable)
    luna = table[table.find("gpt-5.6-luna"):table.find("</tr>", table.find("gpt-5.6-luna"))]
    record("a bar under each figure carries its share of the column, so models compare down a column",
           widths == ["100"] * 5 and re.findall(r'style="width:(\d+)%"', luna)[0] == "61",
           f"fable={widths} luna={re.findall(r'style=\"width:(\\d+)%\"', luna)}")
except Exception as e:
    record("a figure measured at an effort no lane runs is shown grey and unattributed; "
           "one at the lane's effort names the lane; no column claims a lane effort",
           False, repr(e))

try:
    collected = bench.collect(LANES, epoch_csv=FIXTURE, key_file=None)
    doctored = copy.deepcopy(collected)
    doctored["models"]["gpt-5.6-sol"]["epoch"]["cells"]["DeepSWE"]["effort"] = "unknown"
    page = bench_page.render(doctored, LANES, None)
    table = page[page.find('<table class="scores">'):]
    sol = table[table.find("gpt-5.6-sol"):table.find("</tr>", table.find("gpt-5.6-sol"))]
    record("an unstated effort is attributed to no lane and says so",
           "effort not stated" in sol and sol.count('class="fig unattributed"') == 1
           and sol.count('class="fig attributed"') == 4,
           sol[:400])
except Exception as e:
    record("an unstated effort is attributed to no lane and says so", False, repr(e))

try:
    # the shape after the attribution fix: a cell keyed by measured effort,
    # `unknown` a literal key, several figures on one benchmark, and the AA
    # effort carried through collect()
    collected = bench.collect(LANES, epoch_csv=FIXTURE, key_file=None)
    future = copy.deepcopy(collected)
    sol = future["models"]["gpt-5.6-sol"]
    sol["epoch"]["cells"]["DeepSWE"] = {
        "high": {"performance": 0.90, "source": "f", "duplicates": 0},
        "max": {"performance": 0.95, "source": "f", "duplicates": 0},
        "unknown": {"performance": 0.47, "source": "f", "duplicates": 0},
    }
    sol["epoch"]["cells"]["FrontierCode"] = {"xhigh": {"performance": 0.5, "source": "f", "duplicates": 0}}
    future["aa_skipped"] = None
    future["aa_columns"] = ["Coding Index"]
    for model, rec in future["models"].items():
        rec["aa"] = {"cols": {"Coding Index": 50.0}, "mean": None, "mean_s": "", "effort": None}
    sol["aa"] = {"cols": {"Coding Index": 61.0}, "mean": None, "mean_s": "", "effort": "high"}
    future["lanes"] = {"sol-high@codex": {"cells": {}, "mean": 1.0, "mean_s": "1.0 (n=1)", "n": 1}}
    page = bench_page.render(future, LANES, None)
    table = page[page.find('<table class="scores">'):]
    row = table[table.find("gpt-5.6-sol"):table.find("</tr>", table.find("gpt-5.6-sol"))]
    tds = re.findall(r"<td[^>]*>.*?</td>", row, re.S)
    deepswe, frontier, aa_cell = tds[2], tds[3], tds[-1]
    record("the post-fix cell shape reads: every effort's figure shown, in effort order, "
           "each attributed on its own, and the AA effort attributed too",
           deepswe.count('<span class="fig') == 3
           and re.findall(r"at (high|max)|effort not stated", deepswe) == ["high", "max", "effort not stated"]
           and deepswe.count('class="fig attributed"') == 1 and 'title="sol-high@codex"' in deepswe
           and "at max, not carried" in deepswe
           and frontier.count('class="fig unattributed"') == 1 and "at xhigh, not carried" in frontier
           and 'class="fig attributed" title="sol-high@codex">61<span class="at">at high' in aa_cell
           and "Artificial Analysis</th>" in table,
           f"deepswe={deepswe!r} frontier={frontier!r} aa={aa_cell!r}")
except Exception as e:
    record("the post-fix cell shape reads: every effort's figure shown, in effort order, "
           "each attributed on its own, and the AA effort attributed too", False, repr(e))


# --- comparators are context, and the real data stays legible --------------------
try:
    page = bench_page.render(None, ASTRA, SWEEP)
    body = page[page.find('<table class="sweep">'):]
    record("a comparator is present as context and marked as nobody's lane, never dropped",
           "GLM-5.3" in page and "Opus 5" in page
           and body.count(f'<span class="sub">{bench_page.NO_LANE}</span>') == 2
           and 'class="comparator' in body
           and "Top of the board: gpt-6-astra max" in page)
except Exception as e:
    record("a comparator is present as context and marked as nobody's lane, never dropped",
           False, repr(e))

try:
    real = [os.path.join(REAL_DATA, f) for f in ("tbench-accepted.json", "swerb-accepted.json")]
    live = os.path.expanduser("~/.config/delegate/lanes.json")
    if all(os.path.isfile(p) for p in real) and os.path.isfile(live):
        rows = []
        for p in real:
            with open(p, encoding="utf-8") as f:
                rows.extend(json.load(f))
        with open(live, encoding="utf-8") as f:
            lanes = json.load(f)
        page = bench_page.render(None, lanes, rows)
        clashes = [overlaps(label_boxes(svg)) for svg in svgs_of(page)]
        record("the real data draws with no overprinted label on either board",
               len(clashes) == 2 and not any(clashes), f"clashes={clashes}")
    else:
        record("the real data draws with no overprinted label on either board", True,
               "(real data not present; skipped)")
except Exception as e:
    record("the real data draws with no overprinted label on either board", False, repr(e))


sys.exit(1 if fails else 0)
