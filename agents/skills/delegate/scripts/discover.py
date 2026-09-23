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

Generation (ticket 33):
  - Every model carries its `level` (the slug with the version removed) and its
    `version`, and says whether it is `superseded`: by the harness itself
    (codex sets `upgrade` on a model it is retiring) or by another model of the
    same level at a higher version. The rest are the current generation.
  - `refresh_catalog` proposes, in memory, the catalog that holds a lane for
    every effort of every current-generation model, with the superseded models'
    lanes gone and each successor in its predecessor's place.

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
        "reason": "<string>" | null,
        "level": "<slug with the version removed>",
        "version": [<int>],
        "superseded": "<why>" | null,
        "members": {"<effort>": "<slug>"}
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
import copy
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
from catalog import CatalogError, EFFORTS, HARNESSES, HARNESS_EFFORTS, load_catalog

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

# Each harness runs its own vendor's models. agy also serves other vendors'
# models (`claude-sonnet-4-6`, `gpt-oss-120b-medium`); they stay in the report,
# and the refresh leaves them alone — a lane on somebody else's model through
# agy is not what this catalog is for (ticket 33).
HARNESS_VENDOR = {"codex": "gpt", "claude": "claude", "agy": "gemini", "grok": "grok"}

# A slug component that is a version: `6`, `5.6`, and the `5` `5` of
# `claude-opus-5-5`.
VERSION_PART = re.compile(r"^\d+(?:\.\d+)*$")

# The words that name a whole family rather than one model. A new lane is named
# after the model, so `gpt-6-sol` gives `sol6`; where the family word is the
# model's own name, as grok's is, the name keeps it and gives `grok47`.
VENDOR_WORDS = ("gpt", "claude", "gemini", "grok")

# An ultra lane is generated off and says why: no source scores it, and its
# automatic task delegation contradicts the worker preamble (ticket 15).
ULTRA_BASIS = (
    "unscoreable: no published source reports ultra on any benchmark for any model; "
    "ultra is maximum reasoning with automatic task delegation, which contradicts worker preamble "
    "('Do not delegate, spawn subagents, or call other agents'); "
    "meter_weight is a property of the plan, not the model (no benchmark can supply it)"
)

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
            # codex names the replacement of a model it is retiring; that is the
            # harness saying the model is superseded (ticket 33)
            "upgrade": item.get("upgrade"),
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
        base, effort = catalog.agy_family(slug)
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


def model_level(slug):
    """(level, version) for a model slug: the slug with its version taken out,
    and that version as a tuple of whole numbers.

    `gpt-6-sol` and `gpt-5.6-sol` are both level `gpt-sol`, at (6,) and (5, 6);
    `claude-opus-5-5` is `claude-opus` at (5, 5); a slug with no version is its
    own level, at (). The agy effort suffix comes off first, so one slug family
    has one level (`catalog.agy_family`).
    """
    base, _effort = catalog.agy_family(slug or "")
    words, version = [], []
    for part in base.split("-"):
        if VERSION_PART.match(part):
            version.extend(int(number) for number in part.split("."))
        else:
            words.append(part)
    return "-".join(words), tuple(version)


def mark_generation(models, harness):
    """Give each model its `level`, `version` and `superseded`, in place.

    A model is superseded when the harness says so — codex names the model that
    replaces one it is retiring — or when another model on the same harness has
    the same level at a higher version. The rest are the current generation.
    """
    newest = {}
    for item in models:
        level, version = model_level(item["slug"])
        item["level"], item["version"] = level, list(version)
        item["superseded"] = None
        best = newest.get(level)
        if best is None or version > tuple(best["version"]):
            newest[level] = item
    for item in models:
        upgrade = item.get("upgrade")
        replacement = upgrade.get("model") if isinstance(upgrade, dict) else None
        if replacement:
            item["superseded"] = f"{harness} replaces it with {replacement}"
            continue
        best = newest[item["level"]]
        if best is not item:
            item["superseded"] = f"{best['slug']} is newer"
    return models


