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
  - claude: has no list command. Claude models come from the catalog's
    claude lanes, one entry per model, with the stated reason that they are
    hand-named and undiscoverable. Claude models are never guessed. Their
    efforts come from `claude --help`, which prints the `--effort` values on
    the line after the flag; when that output lists none, the harness table
    `catalog.HARNESS_EFFORTS` stands in. A Haiku model gets no efforts: the
    Claude Code docs (https://code.claude.com/docs/en/model-config, checked
    2026-09-12) say Haiku supports no effort level.

Efforts per harness (ticket 19):
  - codex: per model, from `codex debug models`.
  - claude: from `claude --help`, as above.
  - agy: in the slug. `gemini-3.8-flash-high`, `-medium` and `-low` are one
    model family, `gemini-3.8-flash`, with efforts high, medium and low, and
    a stanza for one of them names the suffixed slug.
  - grok: `catalog.HARNESS_EFFORTS["grok"]`; `grok --help` lists no values and
    the CLI accepts any, so only the effort a lane has run at is offered.

Drift detection:
  - Slugs with no lane: models offered by a present harness that have no
    corresponding lane in lanes.json.
  - Lanes with retired/missing models: lanes in lanes.json whose model
    is no longer returned by the harness (checked only for successfully
    queried harnesses; claude lanes are excluded).

Lane generation (--efforts <model>):
  - Prints one ready-to-paste lane stanza per reasoning effort reported
    for the model, with shared price block above.
  - Generates ultra with enabled: false and documented basis.

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
        "efforts": ["<effort>"],
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
    (codex-debug-models.json, agy-models.txt, grok-models.txt, claude-help.txt).
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
from catalog import CatalogError, EFFORTS, HARNESSES, HARNESS_EFFORTS, load_catalog, strip_effort_suffix

# Harness evaluation order: harnesses with discover commands first, then claude
DISCOVER_HARNESSES = ("codex", "agy", "grok", "claude")

FIXTURE_FILES = {
    "codex": "codex-debug-models.json",
    "agy": "agy-models.txt",
    "grok": "grok-models.txt",
    "claude": "claude-help.txt",
}

HARNESS_COMMANDS = {
    "codex": ["codex", "debug", "models"],
    "agy": ["agy", "models"],
    "grok": ["grok", "models"],
    "claude": ["claude", "--help"],
}

