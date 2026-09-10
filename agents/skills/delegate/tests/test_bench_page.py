#!/usr/bin/env python3
"""Tests for bench_page.py. Run: python3 tests/test_bench_page.py"""
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DELEGATE_DIR = os.path.abspath(os.path.join(HERE, "..", "scripts"))
FIXTURE = os.path.join(HERE, "fixture", "bench-epoch.csv")
sys.path.insert(0, DELEGATE_DIR)

import bench
import bench_page
import catalog

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
    return re.search(r"""(?:src|href)\s*=\s*['"]https?://""", html, re.I)


EFFORT_ROWS = [
    {
        "source": "swerb",
        "url": "https://example.invalid/leaderboard/",
        "model": "gpt-5.6-sol",
        "effort": "high",
        "benchmark": "SWE Refactor Bench",
        "score": 19.0,
        "cost_usd": 9.1,
        "observed": "2026-09-10",
        "provenance": "unlabelled",
        "uncertain": False,
    },
    {
        "source": "aa",
        "url": "https://example.invalid/models/",
        "model": "gpt-5.6-sol",
        "effort": "low",
        "benchmark": "SWE-Bench verified",
        "score": 4.0,
        "cost_usd": 1.2,
        "observed": "2026-09-10",
        "provenance": "unlabelled",
        "uncertain": True,
    },
]


try:
    collected = bench.collect(LANES, epoch_csv=FIXTURE, key_file=None)
    html = bench_page.render(collected, LANES)
    record("page from epoch fixture",
           "claude-fable-5-1" in html
           and "DeepSWE" in html
           and "98.0" in html
           and "<table>" in html
           and "Read-only" in html,
           html[:400])
    record("fixture page has no remote stylesheet or script",
           remote_resource(html) is None
           and "<style>" in html
           and "<link" not in html.lower(),
           html[:200])
except Exception as e:
    record("page from epoch fixture", False, repr(e))

try:
    html = bench_page.render(None, LANES)
    record("page with bench=None names missing data",
           "Benchmark collection data is missing" in html
           and "Per-effort data is missing" in html
           and "Epoch benchmarks" not in html,
           html[:400])
except Exception as e:
    record("page with bench=None names missing data", False, repr(e))

try:
    collected = bench.collect(LANES, epoch_csv=FIXTURE, key_file=None)
    html = bench_page.render(collected, LANES, EFFORT_ROWS)
    sol_high = html.find("gpt-5.6-sol")
    record("page with per-effort rows",
           "unlabelled" in html
           and "SWE Refactor Bench" in html
           and "uncertain" in html
           and "19.0" in html
           and "9.1" in html
           and "2026-09-10" in html
           and sol_high != -1,
           html[html.find("Per-effort"):html.find("Per-effort") + 500] if "Per-effort" in html else html[:400])
    record("effort page has no remote stylesheet or script",
           remote_resource(html) is None)
except Exception as e:
    record("page with per-effort rows", False, repr(e))

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
    import re
    import xml.etree.ElementTree as ET

    rows = [
        {"source": "t", "model": "m-a", "effort": "low", "benchmark": "B1",
         "score": 10.0, "cost_usd": 1.0, "uncertain": False},
        {"source": "t", "model": "m-a", "effort": "high", "benchmark": "B1",
         "score": 20.0, "cost_usd": 2.0, "uncertain": False},
        {"source": "t", "model": "m-b", "effort": "low", "benchmark": "B2",
         "score": 5.0, "cost_usd": 3.0, "uncertain": False},
        # a model a lane does run, on one effort: nothing to compare either,
        # but for a different reason, and the two must not read as one
        {"source": "t", "model": "gpt-5.6-sol", "effort": "high", "benchmark": "B1",
         "score": 7.0, "cost_usd": 4.0, "uncertain": False},
        # excluded: uncertain, and a zero cost that cannot be placed on the axis
        {"source": "t", "model": "m-c", "effort": "low", "benchmark": "B1",
         "score": 9.0, "cost_usd": 9.0, "uncertain": True},
        {"source": "t", "model": "m-d", "effort": "low", "benchmark": "B1",
         "score": 9.0, "cost_usd": 0, "uncertain": False},
    ]
    page = bench_page.render(None, LANES, rows)
    svgs = re.findall(r"<svg.*?</svg>", page, re.S)
    for svg in svgs:
        ET.fromstring(svg)          # raises if the markup is malformed
    points = page.count("<circle")
    ok = (
        # one panel per model and benchmark, and only where two efforts can be
        # compared: m-a low/high on B1 is a comparison, m-b's single row is not
        len(svgs) == 1
        and points == 2                     # uncertain and zero-cost rows dropped
        # m-b is nobody's lane; sol is a lane on one effort. Different lines.
        and "No lane runs these" in page and "m-b" in page
        and "on one effort only" in page and "gpt-5.6-sol" in page
        and "dominates" in page
        and "cost is not comparable" in page
    )
    record("plot draws one well-formed svg per model that can show domination",
           ok, f"svgs={len(svgs)} points={points}")
