#!/usr/bin/env python3
"""Tests for bench_page.py. Run: python3 tests/test_bench_page.py

The plots are drawn by assets/bench_page.js from JSON the page carries. The
decisions in that JSON are Python's and are tested here directly; the frontier
and the layout are the script's, and the tests that need them run its pure
`layout` under node when node is on PATH."""
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DELEGATE_DIR = os.path.abspath(os.path.join(HERE, "..", "scripts"))
FIXTURE = os.path.join(HERE, "fixture", "bench-epoch.csv")
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
REAL_DATA = os.path.join(REPO, ".scratch", "delegate-redesign", "_data")
STOWED_LANES = os.path.join(REPO, "stow", "delegate", ".config", "delegate", "lanes.json")
sys.path.insert(0, DELEGATE_DIR)

import bench
import bench_page
import catalog
import setup_tui

LANES = catalog.load_json(os.path.abspath(os.path.join(HERE, "..", "assets", "samples", "lanes.json")))
NODE = shutil.which("node")
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


def data_of(html):
    """The JSON the plots draw, or None when the page carries none."""
    m = re.search(r'<script type="application/json" id="bench-data">(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else None


def board_named(data, benchmark):
    return next(b for b in data["boards"] if b["benchmark"] == benchmark)


def overlaps(labels):
    boxes = [(l["box"], l["text"]) for l in labels]
    return [(a[1], b[1]) for i, a in enumerate(boxes) for b in boxes[i + 1:]
            if a[0][0] < b[0][2] and b[0][0] < a[0][2] and a[0][1] < b[0][3] and b[0][1] < a[0][3]]


LAYOUT_DRIVER = r"""
const fs = require("fs"), vm = require("vm");
const mod = { exports: {} };
vm.runInNewContext(fs.readFileSync(process.argv[2], "utf8"), { module: mod });
const P = mod.exports;
const cases = JSON.parse(fs.readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify({ W: P.W, H: P.H, PAD: P.PAD, out: cases.map(({ board, state }) => {
  const st = Object.assign({ frontier: "lanes", labels: "lanes", lines: true, zoom: null }, state);
  for (const k of ["hiddenModels", "hiddenHarness", "hiddenEfforts"]) st[k] = new Set(state[k] || []);
  const lay = P.layout(board, st);
  return { frontier: lay.frontier.map((p) => p.name + " " + p.effort),
           labels: lay.labels.map((l) => ({ text: l.text, box: l.box })),
           xTicks: lay.xTicks.map((t) => t.text), yTicks: lay.yTicks.map((t) => t.text),
           points: lay.points.map((q) => [q.x, q.y]), shown: lay.shown.length };
}) }));
"""


def run_layout(cases):
    """The script's own layout for each (board, settings) case, run under
    node. None when node is not on PATH."""
    if not NODE:
        return None
    with tempfile.TemporaryDirectory() as td:
        driver = os.path.join(td, "driver.js")
        with open(driver, "w", encoding="utf-8") as f:
            f.write(LAYOUT_DRIVER)
        result = subprocess.run([NODE, driver, bench_page.SCRIPT_PATH], input=json.dumps(cases),
                                capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-800:])
    return json.loads(result.stdout)


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
    collected = bench.collect(LANES, epoch_csv=FIXTURE)
    html = bench_page.render(collected, LANES)
    record("page from epoch fixture",
           "claude-fable-5-1" in html and "DeepSWE" in html and "98.0" in html
           and "<table" in html and "Read-only" in html,
           html[:400])
    record("the page loads nothing remote, and its one script is inline",
           remote_resource(html) is None and "<style>" in html
           and not re.search(r"<script[^>]*\bsrc\s*=", html, re.I)
           and "<link" not in html.lower() and html.count("<script>") == 1,
           html[:200])
except Exception as e:
    record("page from epoch fixture", False, repr(e))

try:
    html = bench_page.render(None, LANES)
    record("page with bench=None names missing data",
           "Benchmark collection data is missing" in html
           and "Per-effort data is missing" in html
           and data_of(html) is None,
           html[:400])
except Exception as e:
    record("page with bench=None names missing data", False, repr(e))

try:
    collected = bench.collect(LANES, epoch_csv=FIXTURE)
    html = bench_page.render(collected, LANES, EFFORT_ROWS)
    record("page with per-effort rows carries every number and its provenance",
           "unlabelled" in html and "SWE Refactor Bench" in html and "uncertain" in html
           and "19.0" in html and "$9.1" in html and "2026-09-10" in html
           and "example.invalid/leaderboard" in html and "gpt-5.6-sol" in html,
           html[:400])
    record("effort page loads nothing remote", remote_resource(html) is None)
except Exception as e:
    record("page with per-effort rows carries every number and its provenance", False, repr(e))

try:
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "bench.html")
        collected = bench.collect(LANES, epoch_csv=FIXTURE)
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

try:
    collected = bench.collect(copy.deepcopy(ASTRA), epoch_csv=FIXTURE)
    page = bench_page.render(collected, ASTRA, SWEEP)

    def inside_details(index):
        before = page[:index]
        return len(re.findall(r"<details\b", before)) > before.count("</details>")

    # The comparison of boards (ticket 25) is the key to the plots, not
    # evidence, so it is the one table left open, between the plots and the
    # collapsed evidence.
    tables = [m.start() for m in re.finditer(r"<table\b", page) if not page.startswith('<table class="compare"', m.start())]
    kinds = set(re.findall(r'<table class="(\w+)"', page))
    compare = page.find('<table class="compare"')
    record("every evidence table is collapsed until asked for, under the plots and the board comparison",
           kinds == {"sweep", "rows", "catalog", "scores", "compare"}
           and all(inside_details(i) for i in tables)
           and not inside_details(compare)
           and not re.search(r"<details[^>]*\bopen\b", page)
           and page.find('id="plots"') < compare < page.find("<details"),
           f"kinds={kinds} tables={len(tables)}")
