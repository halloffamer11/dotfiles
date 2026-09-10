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

sys.exit(1 if fails else 0)
