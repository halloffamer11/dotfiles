#!/usr/bin/env python3
"""catalog.py — lane catalog and routing configuration for delegate.

Manages the catalog of execution lanes (harness x model x meter) and the
routing policy mapping task classes to minimum model tiers.

Locations:
  CONFIG_DIR = ~/.config/delegate (expanded at call time)
  global lanes:    <CONFIG_DIR>/lanes.json
  global routing:  <CONFIG_DIR>/routing.json
  project routing: <git-root>/.delegate/routing.json
  class guide:     <skill>/assets/classes.md
  project guide:   <git-root>/.delegate/classes.md

CLI forms:
  catalog.py show [--cwd DIR] [--config-dir DIR] [--json]
  catalog.py check FILE [--partial]   (warns when one Meter serves a whole Tier)
  catalog.py check-guide [FILE] [--overlay]
  catalog.py fmt FILE [--partial]
  catalog.py set FIELD JSON_VALUE --scope global|project [--cwd DIR] [--config-dir DIR]
      FIELD is lanes.<lane>.tier, routing.gate, routing.margin, routing.meters,
      or routing.overflow
  catalog.py range CLASS FLOOR CEILING --scope global|project [--cwd DIR] [--config-dir DIR]
  catalog.py order LANE POSITION --scope global|project [--cwd DIR] [--config-dir DIR]
  (set/range/order default to a JSON preview; --apply --expect REVISION writes)
"""
import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile

CONFIG_DIR = "~/.config/delegate"

HARNESSES = ("claude", "codex", "agy", "grok")
EFFORTS = ("low", "medium", "high", "xhigh", "max", "ultra")
# The efforts each harness offers, and so the only efforts a lane on it may
# carry (ticket 19). Sources, each checked 2026-09-12:
#   codex   every effort; `codex debug models` lists them per model, and ultra
#           is one of them.
#   claude  `claude --help` (Claude Code 2.1.269): `--effort <level>` with
#           `(low, medium, high, xhigh, max)` on the next line; the same five in
#           https://code.claude.com/docs/en/model-config. That page also says
#           Haiku supports no effort level, which is a model's limit, not the
#           harness's: discover.py applies it.
#   agy     `agy --help`: `--effort ... (low|medium|high)`, and `agy models`
#           lists a -low, -medium and -high slug per Gemini Flash model.
#   grok    `grok --help` documents `--reasoning-effort <EFFORT>` with no
#           values, and `grok --reasoning-effort bogus models` exits 0, so the
#           CLI checks nothing locally. Only high is proven: it is the effort
#           grok46-high@grok has run at. A probe that proves more costs a paid run.
HARNESS_EFFORTS = {
    "codex": EFFORTS,
    "claude": ("low", "medium", "high", "xhigh", "max"),
    "agy": ("low", "medium", "high"),
    "grok": ("high",),
}
CLASSES = ("scout", "mechanical", "impl", "review", "hard-impl")
LANES_VERSION = "delegate-lanes.v1"
ROUTING_VERSION = "delegate-routing.v1"
# Class sections in assets/classes.md (and a project overlay) are ATX headings
# at this level, named exactly as CLASSES. Other heading levels are metadata
# and are not checked against the registry, so "How to pick" cannot collide.
CLASS_GUIDE_HEADING_LEVEL = 2
ATX_HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.+?)\s*$")
FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")
# Floor/Ceiling integers belong in routing.json. A `floor:` / `ceiling:` (or
# `=`) declaration in the guide is how numeric policy drifted before.
FLOOR_CEILING_DECL = re.compile(r"(?i)\b(floor|ceiling)\s*[:=]\s*\d+")

# Benchmark sources print a model however they please: some publish the slug a
# harness accepts (`gpt-5.6-luna`), some a display name (`GPT-6 Astra`,
# `Fable 5.1`). The catalog keys on slugs, so a consumer of published rows has
# to reconcile the two. That mapping is local knowledge — which published name
# denotes which of our lane models — so it lives here, beside the lane, where a
# human can read and correct it: the optional lane field `published_as`.
NORM_SEP = re.compile(r"[-_. ]+")
# Longest first, so `-xhigh` is not read as `-high`. Every effort in EFFORTS
# belongs here: a source names a row `gpt-6-astra-max` as readily as
# `gpt-6-astra-high`, and while `-max` and `-ultra` were missing such a row
# matched no lane model at all and the figure was dropped (ticket 17).
MODEL_EFFORT_SUFFIXES = (
    ("-xhigh", "xhigh"),
    ("-medium", "medium"),
    ("-ultra", "ultra"),
    ("-high", "high"),
    ("-max", "max"),
    ("-low", "low"),
)


class CatalogError(Exception):
    """Plain-language catalog configuration or validation error."""
    pass


def find_git_root(start_dir=None):
    """Find git root by walking up from start_dir (default: current directory)
    until a .git entry (file or directory) is found. No git subprocess.
    Returns absolute directory path, or None if no git root found."""
    if start_dir is None:
        start_dir = os.getcwd()
    current = os.path.abspath(os.path.expanduser(start_dir))
    while True:
        git_path = os.path.join(current, ".git")
        if os.path.exists(git_path) or os.path.islink(git_path):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def format_json(doc):
    """Returns canonical text: json.dumps(doc, indent=2, ensure_ascii=False) plus trailing newline."""
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def write_json(path, doc):
    """Writes format_json(doc) atomically (temp file in the same directory, then os.replace).
    Creates parent directory if needed."""
    full_path = os.path.abspath(os.path.expanduser(path))
    parent_dir = os.path.dirname(full_path)
    os.makedirs(parent_dir, exist_ok=True)
    text = format_json(doc)
    fd, temp_path = tempfile.mkstemp(dir=parent_dir, prefix=".tmp_catalog_", text=True)
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, full_path)
    except BaseException:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        raise