except Exception as e:
    record("every table is collapsed until asked for, under the plots", False, repr(e))

try:
    hostile = dict(SWEEP[5], model='</script><script>alert(1)</script> & "GLM"')
    page = bench_page.render(None, ASTRA, [hostile])
    data = data_of(page)
    record("a model name from a benchmark page cannot end the data's script element",
           data is not None and data["boards"][0]["points"][0]["name"] == hostile["model"]
           and "<script>alert" not in page,
           page[page.find("bench-data"):][:300])
except Exception as e:
    record("a model name from a benchmark page cannot end the data's script element", False, repr(e))


# --- the plot data ------------------------------------------------------------------
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
        # weak: drawn dashed and hollow, and named weak in the table
        {"source": "t", "model": "m-c", "effort": "low", "benchmark": "B1",
         "score": 9.0, "cost_usd": 9.0, "uncertain": True},
        # cannot be placed on a log axis; listed as not drawn
        {"source": "t", "model": "m-d", "effort": "low", "benchmark": "B1",
         "score": 9.0, "cost_usd": 0, "uncertain": False},
    ]
    page = bench_page.render(None, LANES, rows)
    data = data_of(page)
    boards = {(r["source"], r["benchmark"]) for r in rows}
    seen = {(b["source"], b["benchmark"]) for b in data["boards"]}
    t_b1 = next(b for b in data["boards"] if (b["source"], b["benchmark"]) == ("t", "B1"))
    weak = [p for b in data["boards"] for p in b["points"] if p["weak"]]
    record("one board per source and benchmark, never two sources on one cost axis",
           len(data["boards"]) == len(boards) and seen == boards
           and t_b1["unplotted"] == ["m-d low"]
           and [p["plotted"] for p in t_b1["points"] if p["name"] == "m-d"] == [False]
           and [p["name"] for p in weak] == ["m-c"]
           and "a dollar on one board is not a dollar on another" in page,
           f"boards={seen} unplotted={t_b1['unplotted']} weak={weak}")
except Exception as e:
    record("one board per source and benchmark, never two sources on one cost axis", False, repr(e))

try:
    page = bench_page.render(None, LANES, [])
    record("the plot section says so when there are no rows",
           "No per-effort rows" in page and data_of(page) is None)
    page = bench_page.render(None, LANES, [{"source": "t", "model": "m", "effort": "low",
                                            "benchmark": "B", "score": 1, "cost_usd": 0}])
    record("a board with nothing drawable says so and still tables the row",
           "nothing to draw" in page and "<td>low</td>" in page
           and data_of(page)["boards"][0]["finding"].startswith("No row on this board"))
except Exception as e:
    record("the plot section says so when there are no rows", False, repr(e))

try:
    data = bench_page.plot_data(SWEEP, ASTRA)
    points = board_named(data, "Terminal-Bench 4.0")["points"]
    kinds = {}
    for p in points:
        kinds.setdefault(p["kind"], []).append(p)
    lane = next(p for p in points if p["kind"] == "lane")
    page = bench_page.render(None, ASTRA, SWEEP)
    record("a lane, a proposed-off lane, our model at another effort and a comparator "
           "are each their own kind, and a lane point carries its harness and tier",
           {k: len(v) for k, v in kinds.items()} == {"lane": 4, "lane_off": 1, "own_other": 1, "comparator": 2}
           and lane["harness"] == ["codex"] and lane["tier"] == ASTRA["lanes"][lane["lanes"][0]["name"]]["tier"]
           and all(p["harness"] == [] and not p["ours"] for p in kinds["comparator"])
           and kinds["own_other"][0]["harness"] == ["codex"] and kinds["own_other"][0]["lanes"] == []
           and data["harnesses"] == sorted({l["harness"] for l in ASTRA["lanes"].values()})
           and bench_page.NO_LANE in page,
           f"kinds={ {k: len(v) for k, v in kinds.items()} } lane={lane}")
except Exception as e:
    record("a lane, a proposed-off lane, our model at another effort and a comparator "
           "are each their own kind, and a lane point carries its harness and tier", False, repr(e))

# --- the page is the evidence for the pre-screen, so it has to say the same -----
try:
    page = bench_page.render(None, ASTRA, SWEEP)
    proposals = setup_tui.propose_enabled(ASTRA, SWEEP)
    off = sorted(name for name, (on, _why) in proposals.items()
                 if not on and setup_tui.is_dominated_reason(_why))
    struck = [p for p in board_named(data_of(page), "Terminal-Bench 4.0")["points"] if p["kind"] == "lane_off"]
    verdict = re.search(r'<p class="verdict">(.*?)</p>', page, re.S).group(1)
    finding = board_named(data_of(page), "Terminal-Bench 4.0")["finding"]
    body = page[page.find('<table class="sweep">'):]
    order = re.findall(r"<td>(low|medium|high|xhigh|max)</td><td>", body)
    record("the page marks what the wizard marks, names it at the top, and shows the arithmetic",
           off == ["astra-xhigh@codex"] and len(struck) == 1 and struck[0]["effort"] == "xhigh"
           and struck[0]["off"] == "high wins on tbench" and struck[0]["beatenBy"] == "high"
           and "astra-xhigh@codex" in verdict and "high wins on tbench" in verdict
           and "scores the same as high" in finding and "$81.1 more (+4%)" in finding
           and f'<p class="finding">{finding}</p>' in page
           and "off: high wins on tbench" in body
           # efforts most to least, and each step is still what the effort
           # buys over the one below it (ticket 26 replaced the ascending order)
           and order[:5] == ["max", "xhigh", "high", "medium", "low"]
           and "GPT-6 Astra" in page and "gpt-6-astra" in page,
           f"off={off} struck={struck} verdict={verdict[:120]!r} order={order[:6]}")
