#!/usr/bin/env python3
"""Unit test for extract.py against real envelopes captured 2026-09-02. Run: python3 tests/test_extract.py"""
import json, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); X = os.path.join(HERE, "..", "extract.py")
CASES = [  # (file, harness, expected status, expected evidence line or None)
    ("grok.raw", "grok", "done", 2),          # prose before the JSON in "text"
    ("agy.raw", "agy", "done", 2),            # structured_output present
    ("codex.raw", "codex", "done", 2),        # -o wrote the bare object
    ("agy-blocked.raw", "agy", "blocked", None),   # child said blocked
    ("agy-empty.raw", "agy", "blocked", None),     # empty response: no object at all
]
fails = 0
for name, harness, want_status, want_line in CASES:
    out = tempfile.mktemp(suffix=".json")
    subprocess.run([sys.executable, X, harness, os.path.join(HERE, "envelopes", name), out], check=True, capture_output=True)
    o = json.load(open(out))
    line = next((e.get("line") for e in o.get("evidence", [])), None)
    ok = o.get("status") == want_status and (want_line is None or line == want_line) and all(k in o for k in ("deliverable", "open_questions", "changed_files"))
    fails += not ok
    print(("PASS" if ok else "FAIL"), name, "->", o.get("status"), "line", line)
sys.exit(1 if fails else 0)