def lane_stem(level, version, levels=()):
    """The word a new lane's name starts with: the level's own word and the
    version's digits, so `gpt-sol` at (6,) gives `sol6`, `claude-opus` at (5, 5)
    gives `opus55` and `grok` at (4, 7) gives `grok47`.

    `levels` is the harness's current-generation levels. A level that extends
    one of them — `grok-build-fast` extends `grok` — takes that level's stem and
    the word that tells it apart, so `grok-4.7-build-fast` reads `grok47fast`
    beside `grok47`. A superseded level shapes no name: codex still lists
    `gpt-5.5`, whose level is the bare `gpt`, and `gpt-6-sol` is `sol6` all the
    same.
    """
    for other in sorted(levels, key=len, reverse=True):
        if other != level and level.startswith(other + "-"):
            tail = level[len(other) + 1:].split("-")[-1]
            return lane_stem(other, version) + tail
    digits = "".join(str(number) for number in version)
    words = [word for word in level.split("-") if word not in VENDOR_WORDS]
    return (words or level.split("-"))[-1] + digits


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
            claude_doc = [
                {
                    "harness": "claude",
                    "slug": slug,
                    "display_name": None,
                    "lane": ", ".join(lane_names),
                    "lanes": lane_names,
                    "efforts": list(efforts) if model_takes_effort("claude", slug) else [],
                    "reason": "hand-named, undiscoverable",
                    "members": {},
                }
                for slug, lane_names in claude_models.items()
            ]
            models_doc.extend(mark_generation(claude_doc, "claude"))
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
        mark_generation(raw_models, harness)
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
                "level": item["level"],
                "version": item["version"],
                "superseded": item["superseded"],
                # agy names the effort in the slug, so a family says which slug
                # each effort takes; a family of one has no effort and no entry
                "members": {e: m for e, m in (item.get("members") or {}).items() if e},
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


# --- the refresh: bring the catalog to the current generation (ticket 33) ----

# A price is local knowledge read off a vendor's page, so a new lane starts with
# none rather than with its predecessor's, which would be a wrong number that
# reads like a measured one.
UNPRICED_NOTE = (
    "UNPRICED: the price keys stay null until the vendor's page is read; a price is "
    "never copied from another model."
)

# One published name for one claude model: `Claude Opus 5.5`. Claude Code names
# no model, so the benchmark rows are the only list of them there is.
PUBLISHED_CLAUDE = re.compile(r"claude\s+([A-Za-z]+)\s+([0-9]+(?:\.[0-9]+)*)", re.I)


def lane_model(harness, model, effort):
    """The model string a lane on this model at this effort carries. agy names
    the effort in the slug, so the family says which slug an effort takes."""
    if harness == "agy":
        return (model.get("members") or {}).get(effort, model["slug"])
    return model["slug"]


def model_slugs(model):
    """Every slug a model answers for: an agy family answers for each member."""
    return set((model.get("members") or {}).values()) or {model["slug"]}


def own_vendor(model):
    """True when the model is the harness's own vendor's: `gpt-*` on codex,
    `gemini-*` on agy, `grok-*` on grok, `claude-*` on claude.

    The refresh proposes lanes for these only, and nothing else names them
    either: the other vendors' models agy serves are somebody else's business.
    """
    slug = model.get("slug") or ""
    return bool(model.get("level")) and slug.split("-")[0] == HARNESS_VENDOR.get(model.get("harness"))


def claude_generation(models, published_models):
    """The claude models the refresh works from, newest version per level.

    Claude Code lists no model, so the benchmark rows name them: a published
    `Claude <Level> <version>` denotes `claude-<level>-<major>[-<minor>]`, and
    only for a level the catalog already runs on the claude harness. A level
    keeps its catalog model until a newer version of it is named (ticket 33).
    """
    out = [copy.deepcopy(item) for item in models]
    current = {}
    for item in out:
        best = current.get(item["level"])
        if best is None or tuple(item["version"]) > tuple(best["version"]):
            current[item["level"]] = item
    newer = {}
    for name in published_models or ():
        found = PUBLISHED_CLAUDE.fullmatch(str(name).strip())
        if not found:
            continue
        level = f"claude-{found.group(1).lower()}"
        version = tuple(int(number) for number in found.group(2).split("."))
        base = current.get(level)
        if base is None or version <= tuple(base["version"]):
            continue
        if level not in newer or version > newer[level][0]:
            newer[level] = (version, found.group(2))
    for level, (version, text) in newer.items():
        base = current[level]
        slug = "-".join([*level.split("-"), *text.split(".")])
        base["superseded"] = f"{slug} is newer"
        out.append({
            "harness": "claude",
            "slug": slug,
            "display_name": None,
            "lane": "none",
            "lanes": [],
            # the level's efforts: one model of a level takes what the level takes
            "efforts": list(base["efforts"]) if model_takes_effort("claude", slug) else [],
            "reason": "named by the benchmark rows",
            "level": level,
            "version": list(version),
            "superseded": None,
            "members": {},
        })
    return out