except Exception as e:
    record("the page marks what the wizard marks, names it at the top, and shows the arithmetic",
           False, repr(e))

try:
    # One source, three benchmarks off the same runs. medium beats high on two
    # of the three, so the wizard switches high off over the source, and the page
    # has to say so on every one of that source's boards — including b3, where
    # high happens to score more.
    luna = copy.deepcopy(LANES)
    for effort in ("low", "medium", "high"):
        lane = copy.deepcopy(LANES["lanes"]["sol-high@codex"])
        lane["model"] = "gpt-5.6-luna"
        lane["effort"] = effort
        luna["lanes"][f"luna-{effort}@codex"] = lane
    board = []
    for bench_name, points in (("b1", (0.6, 0.5)), ("b2", (0.6, 0.5)), ("b3", (0.4, 0.5))):
        for effort, score, cost in (("medium", points[0], 1.0), ("high", points[1], 2.0)):
            board.append({"source": "aa", "model": "gpt-5.6-luna", "effort": effort,
                          "benchmark": bench_name, "score": score, "cost_usd": cost,
                          "uncertain": False, "provenance": "unlabelled"})
    every = [p for b in bench_page.plot_data(board, luna)["boards"] for p in b["points"]]
    struck = [p for p in every if p["kind"] == "lane_off"]
    kept = [p for p in every if p["kind"] == "lane"]
    record("a lane dominated over its source is struck on every board of that source",
           len(struck) == 3 and all(p["beatenBy"] == "medium" and p["effort"] == "high" for p in struck)
           and len(kept) == 3 and not any(p["beatenBy"] for p in kept),
           f"struck={struck} kept={kept}")
except Exception as e:
    record("a lane dominated over its source is struck on every board of that source",
           False, repr(e))

try:
    page = bench_page.render(None, ASTRA, SWEEP)
    start = page.find('<table class="sweep">')
    body = page[start:page.find("</table>", start)]
    cells = re.findall(r'<td class="num step">([^<]*)</td>', body)
    record("the sweep table gives each step's score and cost delta",
           "+3.6%" in cells and "0.0%" in cells
           and any(c.startswith("+$81.1") and "(+4%)" in c for c in cells)
           and any(c.startswith("+$917") and "(+39%)" in c for c in cells),
           f"cells={cells}")
except Exception as e:
    record("the sweep table gives each step's score and cost delta", False, repr(e))

try:
    # self-reported rows still count in the wizard's rule; uncertain never do.
    # Either way the figure must not look verified.
    rows = [dict(SWEEP[2], provenance="self-reported"), dict(SWEEP[3])]
    page = bench_page.render(None, ASTRA, rows)
    weak = [p for p in data_of(page)["boards"][0]["points"] if p["weak"]]
    body = page[page.find('<table class="sweep">'):]
    record("a weakly-sourced figure is marked weak and flagged in the table",
           len(weak) == 1 and weak[0]["provenance"] == "self-reported" and weak[0]["kind"] == "lane"
           and 'class="flag">self-reported' in body
           and 'class="lane weak' in body,
           f"weak={weak}")
except Exception as e:
    record("a weakly-sourced figure is marked weak and flagged in the table", False, repr(e))

try:
    # a board where a carried lane is measured at its own effort comes before
    # one that only has our models at efforts no lane runs, and the page opens
    # on it and on the best board from another source
    other = [{"source": "swerb", "model": "gpt-5.6-sol", "effort": e, "benchmark": "SWE Refactor Bench",
              "score": s, "cost_usd": c, "uncertain": False}
             for e, s, c in (("low", 7.0, 5.9), ("medium", 6.5, 6.0), ("xhigh", 9.5, 19.1), ("max", 28.5, 143.5))]
    page = bench_page.render(None, ASTRA, other + SWEEP)
    data = data_of(page)
    names = {b["id"]: b["benchmark"] for b in data["boards"]}
    record("the board with carried lanes measured at their effort comes first, and the page "
           "opens on it and on another source",
           [names[i] for i in data["defaults"]] == ["Terminal-Bench 4.0", "SWE Refactor Bench"]
           and page.find("Terminal-Bench 4.0 <span") < page.find("SWE Refactor Bench <span") != -1,
           f"defaults={[names[i] for i in data['defaults']]}")
    # one source, two boards with the same lanes on them: the composite index
    # opens first, because it is the board that reads best at a glance
    index = [dict(r, benchmark="Index", composite=True, source="aa") for r in SWEEP[:5]]
    parts = [dict(r, benchmark="A part", source="aa") for r in SWEEP[:5]]
    data = bench_page.plot_data(parts + index, ASTRA)
    record("among boards that tie on lanes, the composite index opens first",
           [data["boards"][0]["benchmark"], data["boards"][0]["composite"]] == ["Index", True]
           and [b["benchmark"] for b in data["boards"]] == ["Index", "A part"]
           and data["defaults"] == ["b0", "b1"],
           f"boards={[b['benchmark'] for b in data['boards']]} defaults={data['defaults']}")
