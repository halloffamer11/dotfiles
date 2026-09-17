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
  catalog.py check FILE [--partial]
  catalog.py check-guide [FILE] [--overlay]
  catalog.py fmt FILE [--partial]
"""
import argparse
import copy
import json
import os
import re
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

    allowed_top = {"version", "classes", "margin", "gate", "note"}
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


def _effective_lanes(lanes, routing, sources, lanes_source):
    """Return lane records with the canonical Project order projection."""
    effective = copy.deepcopy(lanes)
    for lane_name, lane in effective.items():
        if "order" in lane:
            sources[f"lanes.{lane_name}.order"] = lanes_source

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


def load_catalog(cwd=None, config_dir=None):
    """Loads and validates lanes and effective routing.
    Returns dict: {"meters": ..., "lanes": ..., "routing": ..., "sources": ..., "files": {...}}."""
    base_dir = os.path.expanduser(config_dir if config_dir is not None else CONFIG_DIR)
    lanes_path = os.path.join(base_dir, "lanes.json")
    routing_path = os.path.join(base_dir, "routing.json")

    lanes_doc = load_json(lanes_path)
    validate_lanes(lanes_doc, source=lanes_path)

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
        "files": {
            "lanes": lanes_path,
            "routing": routing_path,
            "project": project_path,
        },
    }


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

    args = parser.parse_args(argv)

    try:
        if args.cmd == "show":
            show_catalog(cwd=args.cwd, config_dir=args.config_dir, as_json=args.json)
        elif args.cmd == "check":
            check_file(args.file, partial=args.partial)
            print(f"ok: {args.file}")
        elif args.cmd == "check-guide":
            guide_path = args.file if args.file is not None else default_class_guide_path()
            validate_guide(guide_path, overlay=args.overlay)
            print(f"ok: {guide_path}")
        elif args.cmd == "fmt":
            fmt_file(args.file, partial=args.partial)
            print(f"formatted: {args.file}")
    except CatalogError as e:
        sys.stderr.write(f"catalog: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
