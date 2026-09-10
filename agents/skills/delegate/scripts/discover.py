#!/usr/bin/env python3
"""discover.py — deterministic model discovery for delegate harnesses.

Queries installed harness CLIs to discover available models and detects
configuration drift against the lane catalog (lanes.json).

Harness behaviors:
  - codex: runs `codex debug models`, returns JSON. Only models with
    visibility == "list" are reported. Models with visibility == "hide"
    (e.g. gpt-reserve, codex-auto-review) are internal or automated and
    are not offered to a human; excluding them is deliberate.
  - agy: runs `agy models`, returns plain text. The header line
    'Fetching available models...' is skipped; subsequent lines are
    tab-delimited '<slug>\t<display name>'.
  - grok: runs `grok models`, returns plain text prose. Slugs are
    extracted from bullet lines under 'Available models:', stripping
    leading bullet markers ('*', '-') and ' (default)' suffix.
  - claude: has no list command. Claude lanes from the catalog are
    reported with the stated reason that they are hand-named and
    undiscoverable. Claude models are never guessed.

Drift detection:
  - Slugs with no lane: models offered by a present harness that have no
    corresponding lane in lanes.json.
  - Lanes with retired/missing models: lanes in lanes.json whose model
    is no longer returned by the harness (checked only for successfully
    queried harnesses; claude lanes are excluded).

Exit status:
  Always exits 0. This script is a reporting tool, never a pipeline gate.
  Missing harness binaries or failing commands are reported inline.

--json schema:
  {
    "harnesses": {
      "<harness>": {
        "status": "ok" | "missing" | "error",
        "error": "<string>" | null,
        "discovered_count": <int>
      }
    },
    "models": [
      {
        "harness": "<harness>",
        "slug": "<slug>",
        "display_name": "<string>" | null,
        "lane": "<lane_name>" | "none",
        "lanes": ["<lane_name>"],
        "reason": "<string>" | null
      }
    ],
    "unmapped": [
      {
        "harness": "<harness>",
        "slug": "<slug>",
        "display_name": "<string>" | null
      }
    ],
    "retired": [
      {
        "lane": "<lane_name>",
        "harness": "<harness>",
        "model": "<slug>"
      }
    ]
  }

Test seams:
  --config-dir: path to directory containing lanes.json and routing.json.
  --harnesses: comma-separated list of harnesses considered present on PATH.
  --fixture-dir: path to directory containing harness fixture files
    (codex-debug-models.json, agy-models.txt, grok-models.txt).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import catalog
from catalog import CatalogError, HARNESSES, load_catalog

# Harness evaluation order: harnesses with discover commands first, then claude
DISCOVER_HARNESSES = ("codex", "agy", "grok", "claude")

FIXTURE_FILES = {
    "codex": "codex-debug-models.json",
    "agy": "agy-models.txt",
    "grok": "grok-models.txt",
}

HARNESS_COMMANDS = {
    "codex": ["codex", "debug", "models"],
    "agy": ["agy", "models"],
    "grok": ["grok", "models"],
}


def parse_codex_output(text):
    """Parses JSON output from `codex debug models`.

    Only models whose visibility is 'list' are reported. Models with
    visibility 'hide' (such as gpt-reserve and codex-auto-review) are
    internal or automated and are not offered to human users; excluding
    them is deliberate.
    """
    doc = json.loads(text)
    if not isinstance(doc, dict) or "models" not in doc:
        raise ValueError("missing 'models' array in JSON output")

    models = []
    for item in doc["models"]:
        if not isinstance(item, dict):
            continue
        # Deliberately exclude hidden/internal models
        if item.get("visibility") != "list":
            continue
        slug = item.get("slug")
        if not slug:
            continue
        models.append({
            "slug": slug,
            "display_name": item.get("display_name"),
        })
    return models


def parse_agy_output(text):
    """Parses plain text output from `agy models`.

    A first line 'Fetching available models...' is skipped;
    each model line is formatted as '<slug>\t<display name>'.
    """
    models = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("Fetching available models"):
            continue
        if "\t" in line:
            parts = line.split("\t", 1)
            slug = parts[0].strip()
            display_name = parts[1].strip() if len(parts) > 1 else None
        else:
            parts = line.split(None, 1)
            slug = parts[0].strip()
            display_name = parts[1].strip() if len(parts) > 1 else None
        if slug:
            models.append({
                "slug": slug,
                "display_name": display_name,
            })
    return models


def parse_grok_output(text):
    """Parses plain text prose from `grok models`.

    Extracts slugs from bullet lines under 'Available models:',
    stripping leading bullets ('*', '-') and ' (default)' suffix.
    """
    models = []
    in_available = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("Available models:"):
            in_available = True
            continue
        if in_available:
            m = re.match(r"^[\*\-]\s+(.*?)(?:\s+\(default\))?$", line)
            if m:
                slug = m.group(1).strip()
                if slug:
                    models.append({
                        "slug": slug,
                        "display_name": slug,
                    })
    return models


def query_harness(harness, fixture_dir=None, runner=None):
    """Queries a single harness for its available models.

    Returns (models_list, error_string).
    """
    if runner is not None:
        try:
            raw = runner(harness)
        except Exception as e:
            return [], f"runner error: {e}"
    elif fixture_dir is not None:
        fname = FIXTURE_FILES.get(harness, f"{harness}-models.txt")
        fpath = os.path.join(fixture_dir, fname)
        if not os.path.isfile(fpath):
            return [], f"fixture file missing: {fname}"
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                raw = f.read()
        except Exception as e:
            return [], f"cannot read fixture {fname}: {e}"
    else:
        cmd = HARNESS_COMMANDS.get(harness)
        if not cmd:
            return [], f"no discovery command for harness '{harness}'"
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if res.returncode != 0:
                err_msg = res.stderr.strip() or f"exit code {res.returncode}"
                return [], f"command failed: {err_msg}"
            raw = res.stdout
        except subprocess.TimeoutExpired:
            return [], "command timed out (30s)"
        except Exception as e:
            return [], f"execution failed: {e}"

    try:
        if harness == "codex":
            return parse_codex_output(raw), None
        elif harness == "agy":
            return parse_agy_output(raw), None
        elif harness == "grok":
            return parse_grok_output(raw), None
        else:
            return [], f"unknown harness '{harness}'"
    except Exception as e:
        return [], f"unparseable output: {e}"


def discover(cat, present=None, fixture_dir=None, runner=None):
    """Discovers available models across harnesses and checks catalog drift.

    cat: dict containing 'lanes' (e.g. from catalog.load_catalog)
    present: set of harness names present on PATH (or None to detect)
    fixture_dir: path to directory containing harness fixtures (or None)
    runner: callable(harness) -> raw string (or None)
    """
    if present is None:
        if fixture_dir is not None:
            present = {
                h for h in DISCOVER_HARNESSES
                if h == "claude" or os.path.isfile(os.path.join(fixture_dir, FIXTURE_FILES.get(h, "")))
            }
        else:
            present = {h for h in DISCOVER_HARNESSES if shutil.which(h)}
    else:
        present = set(present)

    lanes_dict = cat.get("lanes", {}) if isinstance(cat, dict) else {}

    # Map (harness, model) -> list of lane names
    lane_map = {}
    for lane_name, lane_def in lanes_dict.items():
        if isinstance(lane_def, dict):
            h = lane_def.get("harness")
            m = lane_def.get("model")
            if h and m:
                lane_map.setdefault((h, m), []).append(lane_name)

    harnesses_doc = {}
    models_doc = []
    unmapped = []
    retired = []

    for harness in DISCOVER_HARNESSES:
        if harness not in present:
            harnesses_doc[harness] = {
                "status": "missing",
                "error": None,
                "discovered_count": 0,
            }
            continue

        if harness == "claude":
            # Claude has no list command. Claude lanes are named by hand and
            # undiscoverable. Never guess a Claude model list.
            claude_lanes = [
                (lane_name, lane_def)
                for lane_name, lane_def in lanes_dict.items()
                if isinstance(lane_def, dict) and lane_def.get("harness") == "claude"
            ]
            harnesses_doc["claude"] = {
                "status": "ok",
                "error": None,
                "discovered_count": len(claude_lanes),
            }
            for lane_name, lane_def in claude_lanes:
                slug = lane_def.get("model", "")
                models_doc.append({
                    "harness": "claude",
                    "slug": slug,
                    "display_name": None,
                    "lane": lane_name,
                    "lanes": [lane_name],
                    "reason": "hand-named, undiscoverable",
                })
            continue

        raw_models, err = query_harness(harness, fixture_dir=fixture_dir, runner=runner)
        if err is not None:
            harnesses_doc[harness] = {
                "status": "error",
                "error": err,
                "discovered_count": 0,
            }
            continue

        harnesses_doc[harness] = {
            "status": "ok",
            "error": None,
            "discovered_count": len(raw_models),
        }

        discovered_slugs = set()
        for item in raw_models:
            slug = item["slug"]
            display_name = item.get("display_name")
            discovered_slugs.add(slug)

            matched_lanes = lane_map.get((harness, slug), [])
            lane_str = ", ".join(matched_lanes) if matched_lanes else "none"

            models_doc.append({
                "harness": harness,
                "slug": slug,
                "display_name": display_name,
                "lane": lane_str,
                "lanes": matched_lanes,
                "reason": None,
            })

            if not matched_lanes:
                unmapped.append({
                    "harness": harness,
                    "slug": slug,
                    "display_name": display_name,
                })

        # Drift check: lanes pointing at models not in discovered list
        for lane_name, lane_def in lanes_dict.items():
            if isinstance(lane_def, dict) and lane_def.get("harness") == harness:
                m = lane_def.get("model")
                if m and m not in discovered_slugs:
                    retired.append({
                        "lane": lane_name,
                        "harness": harness,
                        "model": m,
                    })

    return {
        "harnesses": harnesses_doc,
        "models": models_doc,
        "unmapped": unmapped,
        "retired": retired,
    }


def format_report(result):
    """Formats discovery results as plain text with aligned columns."""
    lines = []
    lines.append("# models")

    models = result.get("models", [])
    harnesses = result.get("harnesses", {})

    max_harness_w = max((len(h) for h in DISCOVER_HARNESSES), default=6)
    max_slug_w = max((len(m["slug"]) for m in models), default=10)
    max_lane_w = max((len(f"lane: {m['lane']}") for m in models), default=10)

    for harness in DISCOVER_HARNESSES:
        h_info = harnesses.get(harness, {})
        status = h_info.get("status")

        if status == "missing":
            lines.append(f"{harness:<{max_harness_w}}  missing")
            continue
        if status == "error":
            err = h_info.get("error", "unknown error")
            lines.append(f"{harness:<{max_harness_w}}  error: {err}")
            continue

        h_models = [m for m in models if m["harness"] == harness]
        for m in h_models:
            lane_col = f"lane: {m['lane']}"
            line = f"{harness:<{max_harness_w}}  {m['slug']:<{max_slug_w}}  {lane_col:<{max_lane_w}}"
            if m.get("reason"):
                line = f"{line}  ({m['reason']})"
            lines.append(line)

    lines.append("\n# slugs with no lane")
    unmapped = result.get("unmapped", [])
    if unmapped:
        for item in unmapped:
            lines.append(f"{item['harness']:<{max_harness_w}}  {item['slug']}")
    else:
        lines.append("none")

    lines.append("\n# lanes whose model no longer appears in harness")
    retired = result.get("retired", [])
    if retired:
        max_ret_lane_w = max((len(r["lane"]) for r in retired), default=10)
        for item in retired:
            lines.append(f"{item['lane']:<{max_ret_lane_w}}  model: {item['model']}")
    else:
        lines.append("none")

    return "\n".join(lines)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="discover.py",
        description="Deterministic model discovery for delegate harnesses."
    )
    parser.add_argument("--cwd", default=None, help="working directory to find git root from")
    parser.add_argument("--config-dir", default=None, help="config directory containing lanes.json and routing.json")
    parser.add_argument("--harnesses", default=None, help="comma-separated list of present harnesses")
    parser.add_argument("--fixture-dir", default=None, help="directory containing harness output fixtures")
    parser.add_argument("--json", action="store_true", help="output as JSON")

    args = parser.parse_args(argv)

    try:
        cat = load_catalog(cwd=args.cwd, config_dir=args.config_dir)
    except CatalogError as e:
        sys.stderr.write(f"discover: warning: catalog: {e}\n")
        cat = {"lanes": {}}

    if args.harnesses is not None:
        present = set(h.strip() for h in args.harnesses.split(",") if h.strip())
    else:
        present = None

    result = discover(
        cat,
        present=present,
        fixture_dir=args.fixture_dir,
    )

    if args.json:
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
    else:
        print(format_report(result))

    # A report, never a gate: drift is reported, never signalled by exit code.
    return 0


if __name__ == "__main__":
    sys.exit(main())