except Exception as e:
    record("plot draws one well-formed svg per model that can show domination",
           False, repr(e))


try:
    page = bench_page.render(None, LANES, [])
    record("plot says so when no row carries both a score and a cost",
           "nothing to plot" in page and "<svg" not in page)
except Exception as e:
    record("plot says so when no row carries both a score and a cost", False, repr(e))


# --- the page is the evidence for the pre-screen, so it has to say the same ---
try:
    import setup_tui

    astra = catalog.load_json(os.path.abspath(
        os.path.join(HERE, "..", "assets", "samples", "lanes.json")))
    import copy as _copy
    for effort in ("low", "medium", "high", "xhigh", "max"):
        lane = _copy.deepcopy(astra["lanes"]["sol-high@codex"])
        lane["model"] = "gpt-6-astra"
        lane["effort"] = effort
        astra["lanes"][f"astra-{effort}@codex"] = lane
    sweep = []
    for effort, score, cost in (("low", 50.61, 1557.3), ("medium", 54.24, 1914.8),
                                ("high", 57.88, 2269.42), ("xhigh", 57.88, 2350.51),
                                ("max", 58.18, 3267.18)):
        sweep.append({"source": "tbench", "model": "GPT-6 Astra", "effort": effort,
                      "benchmark": "Terminal-Bench 4.0", "score": score,
                      "cost_usd": cost, "uncertain": False, "observed": "2026-09-03",
                      "provenance": "unlabelled"})
    sweep.append({"source": "tbench", "model": "GLM-5.3", "effort": "max",
                  "benchmark": "Terminal-Bench 4.0", "score": 41.82, "cost_usd": 2727.63,
                  "uncertain": False, "observed": "2026-08-14", "provenance": "unlabelled"})
    page = bench_page.render(None, astra, sweep)

    # ticket 16: the published name and the lane model it denotes, side by side
    bridged = ("GPT-6 Astra" in page and "gpt-6-astra" in page
               and 'class="nolane"' in page and bench_page.NO_LANE in page)

    # the hollow point is the one the wizard switched off, by the wizard's rule
    proposals = setup_tui.propose_enabled(astra, sweep)
    off = sorted(name for name, (on, _why) in proposals.items() if not on)
    hollow = re.findall(r'<circle[^>]*fill="#ffffff"[^>]*><title>([^<]*)</title>', page)
    same_rule = off == ["astra-xhigh@codex"] and len(hollow) == 1 and "xhigh" in hollow[0]

    # the sweep reads in effort order, and `max` is not filed after `none`
    body = page[page.find("Per-effort scores"):]
    # the effort cell is the one followed by the score; `dominated by` also
    # holds an effort name and must not be counted as one
    order = re.findall(r'<td>(low|medium|high|xhigh|max)</td><td class="num">', body)
    record("the page names both models, marks what the wizard marks, in effort order",
           bridged and same_rule
           and order[:5] == ["low", "medium", "high", "xhigh", "max"]
           and "dominated by" in page,
           f"bridged={bridged} same_rule={same_rule} off={off} hollow={hollow} order={order[:6]}")
