#!/usr/bin/env python3
"""catalog.py — lane catalog and routing configuration for delegate.

Manages the catalog of execution lanes (harness x model x meter) and the
routing policy mapping task classes to minimum model tiers.

Locations:
  CONFIG_DIR = ~/.config/delegate (expanded at call time)
  global lanes:    <CONFIG_DIR>/lanes.json
  global routing:  <CONFIG_DIR>/routing.json
  project routing: <git-root>/.delegate/routing.json

CLI forms:
  catalog.py show [--cwd DIR] [--config-dir DIR] [--json]
  catalog.py check FILE [--partial]
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
EFFORTS = ("low", "medium", "high", "xhigh")
CLASSES = ("scout", "mechanical", "impl", "review", "hard-impl")
LANES_VERSION = "delegate-lanes.v1"
ROUTING_VERSION = "delegate-routing.v1"


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
        "price", "tier", "basis", "note"
    }
    required_lane_fields = (
        "harness", "model", "effort", "meter", "meter_weight", "timeout",
        "price", "tier", "basis"
    )
    price_keys = ("in", "cache_read", "cache_write", "out")

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

        if not isinstance(lane["basis"], str):
            raise CatalogError(f"{source}: lane '{lane_name}': basis must be a string")

        if "note" in lane and not isinstance(lane["note"], str):
            raise CatalogError(f"{source}: lane '{lane_name}': note must be a string")

    return doc


def validate_routing(doc, source="routing.json", partial=False):
    """Validates a routing document. If partial=False (global file), all required keys
    and all classes must be present. If partial=True (project override), keys are optional.
    Returns doc or raises CatalogError."""
    if not isinstance(doc, dict):
        raise CatalogError(f"{source}: document: must be a JSON object")

    allowed_top = {"version", "classTier", "margin", "gate", "note"}
    for k in doc:
        if k not in allowed_top:
            raise CatalogError(
                f"{source}: key '{k}': unknown top-level key; allowed keys are {', '.join(sorted(allowed_top))}"
            )

    if not partial:
        for req in ("version", "classTier", "margin", "gate"):
            if req not in doc:
                raise CatalogError(f"{source}: key '{req}': missing required top-level key")

    if "version" in doc and doc["version"] != ROUTING_VERSION:
        raise CatalogError(
            f"{source}: key 'version': must equal '{ROUTING_VERSION}', got {doc['version']!r}"
        )

    if "classTier" in doc:
        ct = doc["classTier"]
        if not isinstance(ct, dict):
            raise CatalogError(f"{source}: key 'classTier': classTier must be an object")
        if not partial:
            for c in CLASSES:
                if c not in ct:
                    raise CatalogError(f"{source}: classTier: missing required class '{c}'")
        for cls_name, cls_tier in ct.items():
            if cls_name not in CLASSES:
                raise CatalogError(f"{source}: classTier: unknown class '{cls_name}'")
            if type(cls_tier) is not int or cls_tier < 1 or cls_tier > 4:
                raise CatalogError(
                    f"{source}: classTier: class '{cls_name}': tier must be an integer from 1 to 4, got {cls_tier!r}"
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

    if "note" in doc and not isinstance(doc["note"], str):
        raise CatalogError(f"{source}: key 'note': note must be a string")

    return doc


def merge_routing(global_doc, project_doc=None, global_source="routing.json", project_source=None):
    """Merges global routing and optional project routing.
    Each top-level key in project_doc replaces global value, except classTier which merges per class.
    Returns (routing, sources)."""
    g_src = global_source
    p_src = project_source

    routing = copy.deepcopy(global_doc)
    sources = {}
    for k in global_doc:
        sources[k] = g_src
    if "classTier" in global_doc and isinstance(global_doc["classTier"], dict):
        for c in global_doc["classTier"]:
            sources[f"classTier.{c}"] = g_src

    if project_doc:
        for k, v in project_doc.items():
            if k == "classTier" and isinstance(v, dict):
                if "classTier" not in routing or not isinstance(routing["classTier"], dict):
                    routing["classTier"] = {}
                for c, tier in v.items():
                    routing["classTier"][c] = tier
                    sources[f"classTier.{c}"] = p_src
                sources["classTier"] = p_src
            else:
                routing[k] = copy.deepcopy(v)
                sources[k] = p_src

    return routing, sources


def effective_routing(cwd=None, config_dir=None):
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
        return merge_routing(
            global_doc,
            project_doc,
            global_source=global_path,
            project_source=project_path,
        )
    return merge_routing(
        global_doc,
        None,
        global_source=global_path,
        project_source=None,
    )


def load_catalog(cwd=None, config_dir=None):
    """Loads and validates lanes and effective routing.
    Returns dict: {"meters": ..., "lanes": ..., "routing": ..., "sources": ..., "files": {...}}."""
    base_dir = os.path.expanduser(config_dir if config_dir is not None else CONFIG_DIR)
    lanes_path = os.path.join(base_dir, "lanes.json")
    routing_path = os.path.join(base_dir, "routing.json")

    lanes_doc = load_json(lanes_path)
    validate_lanes(lanes_doc, source=lanes_path)

    routing, sources = effective_routing(cwd=cwd, config_dir=config_dir)

    git_root = find_git_root(cwd)
    project_path = os.path.join(git_root, ".delegate", "routing.json") if git_root else None
    if project_path and not os.path.isfile(project_path):
        project_path = None

    return {
        "meters": lanes_doc["meters"],
        "lanes": lanes_doc["lanes"],
        "routing": routing,
        "sources": sources,
        "files": {
            "lanes": lanes_path,
            "routing": routing_path,
            "project": project_path,
        },
    }


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
        key=lambda item: (-item[1]["tier"], item[0]),
    )
    for name, l in sorted_lanes:
        print(
            f"{name}  {l['tier']}  {l['harness']}  {l['model']}  "
            f"{l['effort']}  {l['meter']}  {l['meter_weight']}  {l['timeout']}  {l['basis']}"
        )

    print("\n# routing")
    routing = cat["routing"]
    sources = cat["sources"]
    for k in ("version", "margin", "gate"):
        if k in routing:
            src = sources.get(k, "")
            print(f"{k}: {routing[k]}  {src}")
    if "classTier" in routing and isinstance(routing["classTier"], dict):
        for cls in CLASSES:
            if cls in routing["classTier"]:
                src = sources.get(f"classTier.{cls}", sources.get("classTier", ""))
                print(f"classTier.{cls}: {routing['classTier'][cls]}  {src}")


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
        elif args.cmd == "fmt":
            fmt_file(args.file, partial=args.partial)
            print(f"formatted: {args.file}")
    except CatalogError as e:
        sys.stderr.write(f"catalog: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