except Exception as e:
    record("the board with carried lanes measured at their effort comes first, and the page "
           "opens on it and on another source", False, repr(e))


# --- the trap: a per-model score is never a lane's score by default --------------
try:
    collected = bench.collect(copy.deepcopy(ASTRA), epoch_csv=FIXTURE)
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
    collected = bench.collect(LANES, epoch_csv=FIXTURE)
    doctored = copy.deepcopy(collected)
    # the source stated no effort: `unknown` is the cell's key, not a value
    cell = doctored["models"]["gpt-5.6-sol"]["epoch"]["cells"]["DeepSWE"]
    doctored["models"]["gpt-5.6-sol"]["epoch"]["cells"]["DeepSWE"] = {
        bench.UNKNOWN_EFFORT: dict(cell[next(iter(cell))])}
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
    collected = bench.collect(LANES, epoch_csv=FIXTURE)
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
    at = table.find("gpt-5.6-sol")
    row = table[table.rfind("<tr", 0, at):table.find("</tr>", at)]  # from <tr>, so td 0 is the model
    tds = re.findall(r"<td[^>]*>.*?</td>", row, re.S)
    deepswe, frontier, aa_cell = tds[2], tds[3], tds[-1]
    record("the post-fix cell shape reads: every effort's figure shown, most effort first, "
           "each attributed on its own, and the AA effort attributed too",
           deepswe.count('<span class="fig') == 3
           # most to least, an unstated effort last (ticket 26 replaced the ascending order)
           and re.findall(r'<span class="at">([^<]*)</span>', deepswe)
           == ["at max, not carried", "at high", "effort not stated"]
           and deepswe.count('class="fig attributed"') == 1 and 'title="sol-high@codex"' in deepswe
           and frontier.count('class="fig unattributed"') == 1 and "at xhigh, not carried" in frontier
           and 'class="fig attributed" title="sol-high@codex">61<span class="at">at high' in aa_cell
           and "Artificial Analysis</th>" in table,
           f"deepswe={deepswe!r} frontier={frontier!r} aa={aa_cell!r}")
except Exception as e:
    record("the post-fix cell shape reads: every effort's figure shown, in effort order, "
           "each attributed on its own, and the AA effort attributed too", False, repr(e))


# --- comparators are context -------------------------------------------------------
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


# --- the script's frontier and layout, under node ------------------------------------
def lane_point(name, effort, score, cost, lanes=True, model=None):
    return {"model": model or name, "name": name, "published": name, "ours": lanes, "effort": effort,
            "score": score, "cost": cost, "plotted": True, "kind": "lane" if lanes else "comparator",
            "weak": False, "lanes": [{"name": f"{name}-{effort}@codex", "harness": "codex", "tier": 1}] if lanes else [],
            "harness": ["codex"] if lanes else [], "tier": 1 if lanes else None, "off": None,
            "beatenBy": None, "provenance": "unlabelled", "observed": None}


try:
    toy = {"id": "b0", "benchmark": "toy", "unit": None, "points": [
        lane_point("a", "low", 10.0, 1.0), lane_point("b", "low", 20.0, 2.0),
        lane_point("c", "low", 15.0, 3.0),
        # the same score as b for more money: beaten, so not on the frontier
        lane_point("d", "low", 20.0, 4.0),
        lane_point("e", "max", 30.0, 5.0, lanes=False)]}
    runs = run_layout([{"board": toy, "state": {"frontier": "lanes"}},
                       {"board": toy, "state": {"frontier": "shown"}},
                       {"board": toy, "state": {"frontier": "lanes", "hiddenModels": ["b"]}},
                       {"board": toy, "state": {"frontier": "shown", "hiddenHarness": ["none"]}},
                       {"board": toy, "state": {"frontier": "off"}}])
    if runs is None:
        record("the frontier is every point that scores more than everything cheaper", True,
               "(node not on PATH; skipped)")
    else:
        got = [r["frontier"] for r in runs["out"]]
        record("the frontier is every point that scores more than everything cheaper, "
               "over what is shown",
               got == [["a low", "b low"], ["a low", "b low", "e max"],
                       ["a low", "c low", "d low"], ["a low", "b low"], []],
               f"got={got}")
except Exception as e:
    record("the frontier is every point that scores more than everything cheaper", False, repr(e))

try:
    fractions = {"id": "b0", "benchmark": "fr", "unit": None,
                 "points": [lane_point("a", "low", 0.62, 1.0), lane_point("b", "low", 0.88, 3.0)]}
    board = board_named(bench_page.plot_data(SWEEP, ASTRA), "Terminal-Bench 4.0")
    runs = run_layout([{"board": board, "state": {"labels": "all"}},
                       {"board": fractions, "state": {}}])
    if runs is None:
        record("no two labels overprint, every point is inside the frame, and a tick is a dollar", True,
               "(node not on PATH; skipped)")
    else:
        W, H, PAD = runs["W"], runs["H"], runs["PAD"]
        sweep, frac = runs["out"]
        inside = all(PAD["l"] <= x <= W - PAD["r"] and PAD["t"] <= y <= H - PAD["b"] for x, y in sweep["points"])
        framed = all(PAD["l"] <= l["box"][0] and l["box"][2] <= W - PAD["r"] and PAD["t"] <= l["box"][1]
                     and l["box"][3] <= H - PAD["b"] for l in sweep["labels"])
        record("no two labels overprint, every point is inside the frame, and a tick is a dollar",
               not overlaps(sweep["labels"]) and inside and framed and len(sweep["labels"]) >= 5
               and sweep["xTicks"] and all(t.startswith("$") and "e" not in t for t in sweep["xTicks"]),
               f"labels={[l['text'] for l in sweep['labels']]} ticks={sweep['xTicks']}")
        record("the score axis fits the points shown, not zero",
               float(frac["yTicks"][0]) >= 0.5 and float(frac["yTicks"][-1]) <= 1.0,
               f"yTicks={frac['yTicks']}")