except Exception as e:
    record("the page names both models, marks what the wizard marks, in effort order",
           False, repr(e))

try:
    # the pair the panel exists to show sat five pixels apart with its two
    # labels printed over each other, on an axis spanning every model's cost
    svg = re.search(r"<svg.*?</svg>", page, re.S).group(0)
    circles = [(float(a), float(b)) for a, b in
               re.findall(r'<circle cx="([\d.]+)" cy="([\d.]+)"', svg)]
    closest = min(((cx - dx) ** 2 + (cy - dy) ** 2) ** 0.5
                  for i, (cx, cy) in enumerate(circles)
                  for dx, dy in circles[i + 1:])
    labels = []
    for lx, ly, anchor, text in re.findall(
            r'<text x="([\d.-]+)" y="([\d.-]+)" class="point" text-anchor="(\w+)">(\w+)<', svg):
        lx, ly, w = float(lx), float(ly), len(text) * 6.0 + 2
        x0 = lx if anchor == "start" else lx - w
        labels.append((x0, ly - 11, x0 + w, ly))
    overlap = any(a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
                  for i, a in enumerate(labels) for b in labels[i + 1:])
    inside = all(2 <= cx <= bench_page.PLOT_W - 2 and 2 <= cy for cx, cy in circles)
    ticks = re.findall(r'class="tick" text-anchor="middle">([^<]+)<', svg)
    record("no two points collide, no two labels overprint, and a tick is a number",
           closest >= 10 and not overlap and inside
           and all("e+" not in tick for tick in ticks),
           f"closest={closest:.1f} overlap={overlap} inside={inside} ticks={ticks}")
except Exception as e:
    record("no two points collide, no two labels overprint, and a tick is a number",
           False, repr(e))

try:
    # five astra lanes at five efforts all read `xhigh` under a column headed
    # `Effort`, because collect reports one representative
    collected = bench.collect(_copy.deepcopy(astra), epoch_csv=FIXTURE, key_file=None)
    page2 = bench_page.render(collected, astra, sweep)
    record("the epoch table names every effort the lanes run",
           "Lane effort(s)" in page2
           and "low, medium, high, xhigh, max" in page2,
           page2[page2.find("Epoch benchmarks"):page2.find("Epoch benchmarks") + 900])
except Exception as e:
    record("the epoch table names every effort the lanes run", False, repr(e))


try:
    # A hollow marker is only hollow if its interior is the ground. The ground
    # is painted inside the SVG, not left to the CSS `background`, which is not
    # part of the document: it goes when the plot is saved out on its own and
    # when a browser prints with background graphics off.
    svg = re.search(r"<svg.*?</svg>", page, re.S).group(0)
    ground = re.search(r'<rect[^>]*fill="([^"]*)"', svg)
    first_child = svg.split(">", 1)[1].lstrip().startswith("<rect")
    pairs = set(re.findall(r'r="5" fill="([^"]*)" stroke="([^"]*)"', svg))
    label = re.search(r'aria-label="([^"]*)"', svg).group(1)
    record("the panel ground is in the document and is the hollow interior",
           ground and ground.group(1) == bench_page.SURFACE and first_child
           # one value, three uses: ground, hollow interior, solid halo
           and pairs == {(bench_page.SURFACE, bench_page.MARK),
                         (bench_page.MARK, bench_page.SURFACE)}
           and "background" not in bench_page.STYLE.split("svg {")[1].split("}")[0]
           # one image, and its label carries the finding, not just the axes
           and "xhigh is dominated" in label and "table below" in label,
           f"ground={ground and ground.group(1)} first={first_child} pairs={pairs} label={label!r}")
except Exception as e:
    record("the panel ground is in the document and is the hollow interior",
           False, repr(e))


sys.exit(1 if fails else 0)
