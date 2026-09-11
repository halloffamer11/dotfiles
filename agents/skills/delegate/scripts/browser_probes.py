#!/usr/bin/env python3
"""browser_probes.py — browser capability eval runner across delegate harnesses.

Dispatches disposable and agent-profile probes through the normal delegate
dispatch path, once per harness (claude, codex, agy, grok), and prints a
Markdown PASS/FAIL table.

Usage:
  python3 scripts/browser_probes.py [--only <harness>[,<harness>]] [--probe disposable|agent-profile] [--dry-run]
"""
import argparse
import concurrent.futures
from datetime import datetime, timezone
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import catalog

DELEGATE_PY = os.path.join(HERE, "delegate.py")
PROBES_DIR = os.path.abspath(os.path.join(HERE, "..", "assets", "probes"))
ALL_HARNESSES = ("claude", "codex", "agy", "grok")
ALL_PROBES = ("disposable", "agent-profile")


def get_cli_version(cli_name):
    """Returns parsed version string from `<cli> --version` or '—' if absent."""
    if not shutil.which(cli_name):
        return "—"
    try:
        proc = subprocess.run([cli_name, "--version"], capture_output=True, text=True, timeout=5)
        out = (proc.stdout or proc.stderr or "").strip()
        if not out:
            return "unknown"
        first_line = out.splitlines()[0].strip()
        m = re.search(r"\b\d+\.\d+(?:\.\d+)?\b", first_line)
        if m:
            return m.group(0)
        return first_line
    except Exception:
        return "unknown"


def load_effective_catalog(config_dir=None):
    """Loads the effective catalog. A catalog error stops the run: probing lanes
    from any other catalog would report on lanes the user does not run."""
    if config_dir is None:
        config_dir = os.environ.get("DELEGATE_CONFIG_DIR")
    try:
        if config_dir:
            return catalog.load_catalog(config_dir=config_dir)
        return catalog.load_catalog()
    except catalog.CatalogError as e:
        sys.exit(f"browser_probes: cannot load the delegate catalog: {e}")


def pick_lowest_tier_lane(cat, harness):
    """Picks enabled lane with lowest tier for harness (ties broken by lane name ascending)."""
    lanes = cat.get("lanes", {})
    matching = []
    for lane_name, lane_def in lanes.items():
        if lane_def.get("harness") == harness and lane_def.get("enabled", True):
            tier = lane_def.get("tier", 999)
            matching.append((tier, lane_name))
    if not matching:
        return None
    matching.sort()
    return matching[0][1]


def build_dispatch_cmd(lane, harness, brief_path, cwd):
    """Builds the delegate.py dispatch command."""
    cmd = [
        sys.executable,
        DELEGATE_PY,
        "dispatch",
        "--lane", lane,
        "--class", "scout",
        "--brief", brief_path,
        "--cwd", cwd,
    ]
    if harness != "agy":
        cmd.extend(["--effort", "low"])
    return cmd


def parse_run_dir_from_stdout(stdout):
    """Extracts run directory path from delegate dispatch output."""
    for line in stdout.splitlines():
        if line.startswith("delegate:") and "run=" in line:
            return line.split("run=")[-1].strip()
    return None


def grade(target, probe, nonce=None):
    """Pure grading function for probe runs.

    target: dict (loaded return.json), path to return.json, path to run dir, or None
    probe: 'disposable' or 'agent-profile'
    nonce: expected nonce string for 'disposable' probe

    Returns (verdict, reason): ('PASS' | 'FAIL', str)
    """
    doc = None
    if isinstance(target, dict):
        doc = target
    elif isinstance(target, str):
        path = target
        if os.path.isdir(path):
            path = os.path.join(path, "return.json")
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    doc = json.load(f)
            except Exception as e:
                return "FAIL", f"invalid return.json: {e}"
        else:
            return "FAIL", "missing return.json"
    elif target is None:
        return "FAIL", "missing return.json"
    else:
        return "FAIL", "invalid return.json"

    status = doc.get("status")
    deliverable = doc.get("deliverable", "")
    if not isinstance(deliverable, str):
        deliverable = str(deliverable or "")

    # Look for explicit FAIL line first. A line with '<' is the brief's own
    # template echoed back, not a verdict, as for PASS lines below.
    fail_reason = None
    for raw_line in deliverable.splitlines():
        line = raw_line.strip().strip("`")
        if "BROWSER-PROBE FAIL" in line and "<" not in line:
            parts = line.split("BROWSER-PROBE FAIL", 1)
            reason = parts[1].lstrip(": ").strip()
            fail_reason = reason if reason else "probe failed"
            break

    if status != "done":
        if fail_reason:
            return "FAIL", fail_reason
        return "FAIL", f"status: {status}"

    if fail_reason:
        return "FAIL", fail_reason

    # Find PASS lines that contain NO '<'
    pass_lines = []
    has_placeholder = False
    for raw_line in deliverable.splitlines():
        line = raw_line.strip().strip("`")
        if "BROWSER-PROBE PASS" in line:
            if "<" in line:
                has_placeholder = True
            else:
                pass_lines.append(line)

    if not pass_lines:
        if has_placeholder:
            return "FAIL", "pass marker contains placeholder <...>"
        return "FAIL", "no BROWSER-PROBE PASS marker found"

    pass_line = pass_lines[0]

    if probe == "disposable":
        m_title = re.search(r"title=([^\s]+(?:\s+[^\s]+)*?)(?=\s+echoed=|$)", pass_line)
        m_echoed = re.search(r"echoed=(\S+)", pass_line)
        title_val = m_title.group(1).strip() if m_title else None
        echoed_val = m_echoed.group(1).strip() if m_echoed else None

        if not title_val:
            return "FAIL", "missing title in pass marker"
        if title_val != "Example Domain":
            return "FAIL", f"wrong title: {title_val!r}"
        if not echoed_val:
            return "FAIL", "missing echoed value in pass marker"
        if nonce is not None and echoed_val != nonce:
            return "FAIL", f"wrong nonce: {echoed_val!r}"

        return "PASS", f"title={title_val} echoed={echoed_val}"

    elif probe == "agent-profile":
        m_acct = re.search(r"account=(.+)", pass_line)
        if not m_acct or not m_acct.group(1).strip():
            return "FAIL", "missing account in pass marker"
        acct_val = m_acct.group(1).strip()
        return "PASS", f"account={acct_val}"

    return "FAIL", f"unknown probe: {probe}"