def _predecessor(model, models, lanes):
    """The superseded model whose lanes this model takes over: the same level on
    the same harness, at the highest version the catalog still runs."""
    best = None
    for item in models:
        if item is model or item["harness"] != model["harness"] or item["level"] != model["level"]:
            continue
        if not item.get("superseded"):
            continue
        slugs = model_slugs(item)
        if not any(lane.get("harness") == item["harness"] and lane.get("model") in slugs
                   for lane in lanes.values()):
            continue
        if best is None or tuple(item["version"]) > tuple(best["version"]):
            best = item
    return best


def _free_name(stem, effort, harness, *taken):
    """`<stem>-<effort>@<harness>`, kept clear of a lane another model runs.

    Two models of one harness deriving the same stem is the one way this name
    can collide; a counter after the stem is the smallest thing that separates
    them and stays the same on every run.
    """
    name = f"{stem}-{effort}@{harness}"
    counter = 1
    while any(name in names for names in taken):
        counter += 1
        name = f"{stem}{counter}-{effort}@{harness}"
    return name


def _donor(harness, effort, lanes, new_lanes, leaving):
    """The lane a new lane copies its meter, weight and timeout from: the same
    harness's lane at the same effort.

    A lane this refresh removes is no use as the note's reference, so a lane it
    adds stands in; failing both, the harness's first lane at any effort does,
    because a figure from the same harness beats no figure at all.
    """
    candidates = [(name, lane) for name, lane in lanes.items()
                  if lane.get("harness") == harness and name not in leaving]
    candidates += [(name, lane) for name, lane in new_lanes.items() if lane["harness"] == harness]
    for name, lane in candidates:
        if lane.get("effort") == effort:
            return name, lane
    return candidates[0] if candidates else (None, None)


def _lane_stem_of(lane_name):
    """`sol` from `sol-high@codex`: what the start page prints as `sol-*@codex`."""
    return lane_name.rsplit("@", 1)[0].rsplit("-", 1)[0]


def refresh_catalog(lanes_doc, discovery, published_models=()):
    """(refreshed lanes document, the changes it proposes).

    The catalog the wizard then edits: a lane for every effort of every
    current-generation model of every harness, the superseded models' lanes
    gone, and every new lane with a predecessor in that predecessor's place.
    Each harness offers its own vendor's models only, and a model its harness
    hides never reaches here.

    A new lane starts carried, `ultra` apart, so every effort of every current
    model reaches the screening page (ticket 35). It takes its predecessor's
    Tier, Order, Meter, weight and timeout, and not its `enabled`.

    Nothing is written: the wizard's confirm writes, and quitting writes
    nothing (ticket 33).
    """
    doc = copy.deepcopy(lanes_doc)
    lanes = doc.get("lanes") or {}
    models = [item for item in (discovery.get("models") or []) if isinstance(item, dict)]
    models = ([item for item in models if item.get("harness") != "claude"]
              + claude_generation([item for item in models if item.get("harness") == "claude"],
                                  published_models))
    own = [item for item in models if own_vendor(item)]

    levels = {}
    for item in own:
        if not item.get("superseded"):
            levels.setdefault(item["harness"], set()).add(item["level"])

    by_key = {(lane.get("harness"), lane.get("model"), lane.get("effort")): name
              for name, lane in lanes.items()}
    leaving = {}
    for item in own:
        if not item.get("superseded"):
            continue
        slugs = model_slugs(item)
        for name, lane in lanes.items():
            if lane.get("harness") == item["harness"] and lane.get("model") in slugs:
                leaving[name] = item

    plan_models, new_lanes, successors = [], {}, {}
    for item in own:
        if item.get("superseded"):
            continue
        harness = item["harness"]
        stem = lane_stem(item["level"], tuple(item["version"]), levels[harness])
        predecessor = _predecessor(item, own, lanes)
        added, replaced = [], []
        for effort in item.get("efforts") or []:
            model_text = lane_model(harness, item, effort)
            if (harness, model_text, effort) in by_key:
                continue
            name = _free_name(stem, effort, harness, lanes, new_lanes)
            pred_name = None
            if predecessor is not None:
                pred_name = by_key.get(
                    (harness, lane_model(harness, predecessor, effort), effort)
                )
            if pred_name:
                source_name, source = pred_name, lanes[pred_name]
                basis = (f"{item['slug']} supersedes {predecessor['slug']} on {harness}; "
                         f"takes the place of {pred_name}")
            else:
                source_name, source = _donor(harness, effort, lanes, new_lanes, set(leaving))
                basis = f"{item['slug']} is new on {harness} at effort '{effort}'"
            if source is None:
                # nothing on this harness to copy a weight or a timeout from
                continue
            record = {
                "harness": harness,
                "model": model_text,
                "effort": effort,
                "meter": source["meter"],
                "meter_weight": source["meter_weight"],
                "timeout": source["timeout"],
                "price": {"in": None, "cache_read": None, "cache_write": None, "out": None},
                # a lane with no predecessor is marked on no tier page, so it
                # lands on tier 1 unless Orin marks it higher
                "tier": source["tier"] if pred_name else 1,
                "basis": ULTRA_BASIS if effort == "ultra" else basis,
                "note": (f"UNMEASURED: meter_weight and timeout copied from {source_name}. "
                         f"{UNPRICED_NOTE}"),
            }
            if pred_name and "order" in source:
                record["order"] = source["order"]
            if effort == "ultra":
                # A new lane starts carried, so every effort of a new model is on
                # the screening page: `enabled` is the one field a successor does
                # not inherit, because a predecessor switched off at an effort is
                # a verdict on that model, not on this one (ticket 35). `ultra`
                # is never carried (ticket 15).
                record["enabled"] = False
            new_lanes[name] = record
            added.append(name)
            if pred_name:
                successors.setdefault(pred_name, []).append(name)
                replaced.append(pred_name)
        if added:
            plan_models.append({
                "harness": harness,
                "model": item["slug"],
                "predecessor": predecessor["slug"] if predecessor else None,
                "stem": stem,
                "predecessor_stem": _lane_stem_of(replaced[0]) if replaced else None,
                "new": added,
                "replaced": replaced,
            })

    ordered = {}
    for name, lane in lanes.items():
        if name in leaving:
            for successor in successors.get(name, []):
                ordered[successor] = new_lanes[successor]
            continue
        ordered[name] = lane
    for name, record in new_lanes.items():
        ordered.setdefault(name, record)
    doc["lanes"] = ordered
    return doc, {
        "models": plan_models,
        "new": list(new_lanes),
        "removed": sorted(leaving),
    }