def load_json(path):
    """Strict JSON parser. Rejects NaN, Infinity, -Infinity.
    Missing file raises CatalogError naming the file and, for global lanes file,
    that samples/lanes.json can be copied there.
    Syntax error raises CatalogError with file name, line, and column."""
    expanded = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(expanded):
        if os.path.basename(expanded) == "lanes.json":
            raise CatalogError(
                f"{path}: file is missing; copy samples/lanes.json there or run /delegate setup"
            )
        raise CatalogError(f"{path}: file is missing")

    try:
        with open(expanded, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        raise CatalogError(f"{path}: file: cannot read: {e}")

    def _reject_constant(c):
        raise ValueError(f"{c} is not allowed in strict JSON")

    try:
        return json.loads(content, parse_constant=_reject_constant)
    except json.JSONDecodeError as e:
        raise CatalogError(
            f"{path}: line {e.lineno}, column {e.colno}: JSON syntax error: {e.msg}"
        )
    except ValueError as e:
        raise CatalogError(f"{path}: number: NaN is not allowed in strict JSON ({e})")


def normalize_name(value):
    """Lower-case, with the -_. and space separators collapsed to one hyphen."""
    if value is None:
        return ""
    return NORM_SEP.sub("-", str(value).strip().lower()).strip("-")


def strip_effort_suffix(model):
    """Splits a trailing effort off a model slug: gemini-3.8-flash-high -> (base, 'high')."""
    for suffix, effort in MODEL_EFFORT_SUFFIXES:
        if model.endswith(suffix):
            return model[: -len(suffix)], effort
    return model, None


def agy_family(slug):
    """The agy slug family a model slug belongs to: (base, effort).

    agy carries the effort in the slug, so `gemini-3.8-flash-high` is the model
    `gemini-3.8-flash` at effort high. A slug whose suffix is not an effort agy
    offers is a family of its own, with no effort: `(slug, None)`.

    One rule in one place. Discovery groups a harness listing with it
    (`discover.group_agy_models`) and the carry rule groups a lane's rows with it
    (`bench.model_families`), so the wizard can never disagree with the models
    discovery reported (ticket 30).
    """
    text = slug or ""
    base, effort = strip_effort_suffix(text)
    if not base or effort not in HARNESS_EFFORTS["agy"]:
        return text, None
    return base, effort


def published_as_map(lanes_doc):
    """{normalized published name: lane model} from every lane's published_as."""
    out = {}
    for lane in (lanes_doc.get("lanes") or {}).values():
        if not isinstance(lane, dict):
            continue
        for name in lane.get("published_as") or []:
            key = normalize_name(name)
            if key:
                out[key] = lane.get("model")
    return out


def resolve_published_model(published, lanes_doc, effort=None):
    """The lane model that a source's printed model name denotes, or None.

    A `published_as` entry is consulted first: it is the human's own correction,
    and it is the only way across a gap formatting cannot bridge
    (`Fable 5.1` -> `claude-fable-5-1`). It cannot contradict the derived rule,
    because `validate_lanes` refuses an entry that names a model another lane
    runs — an entry that could redirect one lane's rows onto another lane is a
    typo, never an intention.

    Failing an entry, the name has to differ from a lane model by formatting
    alone — case and the -_. separators — reaching past the effort suffix some
    of our slugs carry (`gemini-3.8-flash-high`). Anything looser would be a
    guess about which model a leaderboard meant, and a wrong guess switches a
    working lane off. A name that two lane models could equally denote therefore
    resolves to neither, and a name no lane runs resolves to None: the
    leaderboards are full of models that are nobody's lane.

    The one exception is a family of lane models that differ only by their
    effort suffix, which is how agy names one model at several efforts
    (`gemini-3.8-flash-high`, `gemini-3.8-flash-medium`). A row that states its
    `effort` resolves to the one family member carrying that effort; without
    an effort, or with an effort no member carries, it still resolves to
    neither (ticket 19).
    """
    key = normalize_name(published)
    if not key:
        return None
    explicit = published_as_map(lanes_doc)
    if key in explicit:
        return explicit[key]
    candidates = set()
    for lane in (lanes_doc.get("lanes") or {}).values():
        if not isinstance(lane, dict):
            continue
        model = lane.get("model")
        if not isinstance(model, str) or not model.strip():
            continue
        normalized = normalize_name(model)
        base, _effort = strip_effort_suffix(normalized)
        if key in (normalized, base):
            candidates.add(model)
    if len(candidates) == 1:
        return candidates.pop()
    if effort and len(candidates) > 1:
        at_effort = {m for m in candidates
                     if strip_effort_suffix(normalize_name(m))[1] == str(effort)}
        if len(at_effort) == 1:
            return at_effort.pop()
    return None


def validate_lanes(doc, source="lanes.json"):
    """Validates a lanes document against the schema. Returns doc or raises CatalogError."""
    if not isinstance(doc, dict):
        raise CatalogError(f"{source}: document: must be a JSON object")

    allowed_top = {"version", "meters", "lanes", "note"}
    for k in doc:
        if k not in allowed_top:
            raise CatalogError(
                f"{source}: key '{k}': unknown top-level key; allowed keys are 'version', 'meters', 'lanes', 'note'"
            )

    for req in ("version", "meters", "lanes"):
        if req not in doc:
            raise CatalogError(f"{source}: key '{req}': missing required top-level key")

    if doc["version"] != LANES_VERSION:
        raise CatalogError(
            f"{source}: key 'version': must equal '{LANES_VERSION}', got {doc['version']!r}"
        )

    if "note" in doc and not isinstance(doc["note"], str):
        raise CatalogError(f"{source}: key 'note': note must be a string")

    meters = doc["meters"]
    if not isinstance(meters, dict) or len(meters) == 0:
        raise CatalogError(f"{source}: key 'meters': meters must be a non-empty object")

    allowed_meter_fields = {"harness", "plan", "price_month", "probe", "note"}
    required_meter_fields = ("harness", "plan", "price_month", "probe")

    for meter_name, meter in meters.items():
        if not isinstance(meter, dict):
            raise CatalogError(f"{source}: meter '{meter_name}': must be an object")
        for field in meter:
            if field not in allowed_meter_fields:
                raise CatalogError(f"{source}: meter '{meter_name}': unknown field '{field}'")
        for req in required_meter_fields:
            if req not in meter:
                raise CatalogError(f"{source}: meter '{meter_name}': missing required field '{req}'")

        if meter["harness"] not in HARNESSES:
            raise CatalogError(
                f"{source}: meter '{meter_name}': harness must be one of {', '.join(HARNESSES)}, got {meter['harness']!r}"
            )
        if not isinstance(meter["plan"], str) or not meter["plan"].strip():
            raise CatalogError(f"{source}: meter '{meter_name}': plan must be a non-empty string")
        pm = meter["price_month"]
        if type(pm) is bool or not isinstance(pm, (int, float)) or pm < 0:
            raise CatalogError(
                f"{source}: meter '{meter_name}': price_month must be a number >= 0, got {pm!r}"
            )
        if not isinstance(meter["probe"], str) or not meter["probe"].strip():
            raise CatalogError(f"{source}: meter '{meter_name}': probe must be a non-empty string")
        if "note" in meter and not isinstance(meter["note"], str):
            raise CatalogError(f"{source}: meter '{meter_name}': note must be a string")

    lanes = doc["lanes"]
    if not isinstance(lanes, dict) or len(lanes) == 0:
        raise CatalogError(f"{source}: key 'lanes': lanes must be a non-empty object")

    allowed_lane_fields = {
        "harness", "model", "effort", "meter", "meter_weight", "timeout",
        "price", "tier", "basis", "note", "enabled", "published_as", "order"
    }
    required_lane_fields = (
        "harness", "model", "effort", "meter", "meter_weight", "timeout",
        "price", "tier", "basis"
    )
    price_keys = ("in", "cache_read", "cache_write", "out")
    claimed = {}
    # Which lane models a published name could denote on its own, so that a
    # published_as entry cannot be pointed at somebody else's model.
    owners = {}
    for lane in lanes.values():
        if not isinstance(lane, dict):
            continue
        model = lane.get("model")
        if not isinstance(model, str) or not model.strip():
            continue
        normalized = normalize_name(model)
        base, _effort = strip_effort_suffix(normalized)
        for key in {normalized, base}:
            owners.setdefault(key, set()).add(model)

    for lane_name, lane in lanes.items():
        if not isinstance(lane, dict):
            raise CatalogError(f"{source}: lane '{lane_name}': must be an object")
        for field in lane:
            if field not in allowed_lane_fields:
                raise CatalogError(f"{source}: lane '{lane_name}': unknown field '{field}'")
        for req in required_lane_fields:
            if req not in lane:
                raise CatalogError(f"{source}: lane '{lane_name}': missing required field '{req}'")

        harness = lane["harness"]
        if harness not in HARNESSES:
            raise CatalogError(
                f"{source}: lane '{lane_name}': harness must be one of {', '.join(HARNESSES)}, got {harness!r}"
            )
        expected_suffix = f"@{harness}"
        if not lane_name.endswith(expected_suffix):
            raise CatalogError(
                f"{source}: lane '{lane_name}': lane name must end with '{expected_suffix}'"
            )

        if not isinstance(lane["model"], str) or not lane["model"].strip():
            raise CatalogError(f"{source}: lane '{lane_name}': model must be a non-empty string")

        if lane["effort"] not in EFFORTS:
            raise CatalogError(
                f"{source}: lane '{lane_name}': effort must be one of {', '.join(EFFORTS)}, got {lane['effort']!r}"
            )
        offered = HARNESS_EFFORTS[harness]
        if lane["effort"] not in offered:
            raise CatalogError(
                f"{source}: lane '{lane_name}': {harness} does not offer effort {lane['effort']!r}; "
                f"{harness} offers {', '.join(offered)}"
            )

        meter_id = lane["meter"]
        if meter_id not in meters:
            raise CatalogError(
                f"{source}: lane '{lane_name}': meter '{meter_id}' is not defined in meters (missing meter)"
            )
        meter_harness = meters[meter_id].get("harness")
        if meter_harness != harness:
            raise CatalogError(
                f"{source}: lane '{lane_name}': meter '{meter_id}' belongs to another harness '{meter_harness}', does not match lane harness '{harness}'"
            )

        mw = lane["meter_weight"]
        if type(mw) is bool or not isinstance(mw, (int, float)) or mw <= 0:
            raise CatalogError(
                f"{source}: lane '{lane_name}': meter_weight must be a number > 0, got {mw!r}"
            )

        timeout = lane["timeout"]
        if not isinstance(timeout, str) or not re.fullmatch(r"[0-9]+[smh]", timeout):
            raise CatalogError(
                f"{source}: lane '{lane_name}': timeout must match '^[0-9]+[smh]$', got {timeout!r}"
            )

        price = lane["price"]
        if not isinstance(price, dict):
            raise CatalogError(f"{source}: lane '{lane_name}': price must be an object")
        for pk in price:
            if pk not in price_keys:
                raise CatalogError(f"{source}: lane '{lane_name}': price has unknown key '{pk}'")
        for pk in price_keys:
            if pk not in price:
                raise CatalogError(f"{source}: lane '{lane_name}': price is missing required key '{pk}'")
            pv = price[pk]
            if pv is not None:
                if type(pv) is bool or not isinstance(pv, (int, float)) or pv < 0:
                    raise CatalogError(
                        f"{source}: lane '{lane_name}': price key '{pk}' must be a number >= 0 or null, got {pv!r}"
                    )

        tier = lane["tier"]
        if type(tier) is not int or tier < 1 or tier > 4:
            raise CatalogError(
                f"{source}: lane '{lane_name}': tier must be a whole number from 1 to 4, got {tier!r}"
            )

        if "order" in lane:
            # the lane's place inside its tier, from 1, which the wizard's review
            # page writes and rank.py sorts by after tier (ticket 28)
            order = lane["order"]
            if type(order) is not int or order < 1:
                raise CatalogError(
                    f"{source}: lane '{lane_name}': order is the lane's place inside its tier "
                    f"and must be a whole number from 1 up, got {order!r}"
                )

        if not isinstance(lane["basis"], str):
            raise CatalogError(f"{source}: lane '{lane_name}': basis must be a string")

        if "note" in lane and not isinstance(lane["note"], str):
            raise CatalogError(f"{source}: lane '{lane_name}': note must be a string")

        if "enabled" in lane:
            en = lane["enabled"]
            if type(en) is not bool:
                raise CatalogError(
                    f"{source}: lane '{lane_name}': enabled must be a boolean, got {en!r}"
                )

        if "published_as" in lane:
            names = lane["published_as"]
            if not isinstance(names, list) or not names:
                raise CatalogError(
                    f"{source}: lane '{lane_name}': published_as must be a non-empty list of "
                    f"the names benchmark sources print for this model, got {names!r}"
                )
            for name in names:
                if not isinstance(name, str) or not name.strip():
                    raise CatalogError(
                        f"{source}: lane '{lane_name}': published_as entries must be "
                        f"non-empty strings, got {name!r}"
                    )
                key = normalize_name(name)
                foreign = sorted(m for m in owners.get(key, ()) if m != lane["model"])
                if foreign:
                    raise CatalogError(
                        f"{source}: lane '{lane_name}': published_as {name!r} already names "
                        f"model '{foreign[0]}', which another lane runs; that would read "
                        f"'{foreign[0]}' rows as '{lane['model']}'. Drop the entry, or put it "
                        f"on the lane that runs '{foreign[0]}'"
                    )
                first = claimed.get(key)
                if first is not None and first[2] != lane["model"]:
                    raise CatalogError(
                        f"{source}: lane '{lane_name}': published_as {name!r} names the same "
                        f"model as {first[0]!r} on lane '{first[1]}'; one published name "
                        f"denotes one model, but this would make it both '{first[2]}' and "
                        f"'{lane['model']}'"
                    )
                if first is None:
                    claimed[key] = (name, lane_name, lane["model"])

    return doc


def validate_project_lanes(doc, global_lanes, source="project lanes.json",
                           lanes_source="lanes.json"):
    """Validate a project's lane customization against the global lane catalog.

    The file is `<git-root>/.delegate/lanes.json`, beside the project's
    routing.json. It names Lanes the global catalog already has and sets one
    field on them, `tier`; every other Lane field stays global (ticket 32).
    Returns ``doc`` or raises ``CatalogError``.
    """
    if not isinstance(doc, dict):
        raise CatalogError(f"{source}: document: must be a JSON object")

    allowed_top = {"lanes", "note"}
    for k in doc:
        if k == "version":
            # `check` picks its validator by version, so a project file that
            # claimed the lanes version would be checked as a global catalog.
            raise CatalogError(
                f"{source}: key 'version': a project lane customization carries no "
                f"version; the lanes it names are versioned by {lanes_source}"
            )
        if k not in allowed_top:
            raise CatalogError(
                f"{source}: key '{k}': unknown top-level key; allowed keys are "
                f"{', '.join(sorted(allowed_top))}"
            )
    if "note" in doc and not isinstance(doc["note"], str):
        raise CatalogError(f"{source}: key 'note': note must be a string")

    lanes = doc.get("lanes", {})
    if not isinstance(lanes, dict):
        raise CatalogError(
            f"{source}: key 'lanes': lanes must be an object of lane names to "
            "the fields this project sets"
        )
    known = global_lanes.get("lanes", {}) if isinstance(global_lanes, dict) else {}
    for lane_name, lane in lanes.items():
        if lane_name not in known:
            raise CatalogError(
                f"{source}: lane '{lane_name}': lane is not in the global lane "
                f"catalog ({lanes_source}); a project customizes a lane the "
                "catalog already has"
            )
        if not isinstance(lane, dict):
            raise CatalogError(f"{source}: lane '{lane_name}': must be an object")
        for field in lane:
            if field not in ("tier", "note"):
                raise CatalogError(
                    f"{source}: lane '{lane_name}': unknown field '{field}'; a "
                    "project may set only 'tier' (with an optional 'note'); every "
                    "other lane field stays global"
                )
        if "tier" not in lane:
            raise CatalogError(
                f"{source}: lane '{lane_name}': missing required field 'tier'; "
                "a lane entry exists to set a tier"
            )
        tier = lane["tier"]
        if type(tier) is not int or tier < 1 or tier > 4:
            raise CatalogError(
                f"{source}: lane '{lane_name}': tier must be a whole number from "
                f"1 to 4, got {tier!r}"
            )
        if "note" in lane and not isinstance(lane["note"], str):
            raise CatalogError(f"{source}: lane '{lane_name}': note must be a string")
    return doc


def project_tier_changes(global_lanes, project_lanes):
    """Lanes whose Tier the project changes: {lane: {"from": n, "to": m}}.

    A project entry equal to the global Tier changes nothing and is left out,
    which is what "a project Tier is in effect" means to `show` and the rank
    header.
    """
    if not project_lanes:
        return {}
    known = global_lanes.get("lanes", {}) if isinstance(global_lanes, dict) else {}
    changes = {}
    for lane_name, lane in (project_lanes.get("lanes") or {}).items():
        if lane_name not in known or not isinstance(lane, dict):
            continue
        global_tier = known[lane_name].get("tier")
        tier = lane.get("tier")
        if tier is not None and tier != global_tier:
            changes[lane_name] = {"from": global_tier, "to": tier}
    return changes


def validate_routing(doc, source="routing.json", partial=False):
    """Validates a routing document. If partial=False (global file), all required keys
    and all classes must be present. If partial=True (project override), keys are optional.
    Returns doc or raises CatalogError."""
    if not isinstance(doc, dict):
        raise CatalogError(f"{source}: document: must be a JSON object")

    if "classTier" in doc:
        raise CatalogError(f"{source}: key 'classTier': 'classTier' has been replaced by 'classes'; use {{\"classes\": {{\"<class>\": {{\"floor\": 1, \"ceiling\": 2}}}}}}")

    if not partial and "project_order" in doc:
        raise CatalogError(
            f"{source}: key 'project_order': project_order is project-only and "
            "cannot appear in global routing"
        )

    allowed_top = {"version", "classes", "margin", "gate", "meters", "overflow", "note"}
    if partial:
        allowed_top.add("project_order")
    for k in doc:
        if k not in allowed_top:
            raise CatalogError(
                f"{source}: key '{k}': unknown top-level key; allowed keys are {', '.join(sorted(allowed_top))}"
            )

    if not partial:
        for req in ("version", "classes", "margin", "gate"):
            if req not in doc:
                raise CatalogError(f"{source}: key '{req}': missing required top-level key")

    if "version" in doc and doc["version"] != ROUTING_VERSION:
        raise CatalogError(
            f"{source}: key 'version': must equal '{ROUTING_VERSION}', got {doc['version']!r}"
        )

    if "classes" in doc:
        cls_map = doc["classes"]
        if not isinstance(cls_map, dict):
            raise CatalogError(f"{source}: key 'classes': classes must be an object")
        if not partial:
            for c in CLASSES:
                if c not in cls_map:
                    raise CatalogError(f"{source}: classes: missing required class '{c}'")
        for cls_name, cls_range in cls_map.items():
            if cls_name not in CLASSES:
                raise CatalogError(f"{source}: classes: unknown class '{cls_name}'")
            if not isinstance(cls_range, dict):
                raise CatalogError(
                    f"{source}: classes: class '{cls_name}': must be an object with 'floor' and 'ceiling'"
                )
            for fld in cls_range:
                if fld not in ("floor", "ceiling"):
                    raise CatalogError(
                        f"{source}: classes: class '{cls_name}': unknown field '{fld}'"
                    )
            if not partial:
                for req in ("floor", "ceiling"):
                    if req not in cls_range:
                        raise CatalogError(
                            f"{source}: classes: class '{cls_name}': missing required field '{req}'"
                        )
            f = cls_range.get("floor")
            c = cls_range.get("ceiling")
            if f is not None:
                if type(f) is not int or f < 1 or f > 4:
                    raise CatalogError(
                        f"{source}: classes: class '{cls_name}': floor must be an integer from 1 to 4, got {f!r}"
                    )
            if c is not None:
                if type(c) is not int or c < 1 or c > 4:
                    raise CatalogError(
                        f"{source}: classes: class '{cls_name}': ceiling must be an integer from 1 to 4, got {c!r}"
                    )
            if f is not None and c is not None and f > c:
                raise CatalogError(
                    f"{source}: classes: class '{cls_name}': floor ({f}) cannot exceed ceiling ({c}); 1 <= floor <= ceiling <= 4"
                )

    if "margin" in doc:
        m = doc["margin"]
        if type(m) is bool or not isinstance(m, (int, float)) or not (0.0 <= m <= 1.0):
            raise CatalogError(
                f"{source}: key 'margin': margin must be a number between 0 and 1, got {m!r}"
            )

    if "gate" in doc:
        g = doc["gate"]
        if type(g) is bool or not isinstance(g, (int, float)) or not (0.0 <= g <= 1.0):
            raise CatalogError(
                f"{source}: key 'gate': gate must be a number between 0 and 1, got {g!r}"
            )

    if "meters" in doc:
        m = doc["meters"]
        if type(m) is not bool:
            raise CatalogError(
                f"{source}: key 'meters': meters must be a JSON boolean, got {m!r}"
            )

    if "overflow" in doc:
        o = doc["overflow"]
        if type(o) is not bool:
            raise CatalogError(
                f"{source}: key 'overflow': overflow must be a JSON boolean, got {o!r}; "
                "true lets a Range whose carried Lanes are all under the Gate admit the "
                "next Tier instead of stopping"
            )

    if "project_order" in doc:
        project_order = doc["project_order"]
        if not isinstance(project_order, list):
            raise CatalogError(
                f"{source}: key 'project_order': project_order must be a flat list "
                f"of non-empty lane-name strings, got {project_order!r}"
            )
        for lane_name in project_order:
            if not isinstance(lane_name, str) or not lane_name.strip():
                raise CatalogError(
                    f"{source}: key 'project_order': project_order must be a flat list "
                    f"of non-empty lane-name strings, got entry {lane_name!r}"
                )

    if "note" in doc and not isinstance(doc["note"], str):
        raise CatalogError(f"{source}: key 'note': note must be a string")

    return doc


def merge_routing(global_doc, project_doc=None, global_source="routing.json", project_source=None):
    """Merges global routing and optional project routing.
    Each top-level key in project_doc replaces global value, except classes which merges per class and per key.
    Returns (routing, sources)."""
    g_src = global_source
    p_src = project_source

    routing = copy.deepcopy(global_doc)
    sources = {}
    for k in global_doc:
        sources[k] = g_src
    if "classes" in global_doc and isinstance(global_doc["classes"], dict):
        sources["classes"] = g_src
        for c, c_val in global_doc["classes"].items():
            sources[f"classes.{c}"] = g_src
            if isinstance(c_val, dict):
                for sub_k in c_val:
                    sources[f"classes.{c}.{sub_k}"] = g_src

    if project_doc:
        for k, v in project_doc.items():
            if k == "classes" and isinstance(v, dict):
                if "classes" not in routing or not isinstance(routing["classes"], dict):
                    routing["classes"] = {}
                sources["classes"] = p_src
                for c, c_val in v.items():
                    if isinstance(c_val, dict):
                        if c not in routing["classes"] or not isinstance(routing["classes"][c], dict):
                            routing["classes"][c] = {}
                        sources[f"classes.{c}"] = p_src
                        for sub_k, sub_v in c_val.items():
                            routing["classes"][c][sub_k] = sub_v
                            sources[f"classes.{c}.{sub_k}"] = p_src
                    else:
                        routing["classes"][c] = copy.deepcopy(c_val)
                        sources[f"classes.{c}"] = p_src
            else:
                routing[k] = copy.deepcopy(v)
                sources[k] = p_src

    return routing, sources


def meters_enabled(routing):
    """Effective routing.meters: JSON true or false, absent defaults on."""
    if not isinstance(routing, dict) or "meters" not in routing:
        return True
    return routing["meters"] is True


def overflow_enabled(routing):
    """Effective routing.overflow: JSON true or false, absent defaults on.

    On, a Class whose carried in-Range Lanes are every one of them under the
    Gate admits the next Tier above its Ceiling rather than stopping the job
    (ticket 29). Off keeps the stop. The default is on because a Gate-only
    outage costs the job, while the Tier above it costs usage.
    """
    if not isinstance(routing, dict) or "overflow" not in routing:
        return True
    return routing["overflow"] is True


def single_meter_tiers(lanes):
    """[(tier, meter, [lane, ...]), ...] for each Tier one Meter wholly serves.

    Coverage, not judgment (ticket 29): when every carried Lane of a Tier drains
    one Meter, that Meter falling under the Gate takes the whole Tier with it.
    Which Lanes a Tier carries is Orin's decision and this never questions it.
    A Tier with no carried Lane is not named.
    """
    out = []
    for tier in range(1, 5):
        carried = sorted(
            name for name, lane in (lanes or {}).items()
            if isinstance(lane, dict)
            and lane.get("enabled", True)
            and lane.get("tier") == tier
        )
        if not carried:
            continue
        used = {lanes[name].get("meter") for name in carried}
        if len(used) == 1:
            out.append((tier, used.pop(), carried))
    return out


def meter_dependency_lines(lanes, names=False):
    """One line per Tier that `single_meter_tiers` names.

    `names=True` appends the carried Lanes, which `check` has room for. The
    wizard's review page does not: a legend line past 79 places is clipped, so
    that page takes the short form.
    """
    lines = []
    for tier, meter, lane_names in single_meter_tiers(lanes):
        line = f"Tier {tier} depends on Meter {meter}; a Gate stop there stops the Tier."
        if names:
            line += f" Carried: {', '.join(lane_names)}"
        lines.append(line)
    return lines


def _validate_merged_routing(routing, source):
    """Validate a complete effective routing document.

    ``project_order`` has already been validated as project policy; remove that
    project-only projection before applying the complete global-routing shape.
    """
    routing_fields = copy.deepcopy(routing)
    routing_fields.pop("project_order", None)
    validate_routing(routing_fields, source=source, partial=False)


def validate_project_routing(
    doc,
    global_lanes,
    global_routing,
    source="project routing.json",
    lanes_source="lanes.json",
    global_source="routing.json",
):
    """Validate proposed project policy against both global documents.

    This is the public pre-save boundary for project routing. It validates all
    three input documents, Project order's catalog references, and the complete
    routing document produced by merging the proposal over global routing.
    Returns ``doc`` unchanged, or raises ``CatalogError``.
    """
    validate_lanes(global_lanes, source=lanes_source)
    validate_routing(global_routing, source=global_source, partial=False)
    validate_routing(doc, source=source, partial=True)

    lanes = global_lanes["lanes"]
    seen = set()
    for lane_name in doc.get("project_order", []):
        if lane_name in seen:
            raise CatalogError(
                f"{source}: project_order lane '{lane_name}': duplicate lane; "
                "each lane may appear only once"
            )
        seen.add(lane_name)
        if lane_name not in lanes:
            raise CatalogError(
                f"{source}: project_order lane '{lane_name}': lane is not in the "
                "global lane catalog"
            )
        if not lanes[lane_name].get("enabled", True):
            raise CatalogError(
                f"{source}: project_order lane '{lane_name}': lane is globally off; "
                "project_order cannot restore it"
            )

    routing, _sources = merge_routing(
        global_routing,
        doc,
        global_source=global_source,
        project_source=source,
    )
    _validate_merged_routing(
        routing,
        source=f"{source} merged with {global_source}",
    )
    return doc


def effective_routing(cwd=None, config_dir=None, lanes_doc=None, lanes_source=None):
    """Loads global routing, validates it, finds project file from cwd (default current dir),
    validates with partial=True if exists, merges. Returns (routing, sources)."""
    base_dir = os.path.expanduser(config_dir if config_dir is not None else CONFIG_DIR)
    global_path = os.path.join(base_dir, "routing.json")
    global_doc = load_json(global_path)
    validate_routing(global_doc, source=global_path, partial=False)

    git_root = find_git_root(cwd)
    project_path = os.path.join(git_root, ".delegate", "routing.json") if git_root else None

    if project_path and os.path.isfile(project_path):
        project_doc = load_json(project_path)
        validate_routing(project_doc, source=project_path, partial=True)
        if lanes_doc is None and "project_order" in project_doc:
            lanes_source = os.path.join(base_dir, "lanes.json")
            lanes_doc = load_json(lanes_source)
        if lanes_doc is not None:
            validate_project_routing(
                project_doc,
                lanes_doc,
                global_doc,
                source=project_path,
                lanes_source=lanes_source or "lanes.json",
                global_source=global_path,
            )
        routing, sources = merge_routing(
            global_doc,
            project_doc,
            global_source=global_path,
            project_source=project_path,
        )
        _validate_merged_routing(
            routing,
            source=f"{project_path} merged with {global_path}",
        )
        return routing, sources
    routing, sources = merge_routing(
        global_doc,
        None,
        global_source=global_path,
        project_source=None,
    )
    _validate_merged_routing(routing, source=global_path)
    return routing, sources


def _effective_lanes(lanes, routing, sources, lanes_source, project_lanes=None,
                     project_lanes_source=None):
    """Return lane records with the project Tier and the Project order projection.

    A project Tier is applied first, so the Class Range, the Gate, overflow and
    the Order projection below all read the effective Tier (ticket 32). A Lane
    the project moves has no global place in its new Tier, so its `order` goes
    with the move; `project_order` is what can give it one again.
    """
    effective = copy.deepcopy(lanes)
    for lane_name, lane in effective.items():
        if "order" in lane:
            sources[f"lanes.{lane_name}.order"] = lanes_source

    for lane_name, change in project_tier_changes({"lanes": lanes}, project_lanes).items():
        effective[lane_name]["tier"] = change["to"]
        effective[lane_name].pop("order", None)
        sources.pop(f"lanes.{lane_name}.order", None)
        sources[f"lanes.{lane_name}.tier"] = (
            project_lanes_source or "project lanes.json"
        )

    if "project_order" not in routing:
        return effective

    project_source = sources.get("project_order", "project routing.json")
    project_order = routing["project_order"]
    named = set(project_order)

    for tier in range(1, 5):
        named_in_tier = [
            name for name in project_order if effective[name]["tier"] == tier
        ]
        fallback = sorted(
            (
                (name, lane)
                for name, lane in effective.items()
                if lane["tier"] == tier
                and lane.get("enabled", True)
                and name not in named
            ),
            key=lambda item: (
                item[1].get("order") is None,
                item[1].get("order", 0),
                item[0],
            ),
        )
        ordered_names = named_in_tier + [name for name, _lane in fallback]
        for order, lane_name in enumerate(ordered_names, 1):
            effective[lane_name]["order"] = order
            sources[f"lanes.{lane_name}.order"] = (
                project_source if lane_name in named else lanes_source
            )

    return effective


def project_lanes_path(cwd=None):
    """The project lane customization beside the project's routing.json, or None."""
    git_root = find_git_root(cwd)
    if not git_root:
        return None
    path = os.path.join(git_root, ".delegate", "lanes.json")
    return path if os.path.isfile(path) else None


def load_catalog(cwd=None, config_dir=None):
    """Loads and validates lanes and effective routing.
    Returns dict: {"meters": ..., "lanes": ..., "routing": ..., "sources": ..., "files": {...}}."""
    base_dir = os.path.expanduser(config_dir if config_dir is not None else CONFIG_DIR)
    lanes_path = os.path.join(base_dir, "lanes.json")
    routing_path = os.path.join(base_dir, "routing.json")

    lanes_doc = load_json(lanes_path)
    validate_lanes(lanes_doc, source=lanes_path)

    project_lanes_file = project_lanes_path(cwd)
    project_lanes_doc = None
    if project_lanes_file:
        project_lanes_doc = load_json(project_lanes_file)
        validate_project_lanes(
            project_lanes_doc,
            lanes_doc,
            source=project_lanes_file,
            lanes_source=lanes_path,
        )

    routing, sources = effective_routing(
        cwd=cwd,
        config_dir=config_dir,
        lanes_doc=lanes_doc,
        lanes_source=lanes_path,
    )
    lanes = _effective_lanes(
        lanes_doc["lanes"],
        routing,
        sources,
        lanes_path,
        project_lanes=project_lanes_doc,
        project_lanes_source=project_lanes_file,
    )

    git_root = find_git_root(cwd)
    project_path = os.path.join(git_root, ".delegate", "routing.json") if git_root else None
    if project_path and not os.path.isfile(project_path):
        project_path = None

    return {
        "meters": lanes_doc["meters"],
        "lanes": lanes,
        "routing": routing,
        "sources": sources,
        "project_tiers": project_tier_changes(lanes_doc, project_lanes_doc),
        "files": {
            "lanes": lanes_path,
            "routing": routing_path,
            "project": project_path,
            "project_lanes": project_lanes_file,
        },
    }


# --- bulk tier lines: the benchmark page's decisions, pasted (ticket 27) -----

TIER_LINE_VALUES = {"1": 1, "2": 2, "3": 3, "4": 4, "off": "off"}


def parse_tier_lines(text, lanes_doc):
    """Read `<lane> <1-4|off>` lines, as the benchmark page's "Copy as lines"
    writes them. The one parser for the review page's `v` and for
    `setup.py --tiers-from`.

    Returns a dict: `decided` {lane: tier or "off"} in the order first named,
    where the last line for a lane wins; `repeated`, the lanes named more than
    once; `unknown`, names that are no lane in this catalog; `bad`, the line
    numbers that are not a name and one of 1-4 or off; and `refused`, ultra
    lanes a line tried to carry, since an ultra lane is never carried
    (ticket 15). Blank lines are skipped.
    """
    lanes = (lanes_doc or {}).get("lanes") or {}
    out = {"decided": {}, "repeated": [], "unknown": [], "bad": [], "refused": []}
    for number, raw in enumerate((text or "").splitlines(), 1):
        parts = raw.split()
        if not parts:
            continue
        if len(parts) != 2 or parts[1].lower() not in TIER_LINE_VALUES:
            out["bad"].append(number)
            continue
        name, value = parts[0], TIER_LINE_VALUES[parts[1].lower()]
        if name not in lanes:
            if name not in out["unknown"]:
                out["unknown"].append(name)
            continue
        if value != "off" and (lanes[name] or {}).get("effort") == "ultra":
            if name not in out["refused"]:
                out["refused"].append(name)
            continue
        if name in out["decided"] and name not in out["repeated"]:
            out["repeated"].append(name)
        out["decided"][name] = value
    return out


def unnamed_carried(parsed, carried):
    """The carried lanes a set of lines does not name. They go off: "if it's not
    in the tier list, it's not used" (Orin, 2026-09-12; ticket 28).

    Lines that name no lane in the catalog decide nothing, so they switch nothing
    off: a clipboard holding the wrong text must not empty the catalog."""
    if not parsed["decided"]:
        return []
    return [name for name in carried if name not in parsed["decided"]]


def tier_lines_summary(parsed, dropped=()):
    """The one line that says what a set of tier lines did: how many lanes took
    a tier, how many went off by a line, how many carried lanes went off because
    no line named them (`dropped`), then any lane named twice, any name the
    catalog does not know, and any line not read."""
    decided = parsed["decided"]
    tiers = sum(1 for value in decided.values() if value != "off")
    if decided:
        parts = [f"{tiers} took a tier", f"{len(decided) - tiers} went off",
                 f"{len(dropped)} not named, so off"]
    else:
        parts = ["no line names a lane in this catalog, so nothing changed"]
    if parsed["repeated"]:
        parts.append("named twice, last line kept: " + ", ".join(parsed["repeated"]))
    if parsed["unknown"]:
        parts.append("unknown, ignored: " + ", ".join(parsed["unknown"]))
    if parsed["refused"]:
        parts.append("ultra, never carried, ignored: " + ", ".join(parsed["refused"]))
    if parsed["bad"]:
        parts.append("not <lane> <1-4|off>, ignored: line " + ", ".join(str(n) for n in parsed["bad"]))
    return "Lines: " + "; ".join(parts) + "."


def apply_tier_lines_to_doc(lanes_doc, parsed):
    """The prompt-driven interface's form of the same lines: a tier line sets
    the lane's tier and carries it, an off line records it off, and a carried
    lane no line names is recorded off (ticket 28). Returns those lanes."""
    carried = [name for name, lane in lanes_doc["lanes"].items() if lane.get("enabled", True)]
    dropped = unnamed_carried(parsed, carried)
    for name in dropped:
        lanes_doc["lanes"][name]["enabled"] = False
    for name, value in parsed["decided"].items():
        lane = lanes_doc["lanes"][name]
        if value == "off":
            lane["enabled"] = False
        else:
            lane["tier"] = value
            lane.pop("enabled", None)
    return dropped


def write_order_from_lines(lanes_doc, parsed):
    """`--plain` has no review page, so the lines' order inside each tier is the
    order written: each carried lane a line named gets `order`, its place in its
    tier from 1, counted on the tier it holds after the prompts. A lane not
    carried loses any `order` it had. Lines that name no lane change nothing."""
    if not parsed["decided"]:
        return
    placed = {}
    for name in parsed["decided"]:
        lane = lanes_doc["lanes"][name]
        if not lane.get("enabled", True):
            continue
        placed[lane["tier"]] = placed.get(lane["tier"], 0) + 1
        lane["order"] = placed[lane["tier"]]
    for lane in lanes_doc["lanes"].values():
        if not lane.get("enabled", True):
            lane.pop("order", None)


def default_class_guide_path():
    """Shipped Class guide beside this script: ../assets/classes.md."""
    return os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "classes.md")
    )