except Exception as e:
    record("no two labels overprint, every point is inside the frame, and a tick is a dollar",
           False, repr(e))

try:
    real = [os.path.join(REAL_DATA, f) for f in ("aa-accepted.json", "tbench-accepted.json", "swerb-accepted.json")]
    if all(os.path.isfile(p) for p in real) and NODE:
        rows = []
        for p in real:
            with open(p, encoding="utf-8") as f:
                rows.extend(json.load(f))
        lanes = catalog.load_json(STOWED_LANES)
        data = data_of(bench_page.render(None, lanes, rows))
        runs = run_layout([{"board": b, "state": {"labels": "all", "frontier": mode}}
                           for b in data["boards"] for mode in ("lanes", "shown")])
        clashes = [overlaps(r["labels"]) for r in runs["out"]]
        record("the real data draws every board with no overprinted label",
               len(data["boards"]) >= 11 and not any(clashes)
               and all(r["frontier"] for r in runs["out"]),
               f"boards={len(data['boards'])} clashes={[c for c in clashes if c][:2]}")
    else:
        record("the real data draws every board with no overprinted label", True,
               "(real data or node not present; skipped)")
except Exception as e:
    record("the real data draws every board with no overprinted label", False, repr(e))


# --- ticket 25: what each board measures, and zoom --------------------------------
import effort  # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures")


def every_known_row():
    """The AA rows off the fixture page, the Terminal-Bench fixture, and the
    swerb rows when the real data is present: one row set per approved source."""
    with open(os.path.join(FIXTURES, "real_aa_model_page_sample.html"), "rb") as f:
        _packet, rows = effort.aa_extract(f.read(), observed="2026-09-11")
    with open(os.path.join(FIXTURES, "tbench-accepted.json"), encoding="utf-8") as f:
        rows = rows + json.load(f)
    for name in ("aa-accepted.json", "tbench-accepted.json", "swerb-accepted.json"):
        path = os.path.join(REAL_DATA, name)
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                rows = rows + json.load(f)
    return rows


try:
    rows = every_known_row()
    data = bench_page.plot_data(rows, catalog.load_json(STOWED_LANES) if os.path.isfile(STOWED_LANES) else LANES)
    missing = [(b["source"], b["benchmark"]) for b in data["boards"]
               if not b["about"] or not b["about"]["measures"] or not b["about"]["url"]
               or not b["about"]["url"].startswith("https://")]
    sources = {b["source"] for b in data["boards"]}
    record("every board on the page has a description and a source URL",
           not missing and {"aa", "tbench"} <= sources and len(data["boards"]) >= 10
           and all(b["aboutMissing"] is None for b in data["boards"]),
           f"missing={missing} sources={sources}")
    with open(bench_page.BOARDS_PATH, encoding="utf-8") as f:
        described = json.load(f)["boards"]
    cited = [(s, n) for s, boards in described.items() for n, e in boards.items()
             if not (e.get("url") and e.get("fetched") and e.get("measures") and e.get("score"))]
    record("every description on file names its page and the day it was fetched",
           not cited, repr(cited))
except Exception as e:
    record("every board on the page has a description and a source URL", False, repr(e))

try:
    page = bench_page.render(None, ASTRA, SWEEP + [dict(SWEEP[0], source="t", benchmark="Nobody's board")])
    data = data_of(page)
    tb = board_named(data, "Terminal-Bench 4.0")
    stranger = board_named(data, "Nobody's board")
    compare = page[page.find('<table class="compare"'):]
    compare = compare[:compare.find("</table>")]
    record("a board with no methodology page on file says so, and never borrows a description",
           tb["about"]["url"].startswith("https://") and "terminal" in tb["about"]["measures"]
           and stranger["about"] is None and stranger["aboutMissing"] == bench_page.NO_ABOUT
           and bench_page.board_about("t", "Nobody's board") is None,
           f"tb={tb['about']} stranger={stranger['about']}")
    record("the comparison table lists every board with what it measures, scale and cost basis",
           compare.count("<tr>") == len(data["boards"]) + 1
           and all(_h in compare for _h in ("what it measures", "scale", "cost basis"))
           and tb["about"]["measures"].replace("'", "&#x27;") in compare
           and "whole run" in compare and bench_page._esc(bench_page.NO_ABOUT) in compare,
           compare[:600])
except Exception as e:
    record("a board with no methodology page on file says so, and never borrows a description",
           False, repr(e))

try:
    script = open(bench_page.SCRIPT_PATH, encoding="utf-8").read()
    record("selecting a board redraws its description, and the reset button is never hidden",
           "drawAbout(board)" in script and "reset.hidden" not in script
           and '"wheel"' in script and "passive: false" in script)
except Exception as e:
    record("selecting a board redraws its description, and the reset button is never hidden", False, repr(e))