# Claude models that take no effort level at all. The Claude Code docs
# (https://code.claude.com/docs/en/model-config, checked 2026-09-12) list the models that take effort and say "Models not
# listed here do not support effort"; Haiku is not listed. Matched as a word in
# the model slug.
CLAUDE_MODELS_WITHOUT_EFFORT = ("haiku",)


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
        efforts = []
        for level in item.get("supported_reasoning_levels", []):
            if isinstance(level, dict) and "effort" in level:
                efforts.append(level["effort"])
        models.append({
            "slug": slug,
            "display_name": item.get("display_name"),
            "efforts": efforts,
            "supported_reasoning_levels": item.get("supported_reasoning_levels", []),
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


def read_harness(harness, fixture_dir=None, runner=None):
    """The raw text a harness command prints, from a runner, a fixture, or the
    CLI itself. Returns (text, error_string)."""
    if runner is not None:
        try:
            raw = runner(harness)
        except Exception as e:
            return None, f"runner error: {e}"
    elif fixture_dir is not None:
        fname = FIXTURE_FILES.get(harness, f"{harness}-models.txt")
        fpath = os.path.join(fixture_dir, fname)
        if not os.path.isfile(fpath):
            return None, f"fixture file missing: {fname}"
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                raw = f.read()
        except Exception as e:
            return None, f"cannot read fixture {fname}: {e}"
    else:
        cmd = HARNESS_COMMANDS.get(harness)
        if not cmd:
            return None, f"no discovery command for harness '{harness}'"
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if res.returncode != 0:
                err_msg = res.stderr.strip() or f"exit code {res.returncode}"
                return None, f"command failed: {err_msg}"
            raw = res.stdout
        except subprocess.TimeoutExpired:
            return None, "command timed out (30s)"
        except Exception as e:
            return None, f"execution failed: {e}"
    return raw, None


def parse_claude_help(text):
    """The efforts `claude --help` lists for `--effort`, in its order, or [].

    The values sit in parentheses in the flag's description, which wraps onto
    the lines after the flag (`--effort <level>  Effort level for the current
    session` then `(low, medium, high, xhigh, max)`), so the description runs
    until the next line that starts a flag.
    """
    lines = (text or "").splitlines()
    for index, line in enumerate(lines):
        if not re.match(r"\s*--effort\b", line):
            continue
        description = [line]
        for following in lines[index + 1:]:
            if re.match(r"\s*-", following):
                break
            description.append(following)
        found = re.search(r"\(([^()]*)\)", " ".join(description))
        if not found:
            return []
        words = [w.strip().lower() for w in re.split(r"[,|/]", found.group(1))]
        return [w for w in words if w in EFFORTS]
    return []


def claude_efforts(fixture_dir=None, runner=None):
    """(efforts, source) for the claude harness: `claude --help` when it lists
    them, else the harness table, and the source says which."""
    raw, err = read_harness("claude", fixture_dir=fixture_dir, runner=runner)
    efforts = parse_claude_help(raw) if err is None else []
    if efforts:
        return efforts, "claude --help"
    return list(HARNESS_EFFORTS["claude"]), "catalog.HARNESS_EFFORTS (claude --help listed none)"


def model_takes_effort(harness, slug):
    """False for a model its harness runs with no effort level at all."""
    if harness != "claude":
        return True
    words = re.split(r"[^a-z0-9]+", (slug or "").lower())
    return not any(word in words for word in CLAUDE_MODELS_WITHOUT_EFFORT)


def group_agy_models(raw_models):
    """One entry per agy slug family, in listed order.

    agy carries the effort in the slug: `gemini-3.8-flash-high`, `-medium` and
    `-low` are one model at three efforts, so they are reported as
    `gemini-3.8-flash` with efforts [low, medium, high] and `members` mapping
    each effort to the slug agy accepts. A slug without an effort suffix agy
    offers is a family of one with no efforts.
    """
    families, order = {}, []
    for item in raw_models:
        slug = item["slug"]
        base, effort = strip_effort_suffix(slug)
        if effort not in HARNESS_EFFORTS["agy"] or not base:
            base, effort = slug, None
        family = families.get(base)
        if family is None:
            display = item.get("display_name")
            if effort and display:
                display = re.sub(r"\s*\((?:low|medium|high)\)\s*$", "", display, flags=re.I) or display
            family = {"slug": base, "display_name": display, "efforts": [], "members": {}}
            families[base] = family
            order.append(base)
        if effort:
            if effort not in family["efforts"]:
                family["efforts"].append(effort)
            family["members"][effort] = slug
        else:
            family["members"][None] = slug
    out = []
    for base in order:
        family = families[base]
        family["efforts"].sort(key=HARNESS_EFFORTS["agy"].index)
        out.append(family)
    return out


def query_harness(harness, fixture_dir=None, runner=None):
    """Queries a single harness for its available models.

    Returns (models_list, error_string). Every model carries `efforts`; an agy
    model is a slug family (`group_agy_models`).
    """
    raw, err = read_harness(harness, fixture_dir=fixture_dir, runner=runner)
    if err is not None:
        return [], err

    try:
        if harness == "codex":
            return parse_codex_output(raw), None
        elif harness == "agy":
            return group_agy_models(parse_agy_output(raw)), None
        elif harness == "grok":
            models = parse_grok_output(raw)
            for model in models:
                model["efforts"] = list(HARNESS_EFFORTS["grok"])
            return models, None
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
            # Claude has no list command. Claude models are named by hand in
            # the catalog and undiscoverable; never guess a Claude model list.
            # One entry per model, holding every lane that runs it.
            efforts, _source = claude_efforts(fixture_dir=fixture_dir, runner=runner)
            claude_models = {}
            for lane_name, lane_def in lanes_dict.items():
                if isinstance(lane_def, dict) and lane_def.get("harness") == "claude":
                    claude_models.setdefault(lane_def.get("model", ""), []).append(lane_name)
            harnesses_doc["claude"] = {
                "status": "ok",
                "error": None,
                "discovered_count": len(claude_models),
            }
            for slug, lane_names in claude_models.items():
                models_doc.append({
                    "harness": "claude",
                    "slug": slug,
                    "display_name": None,
                    "lane": ", ".join(lane_names),
                    "lanes": lane_names,
                    "efforts": list(efforts) if model_takes_effort("claude", slug) else [],
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
            # an agy family answers for every slug in it: a lane on
            # gemini-3.8-flash-medium is a lane on gemini-3.8-flash
            members = set((item.get("members") or {}).values()) or {slug}
            discovered_slugs.update(members)

            matched_lanes = [
                name for m in sorted(members) for name in lane_map.get((harness, m), [])
            ]
            lane_str = ", ".join(matched_lanes) if matched_lanes else "none"

            models_doc.append({
                "harness": harness,
                "slug": slug,
                "display_name": display_name,
                "lane": lane_str,
                "lanes": matched_lanes,
                "efforts": list(item.get("efforts") or []),
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
            if m.get("efforts"):
                line = f"{line}  efforts: {', '.join(m['efforts'])}"
            lines.append(line.rstrip())

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


def derive_short_name(slug):
    """Derives a short model identifier from a model slug.
    Returns (short_name, derivation_explanation)."""
    parts = slug.split("-")
    prefixes = {"gpt", "claude", "gemini", "grok"}
    # If the slug has hyphen-separated parts, check if last component is a distinctive alphabetic name
    if len(parts) > 1 and parts[-1].isalpha() and parts[-1].lower() not in prefixes:
        return parts[-1].lower(), f"last component of slug '{slug}' after '-'"
    # Look for a distinctive alphabetic part that is not a known vendor prefix
    for p in reversed(parts):
        if p.isalpha() and p.lower() not in prefixes:
            return p.lower(), f"distinctive component '{p.lower()}' from slug '{slug}'"
    # Otherwise fallback to slug with non-alphanumeric characters stripped
    clean = re.sub(r"[^a-zA-Z0-9]", "", slug).lower()
    return clean, f"alphanumeric characters of slug '{slug}'"


def generate_efforts_stanzas(harness, slug, efforts):
    """Generates ready-to-paste lane stanza dictionaries for a model's efforts.
    Returns (short_name, derivation, stanzas_dict)."""
    short_name, derivation = derive_short_name(slug)
    stanzas = {}
    for effort in efforts:
        lane_name = f"{short_name}-{effort}@{harness}"
        stanza = {
            "harness": harness,
            # agy accepts the effort only as part of the slug
            "model": f"{slug}-{effort}" if harness == "agy" else slug,
            "effort": effort,
            "meter": "TODO: meter",
            "meter_weight": "TODO: meter_weight",
            "timeout": "TODO: timeout",
            "price": "TODO: paste shared price block",
            "tier": "TODO: tier (1-4)",
        }
        if effort == "ultra":
            stanza["basis"] = (
                "unscoreable: no published source reports ultra on any benchmark for any model; "
                "ultra is maximum reasoning with automatic task delegation, which contradicts worker preamble "
                "('Do not delegate, spawn subagents, or call other agents'); "
                "meter_weight is a property of the plan, not the model (no benchmark can supply it)"
            )
            stanza["enabled"] = False
        else:
            stanza["basis"] = "meter_weight is a property of the plan, not the model (no benchmark can supply it)"
        stanzas[lane_name] = stanza
    return short_name, derivation, stanzas


def format_efforts_report(harness, slug, efforts):
    """Formats lane stanzas and shared price block as text ready for pasting into lanes.json."""
    short_name, derivation, stanzas = generate_efforts_stanzas(harness, slug, efforts)

    lines = []
    lines.append(f"# Short name '{short_name}' derived from {derivation}. Edit lane keys if preferred.")
    lines.append(f"# Shared price block (all reasoning efforts of '{slug}' share the same token rates; every stanza takes this same block):")
    lines.append('# Paste this block into each lane\'s "price" field below:')
    lines.append('"price": {')
    lines.append('  "in": "TODO: $/1M in", "cache_read": "TODO: $/1M cache read", "cache_write": null, "out": "TODO: $/1M out"')
    lines.append('}')
    lines.append("")
    lines.append("# Ready-to-paste lane stanzas for lanes.json:")

    stanza_blocks = []
    for lane_name, stanza in stanzas.items():
        block_lines = [f'"{lane_name}": {{']
        block_lines.append(f'  "harness": {json.dumps(stanza["harness"])}, "model": {json.dumps(stanza["model"])}, "effort": {json.dumps(stanza["effort"])},')
        block_lines.append(f'  "meter": {json.dumps(stanza["meter"])}, "meter_weight": {json.dumps(stanza["meter_weight"])}, "timeout": {json.dumps(stanza["timeout"])},')
        block_lines.append(f'  "price": {json.dumps(stanza["price"])}, "tier": {json.dumps(stanza["tier"])},')
        if "enabled" in stanza:
            block_lines.append(f'  "basis": {json.dumps(stanza["basis"])},')
            block_lines.append('  "enabled": false')
        else:
            block_lines.append(f'  "basis": {json.dumps(stanza["basis"])}')
        block_lines.append("}")
        stanza_blocks.append("\n".join(block_lines))

    lines.append(",\n".join(stanza_blocks))
    return "\n".join(lines)


def handle_efforts(target_model, cat=None, present=None, fixture_dir=None, runner=None, as_json=False):
    """Discovers efforts for target_model and prints report or message.
    Always returns 0."""
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

    harness_models = {}
    found_harness = None
    found_model_dict = None

    for harness in DISCOVER_HARNESSES:
        if harness not in present:
            continue
        if harness == "claude":
            efforts, _source = claude_efforts(fixture_dir=fixture_dir, runner=runner)
            models = []
            for lane_def in lanes_dict.values():
                if isinstance(lane_def, dict) and lane_def.get("harness") == "claude":
                    m = lane_def.get("model")
                    if m and not any(cm["slug"] == m for cm in models):
                        models.append({
                            "slug": m,
                            "display_name": None,
                            "efforts": list(efforts) if model_takes_effort("claude", m) else [],
                        })
        else:
            models, err = query_harness(harness, fixture_dir=fixture_dir, runner=runner)
            if err is not None:
                continue
        harness_models[harness] = models
        if found_model_dict is None:
            wanted = target_model.lower()
            for m in models:
                # an agy family is found by its own name or any slug in it
                names = {m["slug"], *(m.get("members") or {}).values()}
                if wanted in {n.lower() for n in names}:
                    found_harness = harness
                    found_model_dict = m
                    break

    if found_model_dict is None and "claude" in present and target_model.lower().startswith("claude-"):
        # A Claude model no lane runs yet. It is not guessed: the operator named
        # it, and Claude has no list command to check the name against.
        efforts, _source = claude_efforts(fixture_dir=fixture_dir, runner=runner)
        found_harness = "claude"
        found_model_dict = {
            "slug": target_model,
            "display_name": None,
            "efforts": list(efforts) if model_takes_effort("claude", target_model) else [],
        }

    if found_model_dict is not None:
        efforts = found_model_dict.get("efforts", [])
        if efforts:
            if as_json:
                short_name, derivation, stanzas = generate_efforts_stanzas(found_harness, found_model_dict["slug"], efforts)
                res = {
                    "harness": found_harness,
                    "model": found_model_dict["slug"],
                    "short_name": short_name,
                    "derivation": derivation,
                    "price": {
                        "in": "TODO: $/1M in",
                        "cache_read": "TODO: $/1M cache read",
                        "cache_write": None,
                        "out": "TODO: $/1M out",
                    },
                    "lanes": stanzas,
                }
                sys.stdout.write(json.dumps(res, indent=2) + "\n")
            else:
                print(format_efforts_report(found_harness, found_model_dict["slug"], efforts))
            return 0
        else:
            avail = [m["slug"] for m in harness_models.get(found_harness, [])]
            avail_str = ", ".join(avail) if avail else "none"
            if as_json:
                res = {
                    "error": f"harness '{found_harness}' does not offer reasoning effort levels for model '{target_model}'",
                    "harness": found_harness,
                    "model": target_model,
                    "available": avail,
                }
                sys.stdout.write(json.dumps(res, indent=2) + "\n")
            else:
                print(f"discover: harness '{found_harness}' does not offer reasoning effort levels for model '{target_model}'.")
                if not model_takes_effort(found_harness, target_model):
                    print("Claude Code's docs (https://code.claude.com/docs/en/model-config) say Haiku supports no effort level.")
                print(f"Available models on {found_harness}: {avail_str}")
            return 0

    # Model not found on any present harness
    all_avail = []
    for h in DISCOVER_HARNESSES:
        for m in harness_models.get(h, []):
            all_avail.append(f"{m['slug']} ({h})")
    all_avail_str = ", ".join(all_avail) if all_avail else "none"
    if as_json:
        res = {
            "error": f"model '{target_model}' is not offered by any available harness",
            "model": target_model,
            "available": all_avail,
        }
        sys.stdout.write(json.dumps(res, indent=2) + "\n")
    else:
        print(f"discover: model '{target_model}' is not offered by any available harness.")
        print(f"Available models: {all_avail_str}")
    return 0


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
    parser.add_argument("--efforts", metavar="MODEL", default=None, help="generate lane stanzas per effort level for model")

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

    if args.efforts is not None:
        handle_efforts(
            args.efforts,
            cat=cat,
            present=present,
            fixture_dir=args.fixture_dir,
            as_json=args.json,
        )
        return 0

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