def _iter_guide_headings(text):
    """Yield (lineno, level, title) for ATX headings outside fenced code."""
    in_fence = None
    for lineno, raw in enumerate(text.splitlines(), 1):
        fence = FENCE_OPEN.match(raw)
        if fence:
            mark = fence.group(1)
            ch, n = mark[0], len(mark)
            if in_fence is None:
                in_fence = (ch, n)
            elif ch == in_fence[0] and n >= in_fence[1]:
                in_fence = None
            continue
        if in_fence is not None:
            continue
        matched = ATX_HEADING.match(raw)
        if not matched:
            continue
        title = re.sub(r"\s+#+\s*$", "", matched.group(2)).strip()
        if not title:
            continue
        yield lineno, len(matched.group(1)), title


def validate_guide_text(text, source="classes.md", overlay=False):
    """Validate Class-guide markdown. Global headings must equal CLASSES;
    overlay headings must be a subset. Metadata headings are any other level."""
    if not isinstance(text, str):
        raise CatalogError(f"{source}: document: class guide must be markdown text")

    decl = FLOOR_CEILING_DECL.search(text)
    if decl:
        line = text.count("\n", 0, decl.start()) + 1
        kind = decl.group(1).lower()
        raise CatalogError(
            f"{source}: line {line}: '{kind}' integer is routing.json policy; "
            "the guide must not declare Floor or Ceiling"
        )

    found = []
    seen = {}
    allowed = ", ".join(CLASSES)
    for lineno, level, title in _iter_guide_headings(text):
        if level != CLASS_GUIDE_HEADING_LEVEL:
            continue
        if title in seen:
            raise CatalogError(
                f"{source}: heading '## {title}': duplicate class section "
                f"(first at line {seen[title]})"
            )
        if title not in CLASSES:
            raise CatalogError(
                f"{source}: heading '## {title}': unknown class; class sections "
                f"must be one of {allowed}"
            )
        seen[title] = lineno
        found.append(title)

    names = tuple(found)
    if overlay:
        return names

    missing = [c for c in CLASSES if c not in seen]
    if missing:
        raise CatalogError(
            f"{source}: classes: missing required class '{missing[0]}'"
        )
    return names