ZOOM_DRIVER = r"""
const fs = require("fs"), vm = require("vm");
const mod = { exports: {} };
vm.runInNewContext(fs.readFileSync(process.argv[2], "utf8"), { module: mod });
const P = mod.exports;
const d = { xlo: 1, xhi: 1000, ylo: 0, yhi: 100 };
const p = { x0: P.PAD.l, x1: P.W - P.PAD.r, y0: P.PAD.t, y1: P.H - P.PAD.b };
const x = p.x0 + 0.3 * (p.x1 - p.x0), y = p.y0 + 0.6 * (p.y1 - p.y0);
const at = (dom) => [Math.log10(dom.xlo) + 0.3 * (Math.log10(dom.xhi) - Math.log10(dom.xlo)),
                     dom.yhi - 0.6 * (dom.yhi - dom.ylo)];
const zin = P.zoomAbout(d, p, x, y, 0.5), zout = P.zoomAbout(d, p, x, y, 2);
const asDomain = (z) => ({ xlo: z.c0, xhi: z.c1, ylo: z.s0, yhi: z.s1 });
process.stdout.write(JSON.stringify({ before: at(d), after: at(asDomain(zin)),
  spanIn: [Math.log10(zin.c1 / zin.c0), zin.s1 - zin.s0], coversIn: P.covers(zin, d), coversOut: P.covers(zout, d) }));
"""

try:
    if not NODE:
        record("the wheel zooms about the pointer, and zooming out past the full view is the full view", True,
               "(node not on PATH; skipped)")
    else:
        with tempfile.TemporaryDirectory() as td:
            driver = os.path.join(td, "zoom.js")
            with open(driver, "w", encoding="utf-8") as f:
                f.write(ZOOM_DRIVER)
            out = json.loads(subprocess.run([NODE, driver, bench_page.SCRIPT_PATH], capture_output=True,
                                            text=True, timeout=60, check=True).stdout)
        same = all(abs(a - b) < 1e-9 for a, b in zip(out["before"], out["after"]))
        record("the wheel zooms about the pointer, and zooming out past the full view is the full view",
               same and abs(out["spanIn"][0] - 1.5) < 1e-9 and abs(out["spanIn"][1] - 50) < 1e-9
               and not out["coversIn"] and out["coversOut"], repr(out))
except Exception as e:
    record("the wheel zooms about the pointer, and zooming out past the full view is the full view", False, repr(e))


# --- ticket 26: the page is where tiers are drawn ------------------------------------
try:
    collected = bench.collect(copy.deepcopy(ASTRA), epoch_csv=FIXTURE)
    doc = copy.deepcopy(ASTRA)
    doc["lanes"]["astra-ultra@codex"] = dict(doc["lanes"]["astra-max@codex"], effort="ultra", enabled=False)
    page = bench_page.render(collected, doc, SWEEP)
    data = data_of(page)
    lanes = data["lanes"]
    by_name = {l["name"]: l for l in lanes}
    astra = [l["name"] for l in lanes if l["group"] == "gpt-6-astra"]
    groups = []
    for l in lanes:
        if not groups or groups[-1] != l["group"]:
            groups.append(l["group"])
    wizard = setup_tui.Wizard(copy.deepcopy(doc), {"classes": {}, "margin": 0, "gate": 0}, collected,
                              set(catalog.HARNESSES), "/tmp/l", "/tmp/r", effort_rows=SWEEP)
    record("the page lists every lane in the tier page's order, grouped by model, efforts most to least, "
           "and says which are carried, proposed off, or drawn nowhere",
           [l["name"] for l in lanes] == setup_tui.lane_order(doc, collected)
           and [l["name"] for l in lanes if l["carried"]] == [n for n in setup_tui.lane_order(doc, collected)
                                                                if wizard._enabled[n] or n == "astra-xhigh@codex"]
           and astra == ["astra-ultra@codex", "astra-max@codex", "astra-xhigh@codex", "astra-high@codex",
                         "astra-medium@codex", "astra-low@codex"]
           and len(groups) == len(set(groups))
           and by_name["astra-ultra@codex"]["carried"] is False
           and by_name["astra-xhigh@codex"]["carried"] is True
           and by_name["astra-xhigh@codex"]["off"] == "high wins on tbench"
           and by_name["astra-high@codex"]["off"] is None
           and by_name["astra-high@codex"]["rows"] is True
           # fable is on no board of this sweep, so it can be no dot
           and by_name["fable-xhigh@claude"]["rows"] is False
           and by_name["fable-xhigh@claude"]["carried"] is True
           and by_name["astra-high@codex"]["harness"] == "codex"
           and by_name["astra-high@codex"]["tier"] == doc["lanes"]["astra-high@codex"]["tier"]
           and set(lanes[0]) == {"name", "harness", "model", "group", "effort", "tier", "carried", "off", "rows"},
           repr(lanes[:3]))
    key = data["catalogKey"]
    other = copy.deepcopy(doc)
    other["lanes"]["extra-high@codex"] = copy.deepcopy(doc["lanes"]["astra-high@codex"])
    record("the page's tiers are keyed by the catalog, and the page says where they live",
           re.fullmatch(r"[0-9a-f]{12}", key) and bench_page.catalog_key(doc) == key
           and bench_page.catalog_key(other) != key
           and 'id="tiers"' in page and "stays in this browser" in page and "Read-only" in page
           and "Tiers are set in the wizard; nothing is entered here" not in page,
           repr(key))
    # every table: a model's efforts most to least
    cat = page[page.find('<table class="catalog">'):]
    cat = cat[:cat.find("</table>")]
    cat_names = re.findall(r'<td><span class="mono">([^<]*@[^<]*)</span></td>', cat)
    rows_block = page[page.find('<table class="rows">'):]
    rows_block = rows_block[:rows_block.find("</table>")]
    astra_rows = re.findall(r"<td><span class=mono>gpt-6-astra</span></td><td>(\w+)</td>", rows_block)
    record("the catalog and rows tables group by model with efforts most to least",
           [n for n in cat_names if n.startswith("astra-")] == astra
           and astra_rows == ["max", "xhigh", "high", "medium", "low"],
           repr((cat_names, astra_rows)))