def run_probe_for_harness(harness, probe_name, lane):
    """Executes a single probe dispatch for one harness."""
    tmpdir = tempfile.mkdtemp(prefix=f"delegate-probe-{harness}-{probe_name}-")
    nonce = uuid.uuid4().hex[:12]

    probe_template_path = os.path.join(PROBES_DIR, f"{probe_name}.md")
    with open(probe_template_path, "r", encoding="utf-8") as f:
        content = f.read()
    content = content.replace("{{NONCE}}", nonce)

    brief_path = os.path.join(tmpdir, f"{probe_name}.md")
    with open(brief_path, "w", encoding="utf-8") as f:
        f.write(content)

    cmd = build_dispatch_cmd(lane, harness, brief_path, tmpdir)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    run_dir = parse_run_dir_from_stdout(proc.stdout)

    if run_dir:
        verdict, reason = grade(run_dir, probe_name, nonce=nonce)
    else:
        err = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else f"exit {proc.returncode}"
        verdict, reason = "FAIL", f"dispatch failed: {err}"

    return verdict, reason


def main(argv=None):
    parser = argparse.ArgumentParser(description="Browser capability eval runner across delegate harnesses.")
    parser.add_argument("--only", default=None, help="comma-separated list of harnesses to run")
    parser.add_argument("--probe", choices=ALL_PROBES, default=None, help="run only one probe")
    parser.add_argument("--dry-run", action="store_true", help="print dispatch commands without starting them")

    args = parser.parse_args(argv)

    if args.only:
        harnesses = [h.strip() for h in args.only.split(",") if h.strip()]
        for h in harnesses:
            if h not in ALL_HARNESSES:
                sys.stderr.write(f"error: unknown harness '{h}'; must be in {', '.join(ALL_HARNESSES)}\n")
                return 2
    else:
        harnesses = list(ALL_HARNESSES)

    probes = [args.probe] if args.probe else list(ALL_PROBES)

    cat = load_effective_catalog()

    if args.dry_run:
        for harness in harnesses:
            if not shutil.which(harness):
                for probe in probes:
                    print(f"| {harness} | — | {probe} | FAIL | cli absent |")
                continue
            lane = pick_lowest_tier_lane(cat, harness)
            if not lane:
                for probe in probes:
                    print(f"| {harness} | — | {probe} | FAIL | no enabled lane |")
                continue
            for probe in probes:
                tmpdir = tempfile.mkdtemp(prefix=f"delegate-probe-{harness}-{probe}-")
                nonce = uuid.uuid4().hex[:12]
                probe_template_path = os.path.join(PROBES_DIR, f"{probe}.md")
                with open(probe_template_path, "r", encoding="utf-8") as f:
                    content = f.read()
                content = content.replace("{{NONCE}}", nonce)
                brief_path = os.path.join(tmpdir, f"{probe}.md")
                with open(brief_path, "w", encoding="utf-8") as f:
                    f.write(content)
                cmd = build_dispatch_cmd(lane, harness, brief_path, tmpdir)
                print(" ".join(cmd))
        return 0

    results = {}

    def worker(harness):
        h_rows = []
        if not shutil.which(harness):
            for probe in probes:
                h_rows.append((harness, "—", probe, "FAIL", "cli absent"))
            return harness, h_rows

        version = get_cli_version(harness)
        lane = pick_lowest_tier_lane(cat, harness)
        if not lane:
            for probe in probes:
                h_rows.append((harness, version, probe, "FAIL", "no enabled lane"))
            return harness, h_rows

        for probe in probes:
            verdict, reason = run_probe_for_harness(harness, probe, lane)
            h_rows.append((harness, version, probe, verdict, reason))
        return harness, h_rows

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(harnesses))) as executor:
        futures = [executor.submit(worker, h) for h in harnesses]
        for fut in concurrent.futures.as_completed(futures):
            h, rows = fut.result()
            results[h] = rows

    table_rows = []
    for h in harnesses:
        table_rows.extend(results.get(h, []))

    print("| harness | CLI version | probe | PASS/FAIL | reason |")
    print("|---|---|---|---|---|")
    for h, v, p, res, rsn in table_rows:
        print(f"| {h} | {v} | {p} | {res} | {rsn} |")
    print()
    print(f"hostname: {socket.gethostname()}")
    print(f"date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M %Z')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