def validate_guide(path, overlay=False):
    """Validate one Class guide file. overlay=True for a project subset."""
    expanded = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(expanded):
        raise CatalogError(f"{path}: file is missing")
    try:
        with open(expanded, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception as e:
        raise CatalogError(f"{path}: file: cannot read: {e}")
    validate_guide_text(text, source=path, overlay=overlay)
    return text


def check_file(path, partial=False):
    """Validates one file. Detects validator from version field."""
    doc = load_json(path)
    if not isinstance(doc, dict) or "version" not in doc:
        raise CatalogError(
            f"{path}: version: missing version; must be one of '{LANES_VERSION}', '{ROUTING_VERSION}'"
        )
    version = doc["version"]
    if version == LANES_VERSION:
        validate_lanes(doc, source=path)
    elif version == ROUTING_VERSION:
        validate_routing(doc, source=path, partial=partial)
    else:
        raise CatalogError(
            f"{path}: version: unknown version {version!r}; must be one of '{LANES_VERSION}', '{ROUTING_VERSION}'"
        )
    return doc


def fmt_file(path, partial=False):
    """Validates like check and rewrites file through write_json."""
    doc = check_file(path, partial=partial)
    write_json(path, doc)
    return doc


def show_catalog(cwd=None, config_dir=None, as_json=False):
    """Prints effective catalog for cwd. If as_json, prints formatted JSON."""
    cat = load_catalog(cwd=cwd, config_dir=config_dir)
    if as_json:
        sys.stdout.write(format_json(cat))
        return

    print("# meters")
    for name, m in cat["meters"].items():
        print(f"{name}  {m['harness']}  {m['plan']}  {m['price_month']}")

    print("\n# lanes")
    sorted_lanes = sorted(
        cat["lanes"].items(),
        key=lambda item: (
            -item[1]["tier"],
            item[1].get("order") is None,
            item[1].get("order", 0),
            item[0],
        ),
    )
    for name, l in sorted_lanes:
        order = l.get("order")
        order_source = cat["sources"].get(f"lanes.{name}.order", "")
        order_text = f"  order={order}  {order_source}" if order is not None else ""
        print(
            f"{name}  {l['tier']}  {l['harness']}  {l['model']}  "
            f"{l['effort']}  {l['meter']}  {l['meter_weight']}  {l['timeout']}  "
            f"{l['basis']}{order_text}"
        )

    project_tiers = cat.get("project_tiers") or {}
    if project_tiers:
        moved = "  ".join(
            f"{name} {change['from']} -> {change['to']}"
            for name, change in sorted(project_tiers.items())
        )
        print(f"\n# project tier in effect: {moved}  "
              f"{cat['files'].get('project_lanes') or ''}")

    print("\n# routing")
    routing = cat["routing"]
    sources = cat["sources"]
    for k in ("version", "margin", "gate"):
        if k in routing:
            src = sources.get(k, "")
            print(f"{k}: {routing[k]}  {src}")
    if "classes" in routing and isinstance(routing["classes"], dict):
        for cls in CLASSES:
            if cls in routing["classes"]:
                c_val = routing["classes"][cls]
                if isinstance(c_val, dict):
                    f_val = c_val.get("floor")
                    c_val_ceil = c_val.get("ceiling")
                    f_src = sources.get(f"classes.{cls}.floor", sources.get(f"classes.{cls}", sources.get("classes", "")))
                    c_src = sources.get(f"classes.{cls}.ceiling", sources.get(f"classes.{cls}", sources.get("classes", "")))
                    if f_src == c_src:
                        print(f"classes.{cls}: floor={f_val} ceiling={c_val_ceil}  {f_src}")
                    else:
                        print(f"classes.{cls}.floor: {f_val}  {f_src}")
                        print(f"classes.{cls}.ceiling: {c_val_ceil}  {c_src}")


HERE_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
_SET_LANE_PREFIX = "lanes."
_SET_LANE_TIER_SUFFIX = ".tier"
_SET_ROUTING_FIELDS = {
    "gate": "routing.gate",
    "margin": "routing.margin",
    "meters": "routing.meters",
    "overflow": "routing.overflow",
}
# The routing switches whose value is a boolean defaulting on, each with the
# reader that says what the merged documents come to.
_BOOL_ROUTING_KEYS = {"meters": meters_enabled, "overflow": overflow_enabled}


def _rank_mod():
    """Load rank.py lazily so catalog import stays one-way at module load."""
    if "rank" in sys.modules:
        return sys.modules["rank"]
    if HERE_SCRIPTS not in sys.path:
        sys.path.insert(0, HERE_SCRIPTS)
    import rank as rank_mod
    return rank_mod


def _present_harnesses(present=None):
    if present is not None:
        return set(present)
    return {h for h in HARNESSES if shutil.which(h)}


def _cached_meters(meters=None):
    if meters is not None:
        return meters
    return _rank_mod().load_cached_usage()


def _loads_strict(content, path):
    """Parse snapshot bytes with the same strict JSON rules as load_json."""
    if content is None:
        if os.path.basename(path) == "lanes.json":
            raise CatalogError(
                f"{path}: file is missing; copy samples/lanes.json there or run /delegate setup"
            )
        raise CatalogError(f"{path}: file is missing")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as e:
        raise CatalogError(f"{path}: file: cannot read: {e}")

    def _reject_constant(c):
        raise ValueError(f"{c} is not allowed in strict JSON")

    try:
        return json.loads(text, parse_constant=_reject_constant)
    except json.JSONDecodeError as e:
        raise CatalogError(
            f"{path}: line {e.lineno}, column {e.colno}: JSON syntax error: {e.msg}"
        )
    except ValueError as e:
        raise CatalogError(f"{path}: number: NaN is not allowed in strict JSON ({e})")


def _describe_source(path):
    abs_path = os.path.abspath(os.path.expanduser(path))
    is_link = os.path.islink(abs_path)
    is_file = os.path.isfile(abs_path)
    resolved = os.path.realpath(abs_path) if (is_link or is_file or os.path.lexists(abs_path)) else None
    content = None
    if is_file:
        try:
            with open(abs_path, "rb") as f:
                content = f.read()
        except OSError as e:
            raise CatalogError(f"{path}: file: cannot read: {e}")
    return {
        "file": abs_path,
        "resolved": resolved,
        "symlink": is_link,
        "exists": is_file,
        "content": content,
    }


def _source_public(desc):
    if desc is None:
        return None
    return {
        "file": desc["file"],
        "resolved": desc["resolved"],
        "symlink": desc["symlink"],
        "exists": desc["exists"],
    }


def _hash_source(hasher, key, desc):
    hasher.update(key.encode("utf-8"))
    hasher.update(b"\0")
    if desc is None:
        hasher.update(b"ABSENT\0")
        return
    hasher.update(desc["file"].encode("utf-8"))
    hasher.update(b"\0")
    hasher.update((desc["resolved"] or "").encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(b"1" if desc["symlink"] else b"0")
    hasher.update(b"\0")
    hasher.update(b"1" if desc["exists"] else b"0")
    hasher.update(b"\0")
    hasher.update(desc["content"] or b"")
    hasher.update(b"\0")


def _source_snapshot(cwd=None, config_dir=None):
    base_dir = os.path.abspath(os.path.expanduser(
        config_dir if config_dir is not None else CONFIG_DIR
    ))
    lanes_path = os.path.join(base_dir, "lanes.json")
    routing_path = os.path.join(base_dir, "routing.json")
    git_root = find_git_root(cwd)
    project_path = (
        os.path.join(git_root, ".delegate", "routing.json") if git_root else None
    )
    project_lanes_file = (
        os.path.join(git_root, ".delegate", "lanes.json") if git_root else None
    )
    lanes = _describe_source(lanes_path)
    routing = _describe_source(routing_path)
    if project_path is None:
        project = None
    else:
        project = _describe_source(project_path)
    if project_lanes_file is None:
        project_lanes = None
    else:
        project_lanes = _describe_source(project_lanes_file)
    hasher = hashlib.sha256()
    _hash_source(hasher, "lanes", lanes)
    _hash_source(hasher, "routing", routing)
    _hash_source(hasher, "project", project)
    _hash_source(hasher, "project_lanes", project_lanes)
    return {
        "lanes": lanes,
        "routing": routing,
        "project": project,
        "project_lanes": project_lanes,
        "git_root": git_root,
        "revision": hasher.hexdigest(),
        "files": {
            "lanes": lanes["file"],
            "routing": routing["file"],
            "project": project["file"] if project is not None else None,
            "project_lanes": (
                project_lanes["file"] if project_lanes is not None else None
            ),
        },
    }


def catalog_revision(cwd=None, config_dir=None):
    """Hash global sources, project presence/content, and resolved paths."""
    return _source_snapshot(cwd=cwd, config_dir=config_dir)["revision"]


def _write_preserving_link(path, doc):
    """Write through a symlink chain so the catalog link itself is not replaced."""
    full_path = os.path.abspath(os.path.expanduser(path))
    dest = full_path
    seen = set()
    while os.path.islink(dest):
        if dest in seen:
            raise CatalogError(f"{path}: symlink loop")
        seen.add(dest)
        link = os.readlink(dest)
        dest = link if os.path.isabs(link) else os.path.abspath(
            os.path.join(os.path.dirname(dest), link)
        )
    write_json(dest, doc)


def _catalog_from_docs(lanes_doc, routing_doc, project_doc, files, project_lanes_doc=None):
    """Effective catalog from already-loaded source documents."""
    lanes_source = files["lanes"]
    routing_source = files["routing"]
    project_source = files.get("project")
    project_lanes_source = files.get("project_lanes")
    validate_lanes(lanes_doc, source=lanes_source)
    if project_lanes_doc is not None:
        validate_project_lanes(
            project_lanes_doc,
            lanes_doc,
            source=project_lanes_source or "project lanes.json",
            lanes_source=lanes_source,
        )
    if project_doc is not None:
        validate_project_routing(
            project_doc,
            lanes_doc,
            routing_doc,
            source=project_source or "project routing.json",
            lanes_source=lanes_source,
            global_source=routing_source,
        )
        routing, sources = merge_routing(
            routing_doc,
            project_doc,
            global_source=routing_source,
            project_source=project_source,
        )
        _validate_merged_routing(
            routing,
            source=f"{project_source} merged with {routing_source}",
        )
    else:
        validate_routing(routing_doc, source=routing_source, partial=False)
        routing, sources = merge_routing(
            routing_doc,
            None,
            global_source=routing_source,
            project_source=None,
        )
        _validate_merged_routing(routing, source=routing_source)
    lanes = _effective_lanes(
        lanes_doc["lanes"],
        routing,
        sources,
        lanes_source,
        project_lanes=project_lanes_doc,
        project_lanes_source=project_lanes_source,
    )
    return {
        "meters": lanes_doc["meters"],
        "lanes": lanes,
        "routing": routing,
        "sources": sources,
        "project_tiers": project_tier_changes(lanes_doc, project_lanes_doc),
        "files": {
            "lanes": lanes_source,
            "routing": routing_source,
            "project": project_source,
            "project_lanes": project_lanes_source,
        },
    }


def _rank_preview(cat, meters_doc, present):
    rank = _rank_mod()
    picks = {}
    for cls in CLASSES:
        rows = rank.rank(cls, cat, meters_doc, present)
        picks[cls] = next((row["lane"] for row in rows if row.get("pick")), None)
    leaders = [
        {"tier": preview["tier"], "leader": preview["leader"]}
        for preview in rank.tier_leaders(cat, meters_doc, present)
    ]
    return picks, leaders


def _observations_report(meters_doc, meter_names):
    rank = _rank_mod()
    observed = rank.meter_observations(meters_doc)
    names = list(meter_names)
    if observed is None:
        return "invalid", sorted(names)
    missing = sorted(name for name in names if name not in observed)
    status = "cached" if observed else "missing"
    return status, missing


def parse_set_field(field):
    """Split an allowed set field on the known prefix and final name, not every dot."""
    if not isinstance(field, str) or not field.strip():
        raise CatalogError("field is required")
    if field in ("routing.gate", "routing.margin", "routing.meters", "routing.overflow"):
        return ("routing", field.split(".", 1)[1])
    if field.startswith("routing.classes."):
        raise CatalogError(
            f"field '{field}' is outside this command's allowlist; "
            "use range CLASS FLOOR CEILING to set Floor and Ceiling together"
        )
    if field.startswith(_SET_LANE_PREFIX) and field.endswith(_SET_LANE_TIER_SUFFIX):
        lane = field[len(_SET_LANE_PREFIX):-len(_SET_LANE_TIER_SUFFIX)]
        if not lane:
            raise CatalogError(f"field '{field}': missing lane name")
        return ("lane_tier", lane)
    if field.startswith(_SET_LANE_PREFIX):
        raise CatalogError(
            f"field '{field}' is outside this command's allowlist; "
            "allowed lane field is lanes.<lane>.tier (global, or project with "
            "--scope project); Order uses the order command and carry is not "
            "editable here"
        )
    raise CatalogError(
        f"unknown field '{field}'; allowed fields are "
        "lanes.<lane>.tier, routing.gate, routing.margin, routing.meters, "
        "routing.overflow"
    )


def _carried_in_tier(lanes, tier):
    names = [
        name for name, lane in lanes.items()
        if lane.get("enabled", True) and lane.get("tier") == tier
    ]
    names.sort(key=lambda name: (
        lanes[name].get("order") is None,
        lanes[name].get("order") or 0,
        name,
    ))
    return names


def _move_in_sequence(names, lane, position):
    if lane not in names:
        raise CatalogError(
            f"lane '{lane}' is not a carried lane in this Tier; "
            "Order is one-based among carried Lanes"
        )
    n = len(names)
    if type(position) is not int or position < 1 or position > n:
        raise CatalogError(
            f"position {position!r} is out of range 1..{n} for this Tier"
        )
    rest = [name for name in names if name != lane]
    rest.insert(position - 1, lane)
    return rest


def _append_order_in_tier(lanes, lane_name, new_tier):
    """Place a lane at the end of the destination Tier's existing Order."""
    names = [name for name in _carried_in_tier(lanes, new_tier) if name != lane_name]
    # Materialize the existing effective Order before appending. An unordered
    # Lane sorts after every numbered Lane, so max(order)+1 is not sufficient.
    for order, name in enumerate(names, 1):
        lanes[name]["order"] = order
    lanes[lane_name]["order"] = len(names) + 1



def _load_docs_from_snapshot(snap):
    lanes_doc = _loads_strict(snap["lanes"]["content"], snap["files"]["lanes"])
    routing_doc = _loads_strict(snap["routing"]["content"], snap["files"]["routing"])
    project_desc = snap["project"]
    if project_desc is None:
        project_doc = None
    elif not project_desc["exists"]:
        project_doc = None
    else:
        project_doc = _loads_strict(project_desc["content"], project_desc["file"])
        validate_routing(project_doc, source=project_desc["file"], partial=True)
    project_lanes_desc = snap["project_lanes"]
    if project_lanes_desc is None or not project_lanes_desc["exists"]:
        project_lanes_doc = None
    else:
        project_lanes_doc = _loads_strict(
            project_lanes_desc["content"], project_lanes_desc["file"]
        )
    validate_lanes(lanes_doc, source=snap["files"]["lanes"])
    validate_routing(routing_doc, source=snap["files"]["routing"], partial=False)
    if project_lanes_doc is not None:
        validate_project_lanes(
            project_lanes_doc,
            lanes_doc,
            source=snap["files"]["project_lanes"],
            lanes_source=snap["files"]["lanes"],
        )
    if project_doc is not None:
        validate_project_routing(
            project_doc,
            lanes_doc,
            routing_doc,
            source=snap["files"]["project"],
            lanes_source=snap["files"]["lanes"],
            global_source=snap["files"]["routing"],
        )
    return lanes_doc, routing_doc, project_doc, project_lanes_doc


# Which file each edit destination writes, and how the project pair is named.
_PROJECT_DESTS = {"project": "routing.json", "project_lanes": "lanes.json"}


def _target_from_scope(snap, scope, dest):
    """dest is 'lanes', 'routing', 'project', or 'project_lanes'."""
    if dest in _PROJECT_DESTS:
        desc = snap[dest]
        if desc is None:
            git_root = snap["git_root"]
            if git_root is None:
                raise CatalogError(
                    f"scope 'project' needs a git root so .delegate/{_PROJECT_DESTS[dest]} "
                    "can be written"
                )
            path = os.path.join(git_root, ".delegate", _PROJECT_DESTS[dest])
            return {
                "file": path,
                "resolved": path,
                "symlink": False,
                "exists": False,
            }
        return _source_public(desc)
    return _source_public(snap[dest])


def _require_scope(scope):
    if scope not in ("global", "project"):
        raise CatalogError("scope must be 'global' or 'project'")
    return scope


def _plan_set(field, value, scope, lanes_doc, routing_doc, project_doc,
              project_lanes_doc=None):
    kind, name = parse_set_field(field)
    if kind == "lane_tier":
        if name not in lanes_doc["lanes"]:
            raise CatalogError(f"lane '{name}' is not in the global lane catalog")
        if type(value) is not int or value < 1 or value > 4:
            raise CatalogError(
                f"lane '{name}': tier must be a whole number from 1 to 4, got {value!r}"
            )
        proposed_lanes = copy.deepcopy(lanes_doc)
        proposed_routing = copy.deepcopy(routing_doc)
        proposed_project = copy.deepcopy(project_doc)
        proposed_project_lanes = copy.deepcopy(project_lanes_doc)
        global_tier = lanes_doc["lanes"][name]["tier"]
        if scope == "global":
            lane = proposed_lanes["lanes"][name]
            old_tier = lane["tier"]
            lane["tier"] = value
            if old_tier != value:
                _append_order_in_tier(proposed_lanes["lanes"], name, value)
            values = {
                "field": f"lanes.{name}.tier",
                "lane": name,
                "original": {
                    "tier": global_tier,
                    "order": lanes_doc["lanes"][name].get("order"),
                },
                "resulting": {
                    "tier": proposed_lanes["lanes"][name]["tier"],
                    "order": proposed_lanes["lanes"][name].get("order"),
                },
            }
            return ("lanes", proposed_lanes, proposed_routing, proposed_project,
                    proposed_project_lanes, values)
        # Project scope: the Tier lives in the project's own lanes file, and a
        # Tier equal to the global one is no customization at all (ticket 32).
        if proposed_project_lanes is None:
            proposed_project_lanes = {}
        entries = dict(proposed_project_lanes.get("lanes") or {})
        original_tier = entries.get(name, {}).get("tier", global_tier)
        if value == global_tier:
            entries.pop(name, None)
        else:
            entry = dict(entries.get(name) or {})
            entry["tier"] = value
            entries[name] = entry
        if entries or "lanes" in proposed_project_lanes:
            proposed_project_lanes["lanes"] = entries
        values = {
            "field": f"lanes.{name}.tier",
            "lane": name,
            "original": {"tier": original_tier, "global": global_tier},
            "resulting": {"tier": value, "global": global_tier},
        }
        return ("project_lanes", proposed_lanes, proposed_routing, proposed_project,
                proposed_project_lanes, values)
    if kind == "routing":
        key = name
        proposed_lanes = copy.deepcopy(lanes_doc)
        proposed_routing = copy.deepcopy(routing_doc)
        proposed_project = copy.deepcopy(project_doc)
        proposed_project_lanes = copy.deepcopy(project_lanes_doc)
        dest = "routing" if scope == "global" else "project"
        write_value = True
        effective_reader = _BOOL_ROUTING_KEYS.get(key)
        if effective_reader is not None:
            if type(value) is not bool:
                raise CatalogError(
                    f"key '{key}': {key} must be a JSON boolean, got {value!r}"
                )
            # A no-op of the default on a legacy document must not add the key.
            if value is True:
                if scope == "global" and key not in routing_doc:
                    write_value = False
                elif scope == "project":
                    global_on = effective_reader(routing_doc)
                    project_has = project_doc is not None and key in project_doc
                    if global_on and not project_has:
                        write_value = False
        if write_value:
            if scope == "global":
                proposed_routing[key] = value
            else:
                if proposed_project is None:
                    proposed_project = {}
                proposed_project[key] = value
        original_global = routing_doc.get(key) if key in routing_doc else None
        original_merged, _sources = merge_routing(routing_doc, project_doc)
        original_effective = (
            effective_reader(original_merged) if effective_reader is not None
            else (
                project_doc.get(key, original_global)
                if project_doc is not None else original_global
            )
        )
        resulting_global = proposed_routing.get(key) if key in proposed_routing else None
        resulting_merged, _sources = merge_routing(proposed_routing, proposed_project)
        resulting_effective = (
            effective_reader(resulting_merged) if effective_reader is not None
            else (
                proposed_project.get(key, resulting_global)
                if proposed_project is not None else resulting_global
            )
        )
        return dest, proposed_lanes, proposed_routing, proposed_project, proposed_project_lanes, {
            "field": _SET_ROUTING_FIELDS[key],
            "original": {"global": original_global, "effective": original_effective},
            "resulting": {"global": resulting_global, "effective": resulting_effective},
        }
    raise CatalogError(f"unknown field '{field}'")


def _plan_range(cls, floor, ceiling, scope, lanes_doc, routing_doc, project_doc,
                project_lanes_doc=None):
    if cls not in CLASSES:
        raise CatalogError(
            f"unknown class '{cls}'; must be one of {', '.join(CLASSES)}"
        )
    if type(floor) is not int or type(ceiling) is not int:
        raise CatalogError(
            f"class '{cls}': floor and ceiling must be integers from 1 to 4"
        )
    proposed_lanes = copy.deepcopy(lanes_doc)
    proposed_routing = copy.deepcopy(routing_doc)
    proposed_project = copy.deepcopy(project_doc)
    proposed_project_lanes = copy.deepcopy(project_lanes_doc)
    dest = "routing" if scope == "global" else "project"
    if scope == "global":
        proposed_routing.setdefault("classes", {})
        proposed_routing["classes"].setdefault(cls, {})
        proposed_routing["classes"][cls]["floor"] = floor
        proposed_routing["classes"][cls]["ceiling"] = ceiling
    else:
        if proposed_project is None:
            proposed_project = {}
        proposed_project.setdefault("classes", {})
        proposed_project["classes"].setdefault(cls, {})
        proposed_project["classes"][cls]["floor"] = floor
        proposed_project["classes"][cls]["ceiling"] = ceiling
    original_global = copy.deepcopy(routing_doc.get("classes", {}).get(cls, {}))
    if project_doc and "classes" in project_doc and cls in project_doc.get("classes", {}):
        original_effective = copy.deepcopy(original_global)
        original_effective.update(project_doc["classes"][cls])
    else:
        original_effective = copy.deepcopy(original_global)
    resulting_global = copy.deepcopy(proposed_routing.get("classes", {}).get(cls, {}))
    if proposed_project and "classes" in proposed_project and cls in proposed_project.get("classes", {}):
        resulting_effective = copy.deepcopy(resulting_global)
        resulting_effective.update(proposed_project["classes"][cls])
    else:
        resulting_effective = copy.deepcopy(resulting_global)
    return dest, proposed_lanes, proposed_routing, proposed_project, proposed_project_lanes, {
        "class": cls,
        "original": {"global": original_global, "effective": original_effective},
        "resulting": {"global": resulting_global, "effective": resulting_effective},
    }


def _plan_order(lane, position, scope, lanes_doc, routing_doc, project_doc, files,
                project_lanes_doc=None):
    if lane not in lanes_doc["lanes"]:
        raise CatalogError(f"lane '{lane}' is not in the global lane catalog")
    if not lanes_doc["lanes"][lane].get("enabled", True):
        raise CatalogError(
            f"lane '{lane}' is globally off; Order is among carried Lanes"
        )
    tier = lanes_doc["lanes"][lane]["tier"]
    proposed_lanes = copy.deepcopy(lanes_doc)
    proposed_routing = copy.deepcopy(routing_doc)
    proposed_project = copy.deepcopy(project_doc)
    proposed_project_lanes = copy.deepcopy(project_lanes_doc)
    if scope == "global":
        current = _carried_in_tier(proposed_lanes["lanes"], tier)
        new_seq = _move_in_sequence(current, lane, position)
        for order, name in enumerate(new_seq, 1):
            proposed_lanes["lanes"][name]["order"] = order
        return ("lanes", proposed_lanes, proposed_routing, proposed_project,
                proposed_project_lanes, {
                    "lane": lane,
                    "tier": tier,
                    "position": {
                        "original": current.index(lane) + 1,
                        "resulting": position,
                    },
                    "sequence": {"original": current, "resulting": new_seq},
                })
    before_cat = _catalog_from_docs(
        lanes_doc, routing_doc, project_doc, files, project_lanes_doc
    )
    # Project Order works inside the effective Tier, which a project Tier may
    # have moved the Lane into (ticket 32).
    tier = before_cat["lanes"][lane]["tier"]
    current = _carried_in_tier(before_cat["lanes"], tier)
    new_seq = _move_in_sequence(current, lane, position)
    existing = list((project_doc or {}).get("project_order", []))
    kept = [
        name for name in existing
        if name in before_cat["lanes"] and before_cat["lanes"][name]["tier"] != tier
    ]
    if proposed_project is None:
        proposed_project = {}
    else:
        proposed_project = copy.deepcopy(proposed_project)
    proposed_project["project_order"] = kept + new_seq
    return ("project", proposed_lanes, proposed_routing, proposed_project,
            proposed_project_lanes, {
                "lane": lane,
                "tier": tier,
                "position": {
                    "original": current.index(lane) + 1,
                    "resulting": position,
                },
                "sequence": {"original": current, "resulting": new_seq},
            })


def _changed_fields(op, values, original_doc, proposed_doc, dest):
    changed = []
    if op == "set":
        field = values.get("field")
        if dest == "lanes":
            lane = values["lane"]
            old = original_doc["lanes"][lane]
            new = proposed_doc["lanes"][lane]
            if old.get("tier") != new.get("tier"):
                changed.append(f"lanes.{lane}.tier")
            for name, proposed_lane in proposed_doc["lanes"].items():
                if original_doc["lanes"][name].get("order") != proposed_lane.get("order"):
                    changed.append(f"lanes.{name}.order")
        elif dest == "project_lanes":
            lane = values["lane"]
            old = (original_doc.get("lanes") or {}).get(lane, {})
            new = (proposed_doc.get("lanes") or {}).get(lane, {})
            if old.get("tier") != new.get("tier"):
                changed.append(f"lanes.{lane}.tier")
        else:
            if field == "routing.gate" and original_doc.get("gate") != proposed_doc.get("gate"):
                changed.append("routing.gate")
            if field == "routing.margin" and original_doc.get("margin") != proposed_doc.get("margin"):
                changed.append("routing.margin")
            if field == "routing.meters" and original_doc.get("meters") != proposed_doc.get("meters"):
                changed.append("routing.meters")
            if field == "routing.overflow" and original_doc.get("overflow") != proposed_doc.get("overflow"):
                changed.append("routing.overflow")
        return changed
    if op == "range":
        cls = values["class"]
        old = (original_doc.get("classes") or {}).get(cls) or {}
        new = (proposed_doc.get("classes") or {}).get(cls) or {}
        if old.get("floor") != new.get("floor"):
            changed.append(f"classes.{cls}.floor")
        if old.get("ceiling") != new.get("ceiling"):
            changed.append(f"classes.{cls}.ceiling")
        return changed
    if op == "order":
        if dest == "project":
            if original_doc.get("project_order") != proposed_doc.get("project_order"):
                changed.append("project_order")
            return changed
        old_lanes = original_doc["lanes"]
        new_lanes = proposed_doc["lanes"]
        for name in sorted(set(old_lanes) | set(new_lanes)):
            if old_lanes.get(name, {}).get("order") != new_lanes.get(name, {}).get("order"):
                changed.append(f"lanes.{name}.order")
        return changed
    return changed


def edit_catalog(
    op,
    *,
    scope,
    cwd=None,
    config_dir=None,
    apply=False,
    expect=None,
    present=None,
    meters=None,
    field=None,
    value=None,
    cls=None,
    floor=None,
    ceiling=None,
    lane=None,
    position=None,
):
    """Preview or apply one focused catalog edit. Public for setup reuse.

    ``meters`` is a cached usage document; omitted means load_cached_usage().
    ``present`` is the harness set; omitted means CLIs found on PATH.
    Applying requires ``expect`` equal to the current source revision.
    """
    scope = _require_scope(scope)
    if op not in ("set", "range", "order"):
        raise CatalogError(f"unknown operation '{op}'")
    if apply and not expect:
        raise CatalogError("--apply requires --expect REVISION")
    if expect and not apply:
        raise CatalogError("--expect is only valid with --apply")

    snap = _source_snapshot(cwd=cwd, config_dir=config_dir)
    if scope == "project" and snap["git_root"] is None:
        raise CatalogError(
            "scope 'project' needs a git root so the .delegate files can be written"
        )
    if apply and snap["revision"] != expect:
        raise CatalogError(
            "intervening edit: source documents or resolved paths changed; preview again"
        )

    lanes_doc, routing_doc, project_doc, project_lanes_doc = _load_docs_from_snapshot(snap)
    files = snap["files"]
    if op == "set":
        (dest, proposed_lanes, proposed_routing, proposed_project,
         proposed_project_lanes, values) = _plan_set(
            field, value, scope, lanes_doc, routing_doc, project_doc, project_lanes_doc
        )
    elif op == "range":
        (dest, proposed_lanes, proposed_routing, proposed_project,
         proposed_project_lanes, values) = _plan_range(
            cls, floor, ceiling, scope, lanes_doc, routing_doc, project_doc,
            project_lanes_doc
        )
    else:
        (dest, proposed_lanes, proposed_routing, proposed_project,
         proposed_project_lanes, values) = _plan_order(
            lane, position, scope, lanes_doc, routing_doc, project_doc, files,
            project_lanes_doc
        )

    # Validate the proposal against the original global documents, then
    # the effective catalog the ranker would see after this one write.
    original_by_dest = {
        "lanes": lanes_doc,
        "routing": routing_doc,
        "project": project_doc if project_doc is not None else {},
        "project_lanes": project_lanes_doc if project_lanes_doc is not None else {},
    }
    proposed_by_dest = {
        "lanes": proposed_lanes,
        "routing": proposed_routing,
        "project": proposed_project if proposed_project is not None else {},
        "project_lanes": (
            proposed_project_lanes if proposed_project_lanes is not None else {}
        ),
    }

    # The proposal is validated before anything else is computed from it.
    after_cat = _catalog_from_docs(
        proposed_lanes, proposed_routing, proposed_project, files,
        proposed_project_lanes
    )
    before_cat = _catalog_from_docs(
        lanes_doc, routing_doc, project_doc, files, project_lanes_doc
    )
    present_set = _present_harnesses(present)
    meters_doc = _cached_meters(meters)
    picks_before, leaders_before = _rank_preview(before_cat, meters_doc, present_set)
    picks_after, leaders_after = _rank_preview(after_cat, meters_doc, present_set)
    observations, missing = _observations_report(meters_doc, before_cat["meters"])
    unavailable = sorted(h for h in HARNESSES if h not in present_set)

    changed = _changed_fields(
        op,
        values,
        original_by_dest[dest],
        proposed_by_dest[dest],
        dest,
    )
    noop = proposed_by_dest[dest] == original_by_dest[dest]
    if dest == "project" and project_doc is None:
        noop = proposed_project in (None, {})
        if proposed_project:
            noop = False
    # An empty customization over an absent file writes no empty file.
    if dest == "project_lanes" and project_lanes_doc is None:
        noop = not (proposed_project_lanes or {}).get("lanes")

    target = _target_from_scope(snap, scope, dest)
    written = False
    if apply and not noop:
        if _source_snapshot(cwd=cwd, config_dir=config_dir)["revision"] != snap["revision"]:
            raise CatalogError(
                "intervening edit: source documents or resolved paths changed; preview again"
            )
        write_doc = proposed_by_dest[dest]
        _write_preserving_link(target["file"], write_doc)
        written = True

    return {
        "op": op,
        "scope": scope,
        "revision": snap["revision"],
        "target": target,
        "sources": {
            "lanes": _source_public(snap["lanes"]),
            "routing": _source_public(snap["routing"]),
            "project": _source_public(snap["project"]),
            "project_lanes": _source_public(snap["project_lanes"]),
        },
        "values": values,
        "changed": changed,
        "picks": {"before": picks_before, "after": picks_after},
        "leaders": {"before": leaders_before, "after": leaders_after},
        "unavailable_harnesses": unavailable,
        "missing_observations": missing,
        "observations": observations,
        "noop": noop,
        "written": written,
    }


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser(
        prog="catalog.py",
        description="Delegate catalog and routing management."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_show = sub.add_parser("show", help="show effective catalog")
    p_show.add_argument("--cwd", default=None, help="working directory to find git root from")
    p_show.add_argument("--config-dir", default=None, help="config directory containing lanes.json and routing.json")
    p_show.add_argument("--json", action="store_true", help="output effective catalog as formatted JSON")

    p_check = sub.add_parser("check", help="validate a catalog or routing file")
    p_check.add_argument("file", help="path to file to check")
    p_check.add_argument("--partial", action="store_true", help="allow partial routing file")

    p_guide = sub.add_parser("check-guide", help="validate a class guide")
    p_guide.add_argument(
        "file",
        nargs="?",
        default=None,
        help="path to classes.md (default: this skill's assets/classes.md)",
    )
    p_guide.add_argument(
        "--overlay",
        action="store_true",
        help="project overlay: class sections must be a subset of CLASSES",
    )

    p_fmt = sub.add_parser("fmt", help="format and validate a catalog or routing file")
    p_fmt.add_argument("file", help="path to file to format")
    p_fmt.add_argument("--partial", action="store_true", help="allow partial routing file")

    def add_edit_flags(p):
        p.add_argument(
            "--scope",
            required=True,
            choices=("global", "project"),
            help="which source document to change",
        )
        p.add_argument("--cwd", default=None, help="working directory to find git root from")
        p.add_argument(
            "--config-dir",
            default=None,
            help="config directory containing lanes.json and routing.json",
        )
        p.add_argument("--apply", action="store_true", help="write the selected source document")
        p.add_argument("--expect", default=None, help="revision from a preview of the same sources")

    p_set = sub.add_parser("set", help="preview or apply one allowed field edit")
    p_set.add_argument(
        "field",
        help="lanes.<lane>.tier, routing.gate, routing.margin, routing.meters, "
             "or routing.overflow",
    )
    p_set.add_argument("value", help="JSON value")
    add_edit_flags(p_set)

    p_range = sub.add_parser("range", help="preview or apply a paired Floor and Ceiling")
    p_range.add_argument("cls", metavar="CLASS", help="class name")
    p_range.add_argument("floor", type=int, help="new floor")
    p_range.add_argument("ceiling", type=int, help="new ceiling")
    add_edit_flags(p_range)

    p_order = sub.add_parser("order", help="preview or apply a one-based Order in a Tier")
    p_order.add_argument("lane", help="carried lane name")
    p_order.add_argument("position", type=int, help="one-based position among carried lanes in the Tier")
    add_edit_flags(p_order)

    args = parser.parse_args(argv)

    try:
        if args.cmd == "show":
            show_catalog(cwd=args.cwd, config_dir=args.config_dir, as_json=args.json)
        elif args.cmd == "check":
            doc = check_file(args.file, partial=args.partial)
            # Coverage warnings, never failures: a valid catalog can still
            # leave a Tier resting on one Meter (ticket 29). They go to stderr
            # so that `ok: <file>` stays the whole of this command's stdout.
            for line in meter_dependency_lines(doc.get("lanes"), names=True):
                sys.stderr.write(f"warning: {line}\n")
            print(f"ok: {args.file}")
        elif args.cmd == "check-guide":
            guide_path = args.file if args.file is not None else default_class_guide_path()
            validate_guide(guide_path, overlay=args.overlay)
            print(f"ok: {guide_path}")
        elif args.cmd == "fmt":
            fmt_file(args.file, partial=args.partial)
            print(f"formatted: {args.file}")
        elif args.cmd in ("set", "range", "order"):
            kwargs = {
                "scope": args.scope,
                "cwd": args.cwd,
                "config_dir": args.config_dir,
                "apply": args.apply,
                "expect": args.expect,
            }
            if args.cmd == "set":
                def _reject_constant(c):
                    raise ValueError(f"{c} is not allowed in strict JSON")
                try:
                    value = json.loads(args.value, parse_constant=_reject_constant)
                except json.JSONDecodeError as e:
                    raise CatalogError(
                        f"value is not strict JSON: {e.msg} at column {e.colno}"
                    )
                except ValueError as e:
                    raise CatalogError(f"value is not strict JSON: {e}")
                result = edit_catalog("set", field=args.field, value=value, **kwargs)
            elif args.cmd == "range":
                result = edit_catalog(
                    "range", cls=args.cls, floor=args.floor, ceiling=args.ceiling, **kwargs
                )
            else:
                result = edit_catalog(
                    "order", lane=args.lane, position=args.position, **kwargs
                )
            sys.stdout.write(format_json(result))
    except CatalogError as e:
        sys.stderr.write(f"catalog: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