except Exception as e:
    record("the page lists every lane in the tier page's order, grouped by model, efforts most to least, "
           "and says which are carried, proposed off, or drawn nowhere", False, repr(e))


TIER_DRIVER = r"""
const fs = require("fs"), vm = require("vm");
const mod = { exports: {} };
vm.runInNewContext(fs.readFileSync(process.argv[2], "utf8"), { module: mod });
const P = mod.exports;
const c = JSON.parse(fs.readFileSync(0, "utf8"));
const out = {};
// pan: the content follows the pointer, in log space on the cost axis
const d = { xlo: 1, xhi: 1000, ylo: 0, yhi: 100 };
const p = { x0: P.PAD.l, x1: P.W - P.PAD.r, y0: P.PAD.t, y1: P.H - P.PAD.b };
const half = (p.x1 - p.x0) / 2, quarter = (p.y1 - p.y0) / 4;
out.pan = P.panBy(d, p, half, quarter);
out.bands = [0.5, 1, 2, 4, 5].map((cost) => P.bandTier(cost, [1, 2, 4]));
out.noLines = P.bandTier(3, null);
out.defaults = P.defaultLines([0.1, 0.2, 5, 10]);
out.flat = P.defaultLines([2, 2, 2]);
const lanes = c.lanes.map((l, rank) => Object.assign({ rank }, l));
out.grouped = P.groupLanes(c.ordered.map((name) => lanes.find((l) => l.name === name))).map((l) => l.name);
out.review = P.reviewOrder(lanes, c.tiers).map((l) => l.name);
out.text = P.tierLinesText(lanes, c.tiers);
// layout: the lines, the bands, the page's tiers and the focus
const st = { frontier: "lanes", labels: "lanes", lines: true, zoom: null, hiddenModels: new Set(),
             hiddenHarness: new Set(), hiddenEfforts: new Set(), tiers: c.pointTiers, tierLines: [12, 18, 25], focusTier: null };
const lay = P.layout(c.board, st);
out.lines = lay.lines.map((l) => [l.score, l.inside, Math.round(l.y)]);
out.bandNames = lay.bands.map((b) => b.tier);
out.pointTiers = lay.points.map((q) => [q.p.name, q.tier, q.band, q.dim]);
const focused = P.layout(c.board, Object.assign({}, st, { focusTier: 2 }));
out.dimmed = focused.points.map((q) => [q.p.name, q.dim]);
const zoom = P.focusDomain(c.board, st, 2);
out.focus = zoom && [zoom.s0 <= 12, zoom.s1 >= 18, zoom.s1 < 25, zoom.s0, zoom.s1];
out.focusNothing = P.focusDomain(c.board, Object.assign({}, st, { tierLines: null, tiers: {} }), 3);
process.stdout.write(JSON.stringify(out));
"""