def map_lanes(discovery, lanes_doc):
    """A discovery result whose lane mapping reads the given catalog.

    The refresh changes the catalog in memory, so the drift the start page
    states has to be drift against the catalog the wizard is about to write and
    not against the one it read (ticket 33).

    A model with no lane is worth naming only when the refresh would have given
    it one: a superseded model, another vendor's model that agy serves, and a
    model its harness hides are all not shown, so listing them as lanes missing
    would name exactly what the refresh has just decided not to propose. After
    a refresh that list is normally empty, and the line goes with it.
    """
    result = copy.deepcopy(discovery)
    lane_map = {}
    for lane_name, lane in (lanes_doc.get("lanes") or {}).items():
        if isinstance(lane, dict) and lane.get("harness") and lane.get("model"):
            lane_map.setdefault((lane["harness"], lane["model"]), []).append(lane_name)
    # a harness that answered is a harness whose listing is the whole list, so a
    # lane of its that is not on it is a lane on a retired model
    slugs = {
        name: set() for name, info in (result.get("harnesses") or {}).items()
        if isinstance(info, dict) and info.get("status") == "ok" and name != "claude"
    }
    unmapped = []
    for item in result.get("models") or []:
        harness = item.get("harness")
        members = model_slugs(item)
        if harness in slugs:
            slugs[harness].update(members)
        matched = [name for slug in sorted(members) for name in lane_map.get((harness, slug), [])]
        item["lane"] = ", ".join(matched) if matched else "none"
        item["lanes"] = matched
        if (not matched and harness != "claude"
                and own_vendor(item) and not item.get("superseded")):
            unmapped.append({
                "harness": harness,
                "slug": item.get("slug"),
                "display_name": item.get("display_name"),
            })
    retired = []
    for lane_name, lane in (lanes_doc.get("lanes") or {}).items():
        harness = lane.get("harness")
        if harness == "claude" or harness not in slugs:
            continue
        if lane.get("model") not in slugs[harness]:
            retired.append({"lane": lane_name, "harness": harness, "model": lane.get("model")})
    result["unmapped"], result["retired"] = unmapped, retired
    return result


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
            stanza["basis"] = ULTRA_BASIS
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