try:
    if not NODE:
        record("the script pans, cuts bands, groups lanes as the wizard does, and focuses a tier", True,
               "(node not on PATH; skipped)")
    else:
        doc = copy.deepcopy(LANES)
        for effort in ("low", "medium", "high", "max"):
            lane = copy.deepcopy(LANES["lanes"]["fable-xhigh@claude"])
            lane["effort"] = effort
            doc["lanes"][f"fable-{effort}@claude"] = lane
        doc["lanes"]["flash-low@agy"] = dict(LANES["lanes"]["flash-high@agy"], model="gemini-3.8-flash-low", effort="low")
        lanes = [{"name": n, "group": setup_tui.model_group(doc["lanes"][n]), "effort": doc["lanes"][n]["effort"]}
                 for n in sorted(doc["lanes"])]
        ordered = ["fable-low@claude", "sol-high@codex", "fable-max@claude", "flash-high@agy", "flash-low@agy"]
        tiers = {"sol-high@codex": 4, "fable-low@claude": 3, "fable-max@claude": 1, "flash-low@agy": 1}
        toy = {"id": "b0", "benchmark": "toy", "unit": None, "points": [
            lane_point("a", "low", 10.0, 1.0), lane_point("b", "low", 20.0, 2.0),
            lane_point("c", "low", 15.0, 3.0), lane_point("d", "max", 30.0, 4.0, lanes=False)]}
        point_tiers = {"a-low@codex": 1, "b-low@codex": 2, "c-low@codex": 2}
        with tempfile.TemporaryDirectory() as td:
            driver = os.path.join(td, "tiers.js")
            with open(driver, "w", encoding="utf-8") as f:
                f.write(TIER_DRIVER)
            case = json.dumps({"lanes": lanes, "ordered": ordered, "tiers": tiers, "board": toy, "pointTiers": point_tiers})
            result = subprocess.run([NODE, driver, bench_page.SCRIPT_PATH], input=case, capture_output=True,
                                    text=True, timeout=60)
            if result.returncode != 0:
                raise RuntimeError(result.stderr[-800:])
            out = json.loads(result.stdout)
        pan = out["pan"]
        # dragging right by half the width shows costs a half-decade and a half lower;
        # dragging down by a quarter of the height shows scores 25 higher
        record("a drag pans the content with the pointer, in log space on the cost axis",
               abs(pan["c0"] - 10 ** -1.5) < 1e-9 and abs(pan["c1"] - 10 ** 1.5) < 1e-9
               and abs(pan["s0"] - 25) < 1e-9 and abs(pan["s1"] - 125) < 1e-9, repr(pan))
        record("a band proposes one more than the lines at or below the score, and no lines propose nothing",
               out["bands"] == [1, 2, 3, 4, 4] and out["noLines"] is None
               and out["defaults"] == [2.575, 5.05, 7.525] and len(out["flat"]) == 3
               and out["flat"][0] < out["flat"][1] < out["flat"][2], repr((out["bands"], out["defaults"], out["flat"])))
        record("the script groups lanes exactly as setup_tui.group_lanes does, and the copy is in the review "
               "page's order",
               out["grouped"] == setup_tui.group_lanes(ordered, doc)
               and out["review"][0] == "sol-high@codex"
               and out["review"][1:6] == ["fable-max@claude", "fable-xhigh@claude", "fable-high@claude",
                                          "fable-medium@claude", "fable-low@claude"]
               and out["text"].splitlines() == ["sol-high@codex 4", "fable-max@claude 1", "fable-low@claude 3",
                                                "flash-low@agy 1"],
               repr((out["grouped"], out["review"], out["text"])))
        record("the layout places the tier lines, names each band, carries the page's tier and the band per "
               "point, and dims the points outside a focused tier",
               [l[0] for l in out["lines"]] == [12, 18, 25] and all(l[1] for l in out["lines"])
               and out["lines"][0][2] > out["lines"][1][2] > out["lines"][2][2]
               and out["bandNames"] == [1, 2, 3, 4]
               and sorted(out["pointTiers"]) == sorted([["d", None, 4, False], ["a", 1, 1, False],
                                                        ["b", 2, 3, False], ["c", 2, 2, False]])
               and sorted(out["dimmed"]) == sorted([["d", True], ["a", True], ["b", False], ["c", False]])
               and out["focus"] and out["focus"][:3] == [True, True, True]
               and out["focus"][3] <= 15.0 <= out["focus"][4] and out["focus"][3] <= 20.0 <= out["focus"][4]
               and out["focusNothing"] is None,
               repr((out["lines"], out["bandNames"], out["pointTiers"], out["dimmed"], out["focus"])))
        script = open(bench_page.SCRIPT_PATH, encoding="utf-8").read()
        record("the page's tiers live in localStorage under the catalog's key, are never sent anywhere, and "
               "digits set the selected lane",
               "localStorage" in script and "catalogKey" in script and "fetch(" not in script
               and "XMLHttpRequest" not in script and "lanes.json" not in script
               and "keydown" in script and "/^[1-4]$/" in script and "Copy as lines" in script)
except Exception as e:
    record("the script pans, cuts bands, groups lanes as the wizard does, and focuses a tier", False, repr(e))


# Round 2: automatic bands preserve hand assignments, including after reload.
try:
    driver = r"""
const assert = require('assert');
const P = require(process.argv[1]);
const board = {source:'aa', benchmark:'toy', points: [
  {plotted:true, score:0, lanes:[{name:'a'}]},
  {plotted:true, score:15, lanes:[{name:'b'}]},
  {plotted:true, score:30, lanes:[{name:'c'}]},
  {plotted:true, score:40, lanes:[{name:'off'}]}]};
const lanes = ['a','b','c','no-rows'].map(name => ({name,carried:true})).concat([{name:'off',carried:false}]);
const tiers = {b:4,'no-rows':2}, manual = {b:true};
P.applyBands(board,[10,20,25],lanes,tiers,manual);
assert.deepStrictEqual(tiers,{a:1,b:4,c:4,'no-rows':2});
P.applyBands(board,[-5,5,35],lanes,tiers,manual);
assert.deepStrictEqual(tiers,{a:2,b:4,c:3,'no-rows':2});
delete manual.b;
P.applyBands(board,[-5,5,35],lanes,tiers,manual);
assert.strictEqual(tiers.b,3);
let saved = {tiers:{a:4},lines:{aa:[1,2,3]}};
global.localStorage = {getItem:()=>JSON.stringify(saved),setItem:(k,v)=>{saved=JSON.parse(v)}};
let store = P.makeStore({catalogKey:'fixture',lanes,boards:[board]});
assert.strictEqual(store.manual.a,true);
assert.deepStrictEqual(store.lines,{});
store.lines[P.boardKey(board)] = [-5,0,5]; store.save();
store = P.makeStore({catalogKey:'fixture',lanes,boards:[board]});
assert.deepStrictEqual(store.lines[P.boardKey(board)],[-5,0,5]);
assert.strictEqual(store.manual.a,true);
"""
    result = subprocess.run([NODE, "-e", driver, os.path.abspath(bench_page.SCRIPT_PATH)], capture_output=True, text=True)
    record("score bands preserve overrides, clear releases them, and reload migrates cost lines safely",
           result.returncode == 0, result.stderr)
except Exception as e:
    record("score bands preserve overrides, clear releases them, and reload migrates cost lines safely", False, repr(e))

sys.exit(1 if fails else 0)
