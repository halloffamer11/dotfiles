#!/usr/bin/env python3
"""test_catalog.py — unit and CLI tests for catalog.py. Run: python3 tests/test_catalog.py"""
import copy
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

# Run from a fresh directory with no Git root above it, so that
# `catalog.find_git_root()` never finds the invoking checkout's own
# `.delegate/routing.json`. Every path this file needs comes from HERE.
_ISOLATED_CWD = tempfile.TemporaryDirectory(prefix="delegate-test-")
os.chdir(_ISOLATED_CWD.name)
DELEGATE_DIR = os.path.abspath(os.path.join(HERE, "..", "scripts"))
SAMPLES_DIR = os.path.abspath(os.path.join(HERE, "..", "assets", "samples"))
CATALOG_PY = os.path.join(DELEGATE_DIR, "catalog.py")

sys.path.insert(0, DELEGATE_DIR)
import catalog
import rank

fails = 0


def record(name, ok, detail=""):
    global fails
    if ok:
        print(f"PASS {name}")
    else:
        fails += 1
        print(f"FAIL {name}: {detail}")


def check_catalog_error(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
        return None
    except catalog.CatalogError as e:
        return str(e)


# Load base samples
lanes_sample = catalog.load_json(os.path.join(SAMPLES_DIR, "lanes.json"))
routing_sample = catalog.load_json(os.path.join(SAMPLES_DIR, "routing.json"))

# 1. Samples validate
try:
    catalog.validate_lanes(lanes_sample)
    record("samples validate_lanes", True)
except Exception as e:
    record("samples validate_lanes", False, str(e))

try:
    catalog.validate_routing(routing_sample)
    record("samples validate_routing", True)
except Exception as e:
    record("samples validate_routing", False, str(e))

# 1b. show on config-dir holding samples exits 0 and names every lane and meter
res = subprocess.run(
    [sys.executable, CATALOG_PY, "show", "--config-dir", SAMPLES_DIR],
    capture_output=True,
    text=True,
)
all_meters_present = all(m in res.stdout for m in lanes_sample["meters"])
all_lanes_present = all(l in res.stdout for l in lanes_sample["lanes"])
record(
    "show exits 0 and names every lane and meter",
    res.returncode == 0 and all_meters_present and all_lanes_present,
    f"code={res.returncode}, meters={all_meters_present}, lanes={all_lanes_present}",
)

# 1c. show --json parses
res_json = subprocess.run(
    [sys.executable, CATALOG_PY, "show", "--config-dir", SAMPLES_DIR, "--json"],
    capture_output=True,
    text=True,
)
try:
    parsed = json.loads(res_json.stdout)
    has_keys = all(k in parsed for k in ("meters", "lanes", "routing", "sources", "files"))
    record("show --json parses", res_json.returncode == 0 and has_keys)
except Exception as e:
    record("show --json parses", False, str(e))

# 1d. enabled field: absent defaults to true, explicit true and false are valid
doc_absent = copy.deepcopy(lanes_sample)
doc_absent["lanes"]["fable-xhigh@claude"].pop("enabled", None)
val_absent = catalog.validate_lanes(doc_absent)
record(
    "enabled absent defaults true",
    val_absent is not None and doc_absent["lanes"]["fable-xhigh@claude"].get("enabled", True) is True,
)

doc_true = copy.deepcopy(lanes_sample)
doc_true["lanes"]["fable-xhigh@claude"]["enabled"] = True
val_true = catalog.validate_lanes(doc_true)
record(
    "enabled true is valid",
    val_true is not None and doc_true["lanes"]["fable-xhigh@claude"].get("enabled", True) is True,
)

doc_false = copy.deepcopy(lanes_sample)
doc_false["lanes"]["fable-xhigh@claude"]["enabled"] = False
val_false = catalog.validate_lanes(doc_false)
record(
    "enabled false is valid",
    val_false is not None and doc_false["lanes"]["fable-xhigh@claude"].get("enabled", True) is False,
)

# 1d2. order field (ticket 28): optional; a whole number from 1 is valid, and
#      anything else is refused with a message naming the lane and the rule
doc_order = copy.deepcopy(lanes_sample)
doc_order["lanes"]["fable-xhigh@claude"]["order"] = 1
doc_order["lanes"]["sol-high@codex"]["order"] = 12
record("order absent is valid", catalog.validate_lanes(copy.deepcopy(lanes_sample)) is not None
       and not any("order" in lane for lane in lanes_sample["lanes"].values()))
record("order 1 and 12 are valid", catalog.validate_lanes(doc_order) is not None)
for bad in (0, -1, 1.5, 2.0, "1", True, None, [1]):
    doc_bad = copy.deepcopy(lanes_sample)
    doc_bad["lanes"]["sol-high@codex"]["order"] = bad
    err = check_catalog_error(catalog.validate_lanes, doc_bad)
    record(
        f"order {bad!r} is refused naming the lane and the rule",
        err is not None and "lane 'sol-high@codex'" in err
        and "order is the lane's place inside its tier and must be a whole number from 1 up" in err
        and repr(bad) in err,
        repr(err),
    )
with tempfile.TemporaryDirectory() as _td_order:
    _bad_path = os.path.join(_td_order, "lanes.json")
    _doc = copy.deepcopy(lanes_sample)
    _doc["lanes"]["sol-high@codex"]["order"] = 0
    catalog.write_json(_bad_path, _doc)
    _res = subprocess.run([sys.executable, CATALOG_PY, "check", _bad_path], capture_output=True, text=True)
    _ok_path = os.path.join(_td_order, "ok", "lanes.json")
    catalog.write_json(_ok_path, doc_order)
    _res_ok = subprocess.run([sys.executable, CATALOG_PY, "check", _ok_path], capture_output=True, text=True)
    record("check refuses a bad order in plain language and accepts a good one",
           _res.returncode == 1 and "order" in _res.stderr and "sol-high@codex" in _res.stderr
           and _res_ok.returncode == 0 and _res_ok.stdout.startswith("ok"),
           _res.stderr + _res_ok.stdout)

# 1e. lane at each of the six efforts validates. codex is the harness that
#     offers all six; the fixture used a claude lane until ticket 19, and claude
#     offers no ultra.
for eff in ("low", "medium", "high", "xhigh", "max", "ultra"):
    doc_eff = copy.deepcopy(lanes_sample)
    doc_eff["lanes"]["sol-high@codex"]["effort"] = eff
    val_eff = catalog.validate_lanes(doc_eff)
    record(
        f"effort {eff} validates",
        val_eff is not None and doc_eff["lanes"]["sol-high@codex"]["effort"] == eff,
    )

# 1e2. a lane at an effort its harness does not offer is refused, and the
#      message names that harness's list (ticket 19)
for lane_name, eff, offered in (
    ("fable-xhigh@claude", "ultra", "low, medium, high, xhigh, max"),
    ("flash-high@agy", "xhigh", "low, medium, high"),
    ("grok46-high@grok", "low", "high"),
):
    doc_eff = copy.deepcopy(lanes_sample)
    doc_eff["lanes"][lane_name]["effort"] = eff
    harness = lane_name.split("@")[1]
    msg = check_catalog_error(catalog.validate_lanes, doc_eff)
    record(
        f"reject: {harness} lane at effort {eff}, naming what {harness} offers",
        bool(msg and lane_name in msg and f"does not offer effort '{eff}'" in msg
             and f"{harness} offers {offered}" in msg),
        msg,
    )
record(
    "every harness has an effort list, each inside EFFORTS",
    set(catalog.HARNESS_EFFORTS) == set(catalog.HARNESSES)
    and all(set(v) <= set(catalog.EFFORTS) and v for v in catalog.HARNESS_EFFORTS.values()),
    str(catalog.HARNESS_EFFORTS),
)

# 1f. the stowed catalog carries the three native claude lanes and validates
import json as _json
import os as _os
_stowed_path = _os.path.abspath(_os.path.join(
    _os.path.dirname(__file__), "..", "..", "..", "..",
    "stow", "delegate", ".config", "delegate", "lanes.json"))
with open(_stowed_path, encoding="utf-8") as _f:
    _stowed = _json.load(_f)
record("stowed catalog validates", catalog.validate_lanes(copy.deepcopy(_stowed)) is not None)
for lane_name in ("haiku-high@claude", "sonnet-high@claude", "opus-high@claude"):
    record(
        f"native lane {lane_name} present in the stowed catalog",
        lane_name in _stowed["lanes"] and _stowed["lanes"][lane_name]["meter"] == "claude-general",
    )

# 1g. ticket 19: Fable, Opus and Sonnet at every effort claude offers, each lane
#     on its model's own meter, and every claude lane with its lane-* agent file
_by_model = {}
for _name, _lane in _stowed["lanes"].items():
    _by_model.setdefault((_lane["harness"], _lane["model"]), {})[_lane["effort"]] = (_name, _lane)
for _model in ("claude-fable-5-1", "claude-opus-5", "claude-sonnet-5"):
    _lanes = _by_model.get(("claude", _model), {})
    record(
        f"stowed catalog runs {_model} at every effort claude offers, on one meter",
        set(_lanes) == set(catalog.HARNESS_EFFORTS["claude"])
        and len({l["meter"] for _n, l in _lanes.values()}) == 1,
        str({e: (n, l["meter"]) for e, (n, l) in _lanes.items()}),
    )
record(
    "stowed catalog runs gemini-3.8-flash at every effort agy offers, the effort in the slug",
    {e: l["model"] for e, (_n, l) in
     {**_by_model.get(("agy", "gemini-3.8-flash-low"), {}),
      **_by_model.get(("agy", "gemini-3.8-flash-medium"), {}),
      **_by_model.get(("agy", "gemini-3.8-flash-high"), {})}.items()}
    == {e: f"gemini-3.8-flash-{e}" for e in catalog.HARNESS_EFFORTS["agy"]},
)
_agents_dir = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "..", "..", "agents"))
_missing = []
for _name, _lane in _stowed["lanes"].items():
    if _lane["harness"] != "claude":
        continue
    _path = _os.path.join(_agents_dir, "lane-" + _name.split("@")[0] + ".md")
    if not _os.path.isfile(_path):
        _missing.append(f"{_name}: no {_path}")
        continue
    with open(_path, encoding="utf-8") as _f:
        _front = _f.read().split("---")[1]
    _fields = dict(line.split(": ", 1) for line in _front.strip().splitlines() if ": " in line)
    # Haiku takes no effort, so its agent file names none (ticket 22)
    if _fields.get("model") != _lane["model"] or _fields.get("effort", _lane["effort"]) != _lane["effort"]:
        _missing.append(f"{_name}: {_fields}")
record("every claude lane in the stowed catalog has a lane-* agent file with its model and effort",
       not _missing, str(_missing))

# 2. Rejections
# 2.1 lane naming a missing meter
doc = copy.deepcopy(lanes_sample)
doc["lanes"]["fable-xhigh@claude"]["meter"] = "ghost-meter"
msg = check_catalog_error(catalog.validate_lanes, doc)
record(
    "reject: missing meter",
    bool(msg and "fable-xhigh@claude" in msg and "ghost-meter" in msg and "missing meter" in msg),
    msg,
)

# 2.2 lane whose meter belongs to another harness
doc = copy.deepcopy(lanes_sample)
doc["lanes"]["fable-xhigh@claude"]["meter"] = "codex"
msg = check_catalog_error(catalog.validate_lanes, doc)
record(
    "reject: meter belongs to another harness",
    bool(msg and "fable-xhigh@claude" in msg and "codex" in msg and "harness" in msg),
    msg,
)

# 2.3 tier 0 and tier 5
doc = copy.deepcopy(lanes_sample)
doc["lanes"]["fable-xhigh@claude"]["tier"] = 0
msg0 = check_catalog_error(catalog.validate_lanes, doc)
doc["lanes"]["fable-xhigh@claude"]["tier"] = 5
msg5 = check_catalog_error(catalog.validate_lanes, doc)
record(
    "reject: tier 0 and tier 5",
    bool(msg0 and "fable-xhigh@claude" in msg0 and "tier" in msg0 and "1 to 4" in msg0 and
         msg5 and "fable-xhigh@claude" in msg5 and "tier" in msg5 and "1 to 4" in msg5),
    f"{msg0} | {msg5}",
)

# 2.4 a leftover trust key is rejected as an unknown field (removed 2026-09-10)
doc = copy.deepcopy(lanes_sample)
doc["lanes"]["fable-xhigh@claude"]["trust"] = 5
msg = check_catalog_error(catalog.validate_lanes, doc)
record(
    "reject: leftover trust key",
    bool(msg and "fable-xhigh@claude" in msg and "unknown field" in msg and "trust" in msg),
    f"{msg}",
)

# 2.5 tier given as true
doc = copy.deepcopy(lanes_sample)
doc["lanes"]["fable-xhigh@claude"]["tier"] = True
msg = check_catalog_error(catalog.validate_lanes, doc)
record(
    "reject: tier given as true",
    bool(msg and "fable-xhigh@claude" in msg and "tier" in msg and "1 to 4" in msg),
    msg,
)

# 2.6 unknown top-level key in lanes
doc = copy.deepcopy(lanes_sample)
doc["unknown_key"] = "bad"
msg = check_catalog_error(catalog.validate_lanes, doc)
record(
    "reject: unknown top-level key in lanes",
    bool(msg and "unknown_key" in msg and "unknown top-level key" in msg),
    msg,
)

# 2.7 unknown lane field
doc = copy.deepcopy(lanes_sample)
doc["lanes"]["fable-xhigh@claude"]["extra_prop"] = True
msg = check_catalog_error(catalog.validate_lanes, doc)
record(
    "reject: unknown lane field",
    bool(msg and "fable-xhigh@claude" in msg and "extra_prop" in msg and "unknown field" in msg),
    msg,
)

# 2.8 unknown meter field
doc = copy.deepcopy(lanes_sample)
doc["meters"]["codex"]["extra_meter_prop"] = 123
msg = check_catalog_error(catalog.validate_lanes, doc)
record(
    "reject: unknown meter field",
    bool(msg and "codex" in msg and "extra_meter_prop" in msg and "unknown field" in msg),
    msg,
)

# 2.9 unknown price key
doc = copy.deepcopy(lanes_sample)
doc["lanes"]["fable-xhigh@claude"]["price"]["invalid_token"] = 1
msg = check_catalog_error(catalog.validate_lanes, doc)
record(
    "reject: unknown price key",
    bool(msg and "fable-xhigh@claude" in msg and "invalid_token" in msg and "unknown key" in msg),
    msg,
)

# 2.10 bad timeout "25"
doc = copy.deepcopy(lanes_sample)
doc["lanes"]["fable-xhigh@claude"]["timeout"] = "25"
msg = check_catalog_error(catalog.validate_lanes, doc)
record(
    "reject: bad timeout '25'",
    bool(msg and "fable-xhigh@claude" in msg and "timeout" in msg and "^[0-9]+[smh]$" in msg),
    msg,
)

# 2.11 missing required lane field
doc = copy.deepcopy(lanes_sample)
del doc["lanes"]["fable-xhigh@claude"]["model"]
msg = check_catalog_error(catalog.validate_lanes, doc)
record(
    "reject: missing required lane field",
    bool(msg and "fable-xhigh@claude" in msg and "model" in msg and "missing required field" in msg),
    msg,
)

# 2.12 wrong version
doc_l = copy.deepcopy(lanes_sample)
doc_l["version"] = "bad-lanes.v1"
msg_l = check_catalog_error(catalog.validate_lanes, doc_l)
doc_r = copy.deepcopy(routing_sample)
doc_r["version"] = "bad-routing.v1"
msg_r = check_catalog_error(catalog.validate_routing, doc_r)
record(
    "reject: wrong version",
    bool(msg_l and "version" in msg_l and "must equal" in msg_l and
         msg_r and "version" in msg_r and "must equal" in msg_r),
    f"{msg_l} | {msg_r}",
)

# 2.13 bad JSON syntax (message has line and column)
with tempfile.TemporaryDirectory() as td:
    bad_syntax_path = os.path.join(td, "bad_syntax.json")
    with open(bad_syntax_path, "w") as f:
        f.write('{"test": \n  invalid}')
    msg = check_catalog_error(catalog.load_json, bad_syntax_path)
    record(
        "reject: bad JSON syntax",
        bool(msg and "line" in msg and "column" in msg and "syntax error" in msg),
        msg,
    )

# 2.14 NaN in a number
with tempfile.TemporaryDirectory() as td:
    nan_path = os.path.join(td, "nan.json")
    with open(nan_path, "w") as f:
        f.write('{"val": NaN}')
    msg = check_catalog_error(catalog.load_json, nan_path)
    record(
        "reject: NaN in a number",
        bool(msg and "number" in msg and "NaN" in msg),
        msg,
    )

# 2.15 unknown class in classes
doc = copy.deepcopy(routing_sample)
doc["classes"]["invalid_class"] = {"floor": 1, "ceiling": 2}
msg = check_catalog_error(catalog.validate_routing, doc)
record(
    "reject: unknown class in classes",
    bool(msg and "invalid_class" in msg and "unknown class" in msg),
    msg,
)

# 2.16 class ceiling 5
doc = copy.deepcopy(routing_sample)
doc["classes"]["scout"]["ceiling"] = 5
msg = check_catalog_error(catalog.validate_routing, doc)
record(
    "reject: class tier 5",
    bool(msg and "scout" in msg and "ceiling" in msg and "1 to 4" in msg),
    msg,
)

# 2.16b floor > ceiling rejected
doc = copy.deepcopy(routing_sample)
doc["classes"]["scout"]["floor"] = 4
doc["classes"]["scout"]["ceiling"] = 2
msg = check_catalog_error(catalog.validate_routing, doc)
record(
    "reject: floor exceeds ceiling",
    bool(msg and "scout" in msg and "cannot exceed" in msg),
    msg,
)

# 2.16c legacy key rejected with migration message
legacy_key = "class" + "Tier"
doc_legacy = {"version": "delegate-routing.v1", legacy_key: {"scout": 2}, "margin": 0.2, "gate": 0.1}
msg_legacy = check_catalog_error(catalog.validate_routing, doc_legacy)
record(
    "reject: legacy key with migration message",
    bool(msg_legacy and legacy_key in msg_legacy and "replaced by 'classes'" in msg_legacy and "floor" in msg_legacy and "ceiling" in msg_legacy),
    msg_legacy,
)

# 2.17 margin 1.5
doc = copy.deepcopy(routing_sample)
doc["margin"] = 1.5
msg = check_catalog_error(catalog.validate_routing, doc)
record(
    "reject: margin 1.5",
    bool(msg and "margin" in msg and "between 0 and 1" in msg),
    msg,
)

# 2.18 lane name not ending in @<harness>
doc = copy.deepcopy(lanes_sample)
data = doc["lanes"].pop("flash-high@agy")
doc["lanes"]["flash-high"] = data
msg = check_catalog_error(catalog.validate_lanes, doc)
record(
    "reject: lane name not ending in @<harness>",
    bool(msg and "flash-high" in msg and "lane name must end with" in msg and "@agy" in msg),
    msg,
)

# 2.19 reject: enabled as non-boolean
for bad_val, label in [("true", 'string "true"'), ("false", 'string "false"'), (1, "int 1"), (0, "int 0")]:
    doc_bad = copy.deepcopy(lanes_sample)
    doc_bad["lanes"]["fable-xhigh@claude"]["enabled"] = bad_val
    msg = check_catalog_error(catalog.validate_lanes, doc_bad)
    record(
        f"reject: enabled as {label}",
        bool(msg and "fable-xhigh@claude" in msg and "enabled" in msg and "boolean" in msg),
        msg,
    )

# 2.20 reject: invalid effort
doc_bad_eff = copy.deepcopy(lanes_sample)
doc_bad_eff["lanes"]["fable-xhigh@claude"]["effort"] = "super"
msg_eff = check_catalog_error(catalog.validate_lanes, doc_bad_eff)
record(
    "reject: invalid effort",
    bool(msg_eff and "fable-xhigh@claude" in msg_eff and "effort must be one of" in msg_eff and "got 'super'" in msg_eff),
    msg_eff,
)

# 3. Override merge
with tempfile.TemporaryDirectory() as td:
    cfg_dir = os.path.join(td, "cfg")
    os.makedirs(cfg_dir)
    g_file = os.path.join(cfg_dir, "routing.json")
    catalog.write_json(g_file, routing_sample)

    fake_git = os.path.join(td, "fake_repo")
    os.makedirs(fake_git)
    open(os.path.join(fake_git, ".git"), "w").close()

    p_dir = os.path.join(fake_git, ".delegate")
    p_file = os.path.join(p_dir, "routing.json")
    catalog.write_json(p_file, {"classes": {"scout": {"floor": 3}}})

    r1, s1 = catalog.effective_routing(cwd=fake_git, config_dir=cfg_dir)
    scout_ok = (
        r1["classes"]["scout"]["floor"] == 3 and
        r1["classes"]["scout"]["ceiling"] == routing_sample["classes"]["scout"]["ceiling"] and
        s1["classes.scout.floor"] == p_file and
        s1["classes.scout.ceiling"] == g_file and
        r1["margin"] == 0.2 and
        s1["margin"] == g_file and
        r1["gate"] == 0.1 and
        s1["gate"] == g_file and
        all(r1["classes"][c] == routing_sample["classes"][c] for c in ("mechanical", "impl", "review", "hard-impl"))
    )
    record("override merge: classes scout floor keeps global ceiling", scout_ok)

    # Margin override
    catalog.write_json(p_file, {"margin": 0.5})
    r2, s2 = catalog.effective_routing(cwd=fake_git, config_dir=cfg_dir)
    margin_ok = (
        r2["margin"] == 0.5 and
        s2["margin"] == p_file and
        r2["classes"]["scout"] == routing_sample["classes"]["scout"] and
        s2["classes.scout.floor"] == g_file
    )
    record("override merge: margin only", margin_ok)

    # No git root
    no_git = os.path.join(td, "no_git_dir")
    os.makedirs(no_git)
    r3, s3 = catalog.effective_routing(cwd=no_git, config_dir=cfg_dir)
    no_git_ok = (
        r3["classes"]["scout"] == routing_sample["classes"]["scout"] and
        s3["classes.scout.floor"] == g_file and
        s3["margin"] == g_file
    )
    record("override merge: no git root", no_git_ok)

# 4. note accepted on all levels and ignored in show/routing
with tempfile.TemporaryDirectory() as td:
    l_doc = copy.deepcopy(lanes_sample)
    l_doc["note"] = "top-level lane note"
    l_doc["meters"]["codex"]["note"] = "meter note"
    l_doc["lanes"]["sol-high@codex"]["note"] = "lane note"
    l_valid = (catalog.validate_lanes(l_doc) is not None)

    r_doc = copy.deepcopy(routing_sample)
    r_doc["note"] = "top-level routing note"
    r_valid = (catalog.validate_routing(r_doc) is not None)

    cfg_dir = os.path.join(td, "cfg")
    os.makedirs(cfg_dir)
    catalog.write_json(os.path.join(cfg_dir, "lanes.json"), l_doc)
    catalog.write_json(os.path.join(cfg_dir, "routing.json"), r_doc)

    fake_git = os.path.join(td, "repo")
    os.makedirs(fake_git)
    open(os.path.join(fake_git, ".git"), "w").close()
    p_dir = os.path.join(fake_git, ".delegate")
    catalog.write_json(os.path.join(p_dir, "routing.json"), {"note": "project note override"})

    eff_r, _ = catalog.effective_routing(cwd=fake_git, config_dir=cfg_dir)
    # Check note carried but routing logic unchanged
    note_logic_ok = (
        eff_r["note"] == "project note override" and
        eff_r["margin"] == routing_sample["margin"] and
        eff_r["classes"] == routing_sample["classes"]
    )

    buf = io.StringIO()
    old_out = sys.stdout
    sys.stdout = buf
    try:
        catalog.show_catalog(cwd=fake_git, config_dir=cfg_dir)
    finally:
        sys.stdout = old_out
    show_out = buf.getvalue()
    note_ignored_in_show = (
        "top-level lane note" not in show_out and
        "meter note" not in show_out and
        "lane note" not in show_out and
        "top-level routing note" not in show_out and
        "project note override" not in show_out
    )
    record("note accepted and ignored", l_valid and r_valid and note_logic_ok and note_ignored_in_show)

# 5. write_json round-trip, indentation, idempotence, fmt
with tempfile.TemporaryDirectory() as td:
    fpath = os.path.join(td, "catalog.json")
    catalog.write_json(fpath, lanes_sample)
    with open(fpath, "r", encoding="utf-8") as f:
        text1 = f.read()

    has_2space = '  "version":' in text1
    has_single_newline = text1.endswith("\n") and not text1.endswith("\n\n")
    loaded = catalog.load_json(fpath)
    roundtrip_ok = (loaded == lanes_sample and has_2space and has_single_newline)
    record("write_json round-trip", roundtrip_ok)

    # Writing twice gives identical bytes
    catalog.write_json(fpath, lanes_sample)
    with open(fpath, "r", encoding="utf-8") as f:
        text2 = f.read()
    record("write_json idempotence", text1 == text2)

    # fmt on minified
    min_path = os.path.join(td, "minified.json")
    min_content = json.dumps(lanes_sample, separators=(",", ":"))
    with open(min_path, "w", encoding="utf-8") as f:
        f.write(min_content)

    res_fmt = subprocess.run([sys.executable, CATALOG_PY, "fmt", min_path], capture_output=True, text=True)
    with open(min_path, "rb") as f:
        fmt_bytes = f.read()
    expected_bytes = catalog.format_json(lanes_sample).encode("utf-8")
    record(
        "fmt minified file",
        res_fmt.returncode == 0 and res_fmt.stdout.strip() == f"formatted: {min_path}" and fmt_bytes == expected_bytes,
    )

# 6. check CLI
# Sample file
res_check = subprocess.run(
    [sys.executable, CATALOG_PY, "check", os.path.join(SAMPLES_DIR, "lanes.json")],
    capture_output=True,
    text=True,
)
record(
    "check CLI sample file",
    res_check.returncode == 0 and res_check.stdout.strip() == f"ok: {os.path.join(SAMPLES_DIR, 'lanes.json')}",
)

# Broken file
with tempfile.TemporaryDirectory() as td:
    broken_file = os.path.join(td, "broken.json")
    with open(broken_file, "w") as f:
        f.write('{"version": "delegate-lanes.v1", "broken_key": 1}')
    res_broken = subprocess.run(
        [sys.executable, CATALOG_PY, "check", broken_file],
        capture_output=True,
        text=True,
    )
    record(
        "check CLI broken file",
        res_broken.returncode == 1 and "catalog: " in res_broken.stderr,
    )

    # No version file
    no_ver_file = os.path.join(td, "no_version.json")
    with open(no_ver_file, "w") as f:
        f.write('{"data": 123}')
    res_no_ver = subprocess.run(
        [sys.executable, CATALOG_PY, "check", no_ver_file],
        capture_output=True,
        text=True,
    )
    record(
        "check CLI no version file",
        res_no_ver.returncode == 1 and
        "catalog: " in res_no_ver.stderr and
        "delegate-lanes.v1" in res_no_ver.stderr and
        "delegate-routing.v1" in res_no_ver.stderr,
    )

# 7. published_as: the local mapping from a leaderboard's display name to a lane model
#    (ticket 16). Sources publish "GPT-6 Astra" or "Fable 5.1"; the catalog keys on
#    slugs. The derived rule covers formatting; published_as covers the rest.

pub_ok = copy.deepcopy(lanes_sample)
pub_ok["lanes"]["fable-xhigh@claude"]["published_as"] = ["Fable 5.1", "Claude Fable 5.1"]
record(
    "7.1 published_as list of names is accepted",
    check_catalog_error(catalog.validate_lanes, pub_ok) is None,
)

for bad, tag in (
    ("Fable 5.1", "a bare string"),
    ([], "an empty list"),
    (["Fable 5.1", ""], "an empty entry"),
    (["Fable 5.1", 5], "a non-string entry"),
    (["Fable 5.1", "  "], "a blank entry"),
):
    doc = copy.deepcopy(lanes_sample)
    doc["lanes"]["fable-xhigh@claude"]["published_as"] = bad
    msg = check_catalog_error(catalog.validate_lanes, doc)
    record(
        f"7.2 published_as rejects {tag}",
        bool(msg and "fable-xhigh@claude" in msg and "published_as" in msg),
        msg,
    )

conflict = copy.deepcopy(lanes_sample)
conflict["lanes"]["fable-xhigh@claude"]["published_as"] = ["Fable 5.1"]
conflict["lanes"]["sol-high@codex"]["published_as"] = ["fable 5.1"]
msg = check_catalog_error(catalog.validate_lanes, conflict)
record(
    "7.3 one published name claimed by two models is rejected",
    bool(msg and "Fable 5.1" in msg and "claude-fable-5-1" in msg and "gpt-5.6-sol" in msg),
    msg,
)

shared = copy.deepcopy(lanes_sample)
shared["lanes"]["sol-low@codex"] = copy.deepcopy(shared["lanes"]["sol-high@codex"])
shared["lanes"]["sol-low@codex"]["effort"] = "low"
shared["lanes"]["sol-high@codex"]["published_as"] = ["GPT-5.6 Sol"]
shared["lanes"]["sol-low@codex"]["published_as"] = ["GPT-5.6 Sol"]
record(
    "7.4 the same name on two lanes of one model is accepted",
    check_catalog_error(catalog.validate_lanes, shared) is None,
)

# 7.5 resolution: what the pre-screen asks of the catalog
resolve = catalog.resolve_published_model
astra = copy.deepcopy(lanes_sample)
astra["lanes"]["astra-high@codex"] = copy.deepcopy(astra["lanes"]["sol-high@codex"])
astra["lanes"]["astra-high@codex"]["model"] = "gpt-6-astra"
astra["lanes"]["fable-xhigh@claude"]["published_as"] = ["Fable 5.1"]
cases = (
    ("GPT-6 Astra", "gpt-6-astra", "a display name differing only in case and separators"),
    ("gpt-6-astra", "gpt-6-astra", "a slug already in catalog form"),
    ("GPT-5.6 Sol", "gpt-5.6-sol", "a display name whose dot is a separator"),
    ("Gemini 3.8 Flash", "gemini-3.8-flash-high", "a lane model carrying an effort suffix"),
    ("Fable 5.1", "claude-fable-5-1", "a published_as entry"),
    ("fable  5.1", "claude-fable-5-1", "a published_as entry, loosely typed"),
    ("GLM-5.3", None, "a model that is nobody's lane"),
    ("", None, "an empty name"),
    (None, None, "no name at all"),
)
for name, want, tag in cases:
    got = resolve(name, astra)
    record(f"7.5 resolve {tag}", got == want, f"{name!r} -> {got!r}, wanted {want!r}")

ambiguous = copy.deepcopy(lanes_sample)
ambiguous["lanes"]["flash-medium@agy"] = copy.deepcopy(ambiguous["lanes"]["flash-high@agy"])
ambiguous["lanes"]["flash-medium@agy"]["effort"] = "medium"
ambiguous["lanes"]["flash-medium@agy"]["model"] = "gemini-3.8-flash-medium"
record(
    "7.6 a name two lane models could denote resolves to neither",
    resolve("Gemini 3.8 Flash", ambiguous) is None,
    repr(resolve("Gemini 3.8 Flash", ambiguous)),
)
record(
    "7.6b an agy family name resolves by the row's effort, and to neither at an effort no member runs",
    resolve("Gemini 3.8 Flash", ambiguous, effort="medium") == "gemini-3.8-flash-medium"
    and resolve("Gemini 3.8 Flash", ambiguous, effort="high") == "gemini-3.8-flash-high"
    and resolve("Gemini 3.8 Flash", ambiguous, effort="low") is None,
    repr([resolve("Gemini 3.8 Flash", ambiguous, effort=e) for e in ("medium", "high", "low")]),
)

# 7.7 A published_as entry may not be pointed at a model another lane runs: the
#     explicit map is consulted first, so such an entry would silently read that
#     lane's rows as this one's — its own numbers would then switch it off as
#     dominated while the real lane read "no rows". Both spellings of the
#     collision are rejected: the model slug itself, and the display name that
#     denotes it.
for entry, tag in (
    ("gpt-5.6-luna", "another lane's model slug"),
    ("Gemini 3.8 Flash", "a display name another lane's model already answers to"),
):
    doc = copy.deepcopy(lanes_sample)
    doc["lanes"]["sol-high@codex"]["published_as"] = [entry]
    msg = check_catalog_error(catalog.validate_lanes, doc)
    record(
        f"7.7 published_as rejects {tag}",
        bool(msg and "sol-high@codex" in msg and "gpt-5.6-sol" in msg
             and ("gpt-5.6-luna" in msg or "gemini-3.8-flash-high" in msg)),
        msg,
    )

own = copy.deepcopy(lanes_sample)
own["lanes"]["flash-high@agy"]["published_as"] = ["Gemini 3.8 Flash", "gemini-3.8-flash-high"]
record(
    "7.7 a lane may spell out its own model",
    check_catalog_error(catalog.validate_lanes, own) is None,
)

record(
    "7.7 an entry the derived rule cannot reach still resolves",
    resolve("Fable 5.1", {"lanes": {
        "a@codex": {"model": "gpt-6-astra", "effort": "high"},
        "b@claude": {"model": "claude-fable-5-1", "effort": "xhigh",
                     "published_as": ["Fable 5.1"]},
    }}) == "claude-fable-5-1",
)

record(
    "7.8 every effort strips as a suffix, longest first",
    [catalog.strip_effort_suffix(f"m-{e}") for e in catalog.EFFORTS]
    == [("m", e) for e in catalog.EFFORTS]
    and catalog.strip_effort_suffix("gpt-6-astra-xhigh") == ("gpt-6-astra", "xhigh")
    and catalog.strip_effort_suffix("gpt-6-astra") == ("gpt-6-astra", None),
    str([catalog.strip_effort_suffix(f"m-{e}") for e in catalog.EFFORTS]),
)

# The published name is reconciled against the lane's model, reaching past an
# effort suffix the *catalog* carries (gemini-3.8-flash-high). A suffix on the
# *published* side is left alone on purpose: a row states its effort in its own
# field, and reading `gpt-6-astra-max` as plain `gpt-6-astra` would let a name
# and a field disagree with nobody noticing. The row's own `effort` field is
# what separates agy family members (7.6b).
record(
    "7.8 a suffix on the published side is not silently dropped",
    resolve("gpt-6-astra-max", {"lanes": {
        "a@codex": {"model": "gpt-6-astra", "effort": "high"},
    }}) is None
    and resolve("Gemini 3.8 Flash", {"lanes": {
        "a@agy": {"model": "gemini-3.8-flash-high", "effort": "high"},
    }}) == "gemini-3.8-flash-high",
)

# 7.9 ticket 19: every Claude name an accepted rows file prints resolves to the
#     lane model it denotes in the stowed catalog, and a Claude model that is
#     nobody's lane resolves to none. A new Claude name in the rows fails here
#     until someone decides which it is.
_data_dir = _os.path.abspath(_os.path.join(
    _os.path.dirname(__file__), "..", "..", "..", "..", ".scratch", "delegate-redesign", "_data"))
_claude_names = {
    "Claude Fable 5.1": "claude-fable-5-1", "Fable 5.1": "claude-fable-5-1",
    "Claude Opus 5": "claude-opus-5", "Opus 5": "claude-opus-5", "claude-opus-5": "claude-opus-5",
    "Claude Sonnet 5": "claude-sonnet-5", "Sonnet 5": "claude-sonnet-5",
    "claude-sonnet-5": "claude-sonnet-5",
    "Claude 4.5 Haiku": "claude-haiku-4-5-20251001",
    # other versions, which no lane runs
    "Claude Fable 5": None, "Fable 5": None, "Claude Opus 4.8": None, "Opus 4.8": None,
    "Claude Sonnet 4.6": None,
}
_seen = set()
for _file in ("aa-accepted.json", "tbench-accepted.json", "swerb-accepted.json"):
    _p = _os.path.join(_data_dir, _file)
    if _os.path.isfile(_p):
        with open(_p, encoding="utf-8") as _f:
            _seen |= {r["model"] for r in _json.load(_f)
                      if any(w in r["model"].lower() for w in ("claude", "fable", "opus", "sonnet", "haiku"))}
_wrong = {n: resolve(n, _stowed) for n in _claude_names if resolve(n, _stowed) != _claude_names[n]}
record(
    "7.9 every Claude name in the accepted rows resolves to its lane model, and other versions to none",
    _seen and _seen <= set(_claude_names) and not _wrong,
    f"unaccounted={sorted(_seen - set(_claude_names))} wrong={_wrong}",
)


# 8. Ticket 04: Project order is a project-only overlay on global Order.
project_order_doc = {
    "project_order": ["terra-high@codex", "flash-high@agy", "sol-high@codex"],
}
record(
    "8.1 a flat partial Project order spanning Tiers validates",
    check_catalog_error(
        catalog.validate_project_routing,
        project_order_doc,
        copy.deepcopy(lanes_sample),
        copy.deepcopy(routing_sample),
    ) is None,
)

for bad, tag in (
    ("terra-high@codex", "a string instead of a list"),
    ({"2": ["terra-high@codex"]}, "Tier-keyed object"),
    (["terra-high@codex", 7], "non-string lane"),
    (["terra-high@codex", ""], "empty lane name"),
):
    bad_doc = {"project_order": bad}
    msg = check_catalog_error(catalog.validate_routing, bad_doc, partial=True)
    record(
        f"8.2 Project order rejects {tag}",
        bool(msg and "project_order" in msg and "flat list" in msg),
        msg,
    )

global_project_order = copy.deepcopy(routing_sample)
global_project_order["project_order"] = ["terra-high@codex"]
msg = check_catalog_error(catalog.validate_routing, global_project_order)
record(
    "8.2 Project order is rejected in global routing",
    bool(msg and "project_order" in msg and "project-only" in msg),
    msg,
)

for bad_order, lane_name, rule in (
    (["terra-high@codex", "terra-high@codex"], "terra-high@codex", "duplicate"),
    (["not-a-lane@codex"], "not-a-lane@codex", "global lane catalog"),
):
    msg = check_catalog_error(
        catalog.validate_project_routing,
        {"project_order": bad_order},
        copy.deepcopy(lanes_sample),
        copy.deepcopy(routing_sample),
    )
    record(
        f"8.3 Project order rejects {rule}",
        bool(msg and lane_name in msg and rule in msg),
        msg,
    )

off_lanes = copy.deepcopy(lanes_sample)
off_lanes["lanes"]["terra-high@codex"]["enabled"] = False
msg = check_catalog_error(
    catalog.validate_project_routing,
    {"project_order": ["terra-high@codex"]},
    off_lanes,
    copy.deepcopy(routing_sample),
)
record(
    "8.3 Project order cannot restore a globally off lane",
    bool(msg and "terra-high@codex" in msg and "globally off" in msg),
    msg,
)

# The partial project document is valid by itself, but the merged Class is not.
msg = check_catalog_error(
    catalog.validate_project_routing,
    {"classes": {"scout": {"floor": 4}}},
    copy.deepcopy(lanes_sample),
    copy.deepcopy(routing_sample),
)
record(
    "8.4 public project validation rejects a merged floor above the global ceiling",
    bool(msg and "scout" in msg and "floor (4) cannot exceed ceiling (3)" in msg),
    msg,
)

with tempfile.TemporaryDirectory() as td:
    cfg_dir = os.path.join(td, "cfg")
    os.makedirs(cfg_dir)
    global_lanes = copy.deepcopy(lanes_sample)
    global_lanes["lanes"]["terra-high@codex"]["order"] = 1
    global_lanes["lanes"]["grok46-high@grok"]["order"] = 2
    global_lanes["lanes"]["fable-xhigh@claude"]["enabled"] = False
    global_lanes["lanes"]["fable-xhigh@claude"]["order"] = 7

    # Two catalog additions without Order prove the final fallback is by lane name.
    global_lanes["lanes"]["terra-low@codex"] = copy.deepcopy(
        global_lanes["lanes"]["terra-high@codex"]
    )
    global_lanes["lanes"]["terra-low@codex"]["effort"] = "low"
    global_lanes["lanes"]["terra-low@codex"].pop("order")
    global_lanes["lanes"]["luna-high@codex"] = copy.deepcopy(
        global_lanes["lanes"]["luna-low@codex"]
    )
    global_lanes["lanes"]["luna-high@codex"]["effort"] = "high"
    global_lanes["lanes"]["luna-high@codex"]["tier"] = 2
    global_lanes["lanes"]["luna-high@codex"].pop("order", None)

    lanes_path = os.path.join(cfg_dir, "lanes.json")
    routing_path = os.path.join(cfg_dir, "routing.json")
    catalog.write_json(lanes_path, global_lanes)
    catalog.write_json(routing_path, routing_sample)

    project_dir = os.path.join(td, "fixture-project")
    os.makedirs(os.path.join(project_dir, ".delegate"))
    open(os.path.join(project_dir, ".git"), "w").close()
    project_path = os.path.join(project_dir, ".delegate", "routing.json")

    before = catalog.load_catalog(cwd=project_dir, config_dir=cfg_dir)
    before_orders = {
        name: lane.get("order") for name, lane in before["lanes"].items()
    }
    record(
        "8.5 no Project order leaves global lane records unchanged",
        before["lanes"] == global_lanes["lanes"]
        and before_orders["terra-high@codex"] == 1
        and before_orders["grok46-high@grok"] == 2
        and before_orders["luna-high@codex"] is None,
    )

    catalog.write_json(project_path, {
        "project_order": ["grok46-high@grok", "flash-high@agy"],
        "note": "unrelated project key survives",
    })
    effective = catalog.load_catalog(cwd=project_dir, config_dir=cfg_dir)
    tier2 = sorted(
        (
            (lane["order"], name)
            for name, lane in effective["lanes"].items()
            if lane["tier"] == 2
        )
    )
    record(
        "8.6 named lanes precede global-Order and name fallbacks inside each Tier",
        tier2 == [
            (1, "grok46-high@grok"),
            (2, "terra-high@codex"),
            (3, "luna-high@codex"),
            (4, "terra-low@codex"),
        ],
        repr(tier2),
    )
    record(
        "8.6 effective Order has field sources and cannot change Tier or enabled",
        effective["sources"]["lanes.grok46-high@grok.order"] == project_path
        and effective["sources"]["lanes.terra-high@codex.order"] == lanes_path
        and effective["lanes"]["grok46-high@grok"]["tier"]
            == global_lanes["lanes"]["grok46-high@grok"]["tier"]
        and effective["lanes"]["grok46-high@grok"].get("enabled", True)
            == global_lanes["lanes"]["grok46-high@grok"].get("enabled", True)
        and effective["lanes"]["fable-xhigh@claude"]["enabled"] is False
        and effective["lanes"]["fable-xhigh@claude"]["order"] == 7
        and effective["sources"]["lanes.fable-xhigh@claude.order"] == lanes_path,
    )

    show = io.StringIO()
    old_out = sys.stdout
    sys.stdout = show
    try:
        catalog.show_catalog(cwd=project_dir, config_dir=cfg_dir)
    finally:
        sys.stdout = old_out
    show_text = show.getvalue()
    record(
        "8.7 show displays each effective Order source",
        "grok46-high@grok" in show_text
        and f"order=1  {project_path}" in show_text
        and f"order=2  {lanes_path}" in show_text,
        show_text,
    )

    # Reload the fixture after the project write: both public ranking projections
    # must consume the one effective catalog rather than applying an overlay again.
    present = set(catalog.HARNESSES)
    before_pick = next(r["lane"] for r in rank.rank("impl", before, {}, present) if r["pick"])
    before_tier2 = rank.tier_leaders(before, {}, present)[1]["leader"]
    after_pick = next(r["lane"] for r in rank.rank("impl", effective, {}, present) if r["pick"])
    previews = rank.tier_leaders(effective, {}, present)
    record(
        "8.8 reloaded fixture changes Class ranking and the Tier leader through the public seam",
        before_pick == "terra-high@codex"
        and before_tier2 == "terra-high@codex"
        and after_pick == "grok46-high@grok"
        and [p["tier"] for p in previews] == [1, 2, 3, 4]
        and previews[1]["leader"] == "grok46-high@grok",
        repr((before_pick, before_tier2, after_pick, previews[1]["leader"])),
    )

    catalog.write_json(project_path, 42)
    error = check_catalog_error(
        catalog.effective_routing, cwd=project_dir, config_dir=cfg_dir
    )
    record(
        "8.9 malformed project document raises a catalog error at the routing boundary",
        error is not None and "must be a JSON object" in error,
        str(error),
    )


# 9. Ticket 10: Class guide headings vs CLASSES; overlay is a subset.
GUIDE_PATH = os.path.abspath(os.path.join(HERE, "..", "assets", "classes.md"))


def class_guide(names, extra="", prefix="# Class guide\n\n# How to pick\n\nPick one Class.\n"):
    body = prefix
    for name in names:
        body += f"\n## {name}\n\n### Intent\n\nA {name} job.\n"
    return body + extra


try:
    catalog.validate_guide(GUIDE_PATH)
    record("9.1 shipped class guide validates as global", True)
except Exception as e:
    record("9.1 shipped class guide validates as global", False, str(e))

res_guide = subprocess.run(
    [sys.executable, CATALOG_PY, "check-guide", GUIDE_PATH],
    capture_output=True,
    text=True,
)
record(
    "9.1b check-guide CLI shipped file",
    res_guide.returncode == 0 and res_guide.stdout.strip() == f"ok: {GUIDE_PATH}",
    res_guide.stdout + res_guide.stderr,
)

res_guide_default = subprocess.run(
    [sys.executable, CATALOG_PY, "check-guide"],
    capture_output=True,
    text=True,
)
record(
    "9.1c check-guide default path is the shipped guide",
    res_guide_default.returncode == 0
    and res_guide_default.stdout.strip() == f"ok: {catalog.default_class_guide_path()}"
    and os.path.samefile(catalog.default_class_guide_path(), GUIDE_PATH),
    res_guide_default.stdout + res_guide_default.stderr,
)

record(
    "9.1d metadata headings are not Class sections",
    catalog.validate_guide_text(class_guide(catalog.CLASSES)) == catalog.CLASSES,
)

msg = check_catalog_error(
    catalog.validate_guide_text,
    "# Class guide\n\n## How to pick\n\n" + class_guide(catalog.CLASSES, prefix=""),
)
record(
    "9.1e a ## metadata heading is an unknown class",
    bool(msg and "How to pick" in msg and "unknown class" in msg),
    msg,
)

with tempfile.TemporaryDirectory() as td:
    overlay_path = os.path.join(td, "classes.md")
    with open(overlay_path, "w", encoding="utf-8") as f:
        f.write(class_guide(("scout", "impl")))
    try:
        names = catalog.validate_guide_text(
            class_guide(("scout", "impl")), overlay=True
        )
        catalog.validate_guide(overlay_path, overlay=True)
        overlay_ok = names == ("scout", "impl")
    except Exception as e:
        overlay_ok = False
        names = e
    res_overlay = subprocess.run(
        [sys.executable, CATALOG_PY, "check-guide", overlay_path, "--overlay"],
        capture_output=True,
        text=True,
    )
    res_as_global = subprocess.run(
        [sys.executable, CATALOG_PY, "check-guide", overlay_path],
        capture_output=True,
        text=True,
    )
    record(
        "9.2 overlay subset of CLASSES is accepted",
        overlay_ok
        and res_overlay.returncode == 0
        and res_overlay.stdout.strip() == f"ok: {overlay_path}",
        repr(names) + res_overlay.stdout + res_overlay.stderr,
    )
    record(
        "9.2b overlay as global is missing required classes",
        res_as_global.returncode == 1
        and "missing required class" in res_as_global.stderr,
        res_as_global.stderr,
    )

    empty_overlay = os.path.join(td, "empty.md")
    with open(empty_overlay, "w", encoding="utf-8") as f:
        f.write("# How to pick\n\nProject note only.\n")
    record(
        "9.2c overlay with no Class sections is an empty subset",
        check_catalog_error(catalog.validate_guide, empty_overlay, overlay=True) is None,
    )

msg = check_catalog_error(
    catalog.validate_guide_text,
    class_guide(("scout", "knowledge-scout", "impl")),
    overlay=True,
)
record(
    "9.3 overlay unknown class is rejected",
    bool(msg and "knowledge-scout" in msg and "unknown class" in msg),
    msg,
)

partial = [c for c in catalog.CLASSES if c != "review"]
msg = check_catalog_error(catalog.validate_guide_text, class_guide(partial))
record(
    "9.4 global missing Class section is rejected",
    bool(msg and "missing required class 'review'" in msg),
    msg,
)

msg = check_catalog_error(
    catalog.validate_guide_text,
    class_guide(catalog.CLASSES) + "\n## scout\n\nAgain.\n",
)
record(
    "9.5 duplicate Class section is rejected",
    bool(msg and "duplicate class section" in msg and "## scout" in msg),
    msg,
)

msg = check_catalog_error(
    catalog.validate_guide_text,
    class_guide(catalog.CLASSES, extra="\n### Default\n\nfloor: 2\n"),
)
record(
    "9.6 floor integer declaration is rejected",
    bool(msg and "floor" in msg and "routing.json" in msg and "line " in msg),
    msg,
)

msg = check_catalog_error(
    catalog.validate_guide_text,
    class_guide(("scout",), extra="\nCeiling = 3\n"),
    overlay=True,
)
record(
    "9.6b overlay ceiling integer declaration is rejected",
    bool(msg and "ceiling" in msg and "routing.json" in msg),
    msg,
)

reordered = class_guide(("mechanical",) + catalog.CLASSES[2:] + ("scout",))
record(
    "9.7 global Class sections may use a different order",
    check_catalog_error(catalog.validate_guide_text, reordered) is None,
)
record(
    "9.7b indented Markdown headings remain Class sections",
    check_catalog_error(catalog.validate_guide_text,
                        class_guide(catalog.CLASSES).replace("## scout", "   ## scout")) is None,
)

fenced = class_guide(
    catalog.CLASSES,
    extra="\n```\n## knowledge-scout\nfloor: 9\n```\n",
)
# A fenced heading is not a Class section; a fenced floor: integer still
# duplicates routing.json policy and is refused.
msg = check_catalog_error(catalog.validate_guide_text, fenced)
record(
    "9.8 fenced floor integer is still routing policy",
    bool(msg and "floor" in msg and "routing.json" in msg),
    msg,
)
fenced_heading_only = class_guide(
    catalog.CLASSES,
    extra="\n```\n## knowledge-scout\n```\n",
)
record(
    "9.8b fenced unknown heading is not a Class section",
    check_catalog_error(catalog.validate_guide_text, fenced_heading_only) is None,
)

with tempfile.TemporaryDirectory() as missing_dir:
    missing_path = os.path.join(missing_dir, "classes.md")
    msg = check_catalog_error(catalog.validate_guide, missing_path)
    record(
        "9.9 missing guide file is refused",
        bool(msg and "file is missing" in msg),
        msg,
    )


# 10. Focused catalog edits (ticket 11 CLI). Fixtures only; never the live config.
ALL_HARNESSES = set(catalog.HARNESSES)
EMPTY_METERS = {}


def make_edit_fixture(td, *, project=None, dotted=False, symlink=False):
    real_cfg = os.path.join(td, "real-cfg")
    cfg = os.path.join(td, "cfg")
    os.makedirs(real_cfg)
    os.makedirs(cfg)
    lanes = copy.deepcopy(lanes_sample)
    lanes["lanes"]["terra-high@codex"]["order"] = 1
    lanes["lanes"]["grok46-high@grok"]["order"] = 2
    lanes["lanes"]["luna-low@codex"]["order"] = 1
    lanes["lanes"]["flash-high@agy"]["order"] = 2
    lanes["lanes"]["sol-high@codex"]["order"] = 1
    lanes["lanes"]["fable-xhigh@claude"]["order"] = 1
    if dotted:
        extra = copy.deepcopy(lanes["lanes"]["luna-low@codex"])
        extra["model"] = "gpt-5.6-luna"
        extra["order"] = 3
        lanes["lanes"]["gpt-5.6-luna-low@codex"] = extra
    catalog.write_json(os.path.join(real_cfg, "lanes.json"), lanes)
    catalog.write_json(os.path.join(real_cfg, "routing.json"), copy.deepcopy(routing_sample))
    if symlink:
        os.symlink(os.path.join(real_cfg, "lanes.json"), os.path.join(cfg, "lanes.json"))
        os.symlink(os.path.join(real_cfg, "routing.json"), os.path.join(cfg, "routing.json"))
    else:
        os.replace(os.path.join(real_cfg, "lanes.json"), os.path.join(cfg, "lanes.json"))
        os.replace(os.path.join(real_cfg, "routing.json"), os.path.join(cfg, "routing.json"))
        real_cfg = cfg
    repo = os.path.join(td, "repo")
    os.makedirs(repo)
    open(os.path.join(repo, ".git"), "w").close()
    if project is not None:
        os.makedirs(os.path.join(repo, ".delegate"))
        catalog.write_json(os.path.join(repo, ".delegate", "routing.json"), project)
    return cfg, repo, real_cfg


def file_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def same_path(a, b):
    return os.path.realpath(a) == os.path.realpath(b)


def catalog_cli(args, env, cwd=None):
    return subprocess.run(
        [sys.executable, CATALOG_PY, *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
    )


def isolated_cli_env(td, harnesses=ALL_HARNESSES, meters_doc=None):
    bindir = os.path.join(td, "bin")
    os.makedirs(bindir, exist_ok=True)
    for name in harnesses:
        path = os.path.join(bindir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(path, 0o755)
    cache = os.path.join(td, "usage.json")
    if meters_doc is None:
        meters_doc = {}
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(meters_doc, f)
        f.write("\n")
    env = os.environ.copy()
    env["PATH"] = bindir
    env["DELEGATE_CACHE"] = cache
    env.pop("CONSULT_CACHE", None)
    return env


def expected_picks_leaders(cwd, config_dir, present=ALL_HARNESSES, meters=EMPTY_METERS):
    cat = catalog.load_catalog(cwd=cwd, config_dir=config_dir)
    picks = {}
    for cls in catalog.CLASSES:
        rows = rank.rank(cls, cat, meters, present)
        picks[cls] = next((row["lane"] for row in rows if row.get("pick")), None)
    leaders = [
        {"tier": preview["tier"], "leader": preview["leader"]}
        for preview in rank.tier_leaders(cat, meters, present)
    ]
    return picks, leaders


with tempfile.TemporaryDirectory() as td:
    cfg, repo, _real = make_edit_fixture(td, project={"note": "keep me", "margin": 0.5})
    present = ALL_HARNESSES
    preview = catalog.edit_catalog(
        "set",
        field="routing.gate",
        value=0.25,
        scope="global",
        cwd=repo,
        config_dir=cfg,
        present=present,
        meters=EMPTY_METERS,
    )
    before_picks, before_leaders = expected_picks_leaders(repo, cfg)
    record(
        "10.1 set preview names files, revision, global/effective values and cached picks",
        preview["op"] == "set"
        and preview["scope"] == "global"
        and preview["written"] is False
        and preview["noop"] is False
        and same_path(preview["target"]["file"], os.path.join(cfg, "routing.json"))
        and same_path(preview["target"]["resolved"], os.path.join(cfg, "routing.json"))
        and preview["sources"]["project"]["exists"] is True
        and preview["values"]["original"]["global"] == 0.1
        and preview["values"]["original"]["effective"] == 0.1
        and preview["values"]["resulting"]["global"] == 0.25
        and preview["values"]["resulting"]["effective"] == 0.25
        and preview["changed"] == ["routing.gate"]
        and preview["picks"]["before"] == before_picks
        and preview["leaders"]["before"] == before_leaders
        and preview["observations"] == "missing"
        and set(preview["missing_observations"]) == set(lanes_sample["meters"]),
        repr(preview),
    )

    routing_before = file_bytes(os.path.join(cfg, "routing.json"))
    project_before = file_bytes(os.path.join(repo, ".delegate", "routing.json"))
    lanes_before = file_bytes(os.path.join(cfg, "lanes.json"))
    applied = catalog.edit_catalog(
        "set",
        field="routing.gate",
        value=0.25,
        scope="global",
        cwd=repo,
        config_dir=cfg,
        apply=True,
        expect=preview["revision"],
        present=present,
        meters=EMPTY_METERS,
    )
    routing_after = catalog.load_json(os.path.join(cfg, "routing.json"))
    project_after = catalog.load_json(os.path.join(repo, ".delegate", "routing.json"))
    after_picks, after_leaders = expected_picks_leaders(repo, cfg)
    record(
        "10.1b global apply writes only routing.json and preserves project bytes",
        applied["written"] is True
        and routing_after["gate"] == 0.25
        and routing_after["margin"] == routing_sample["margin"]
        and routing_after["classes"] == routing_sample["classes"]
        and "project_order" not in routing_after
        and file_bytes(os.path.join(repo, ".delegate", "routing.json")) == project_before
        and file_bytes(os.path.join(cfg, "lanes.json")) == lanes_before
        and file_bytes(os.path.join(cfg, "routing.json")) != routing_before
        and applied["picks"]["after"] == after_picks
        and applied["leaders"]["after"] == after_leaders
        and project_after["note"] == "keep me"
        and project_after["margin"] == 0.5,
        repr(applied.get("changed")),
    )

    stale = check_catalog_error(
        catalog.edit_catalog,
        "set",
        field="routing.gate",
        value=0.3,
        scope="global",
        cwd=repo,
        config_dir=cfg,
        apply=True,
        expect=preview["revision"],
        present=present,
        meters=EMPTY_METERS,
    )
    record(
        "10.2 stale source revision is rejected without writing",
        stale is not None and "intervening edit" in stale
        and catalog.load_json(os.path.join(cfg, "routing.json"))["gate"] == 0.25,
        stale,
    )


with tempfile.TemporaryDirectory() as td:
    cfg, repo, real_cfg = make_edit_fixture(td, symlink=True)
    lanes_link = os.path.join(cfg, "lanes.json")
    routing_link = os.path.join(cfg, "routing.json")
    preview = catalog.edit_catalog(
        "set",
        field="lanes.terra-high@codex.tier",
        value=3,
        scope="global",
        cwd=repo,
        config_dir=cfg,
        present=ALL_HARNESSES,
        meters=EMPTY_METERS,
    )
    record(
        "10.3 preview reports the stow symlink and resolved target",
        preview["target"]["symlink"] is True
        and same_path(preview["target"]["file"], lanes_link)
        and same_path(preview["target"]["resolved"], os.path.join(real_cfg, "lanes.json"))
        and preview["values"]["resulting"]["tier"] == 3
        and preview["values"]["resulting"]["order"] == 2
        and "lanes.terra-high@codex.tier" in preview["changed"]
        and "lanes.terra-high@codex.order" in preview["changed"],
        repr(preview["target"]) + repr(preview["values"]),
    )
    catalog.edit_catalog(
        "set",
        field="lanes.terra-high@codex.tier",
        value=3,
        scope="global",
        cwd=repo,
        config_dir=cfg,
        apply=True,
        expect=preview["revision"],
        present=ALL_HARNESSES,
        meters=EMPTY_METERS,
    )
    record(
        "10.3b apply writes through the symlink and leaves the link in place",
        os.path.islink(lanes_link)
        and os.path.islink(routing_link)
        and same_path(lanes_link, os.path.join(real_cfg, "lanes.json"))
        and catalog.load_json(os.path.join(real_cfg, "lanes.json"))["lanes"]["terra-high@codex"]["tier"] == 3
        and catalog.load_json(os.path.join(real_cfg, "lanes.json"))["lanes"]["terra-high@codex"]["order"] == 2
        and catalog.load_json(os.path.join(real_cfg, "lanes.json"))["lanes"]["sol-high@codex"]["tier"] == 3,
    )

    other = os.path.join(td, "other-lanes.json")
    shutil.copy(os.path.join(real_cfg, "lanes.json"), other)
    os.remove(lanes_link)
    os.symlink(other, lanes_link)
    msg = check_catalog_error(
        catalog.edit_catalog,
        "set",
        field="lanes.terra-high@codex.tier",
        value=1,
        scope="global",
        cwd=repo,
        config_dir=cfg,
        apply=True,
        expect=preview["revision"],
        present=ALL_HARNESSES,
        meters=EMPTY_METERS,
    )
    record(
        "10.3c retargeted symlink requires a fresh preview",
        msg is not None and "intervening edit" in msg
        and os.path.islink(lanes_link)
        and catalog.load_json(other)["lanes"]["terra-high@codex"]["tier"] == 3,
        msg,
    )


with tempfile.TemporaryDirectory() as td:
    cfg, repo, _real = make_edit_fixture(td)
    routing_path = os.path.join(cfg, "routing.json")
    before = file_bytes(routing_path)
    mtime = os.stat(routing_path).st_mtime_ns
    preview = catalog.edit_catalog(
        "set",
        field="routing.gate",
        value=0.1,
        scope="global",
        cwd=repo,
        config_dir=cfg,
        present=ALL_HARNESSES,
        meters=EMPTY_METERS,
    )
    applied = catalog.edit_catalog(
        "set",
        field="routing.gate",
        value=0.1,
        scope="global",
        cwd=repo,
        config_dir=cfg,
        apply=True,
        expect=preview["revision"],
        present=ALL_HARNESSES,
        meters=EMPTY_METERS,
    )
    record(
        "10.4 semantic no-op apply preserves file bytes",
        preview["noop"] is True
        and preview["changed"] == []
        and applied["written"] is False
        and applied["noop"] is True
        and file_bytes(routing_path) == before
        and os.stat(routing_path).st_mtime_ns == mtime,
        repr(applied),
    )

    invalid_before = file_bytes(routing_path)
    msg = check_catalog_error(
        catalog.edit_catalog,
        "set",
        field="routing.gate",
        value=2,
        scope="global",
        cwd=repo,
        config_dir=cfg,
        apply=True,
        expect=catalog.catalog_revision(cwd=repo, config_dir=cfg),
        present=ALL_HARNESSES,
        meters=EMPTY_METERS,
    )
    record(
        "10.4b invalid write preserves file bytes",
        msg is not None and "gate" in msg
        and file_bytes(routing_path) == invalid_before,
        msg,
    )

    msg = check_catalog_error(
        catalog.edit_catalog,
        "set",
        field="lanes.terra-high@codex.tier",
        value=2,
        scope="project",
        cwd=repo,
        config_dir=cfg,
        present=ALL_HARNESSES,
        meters=EMPTY_METERS,
    )
    record(
        "10.4c project Lane Tier writes are rejected",
        msg is not None and "global-only" in msg and "terra-high@codex" in msg,
        msg,
    )
    preview_m = catalog.edit_catalog(
        "set",
        field="routing.meters",
        value=False,
        scope="global",
        cwd=repo,
        config_dir=cfg,
        present=ALL_HARNESSES,
        meters=EMPTY_METERS,
    )
    record(
        "10.4d routing.meters accepts JSON false",
        preview_m["values"]["original"]["effective"] is True
        and preview_m["values"]["resulting"]["effective"] is False
        and preview_m["changed"] == ["routing.meters"]
        and preview_m["noop"] is False,
        repr(preview_m["values"]),
    )
    catalog.edit_catalog(
        "set",
        field="routing.meters",
        value=False,
        scope="global",
        cwd=repo,
        config_dir=cfg,
        apply=True,
        expect=preview_m["revision"],
        present=ALL_HARNESSES,
        meters=EMPTY_METERS,
    )
    written_m = catalog.load_json(os.path.join(cfg, "routing.json"))
    record(
        "10.4d2 applying meters false writes the boolean and keeps Gate/Margin",
        written_m["meters"] is False
        and written_m["gate"] == routing_sample["gate"]
        and written_m["margin"] == routing_sample["margin"],
        repr(written_m.get("meters")),
    )


with tempfile.TemporaryDirectory() as td:
    cfg, repo, _real = make_edit_fixture(td)
    global_before = file_bytes(os.path.join(cfg, "routing.json"))
    preview = catalog.edit_catalog(
        "range",
        cls="scout",
        floor=4,
        ceiling=4,
        scope="project",
        cwd=repo,
        config_dir=cfg,
        present=ALL_HARNESSES,
        meters=EMPTY_METERS,
    )
    record(
        "10.5 paired project Range preview sets both bounds against original globals",
        preview["values"]["original"]["global"] == {"floor": 2, "ceiling": 3}
        and preview["values"]["original"]["effective"] == {"floor": 2, "ceiling": 3}
        and preview["values"]["resulting"]["global"] == {"floor": 2, "ceiling": 3}
        and preview["values"]["resulting"]["effective"] == {"floor": 4, "ceiling": 4}
        and preview["changed"] == ["classes.scout.floor", "classes.scout.ceiling"]
        and preview["target"]["file"] == os.path.join(repo, ".delegate", "routing.json")
        and preview["sources"]["project"]["exists"] is False,
        repr(preview["values"]),
    )
    catalog.edit_catalog(
        "range",
        cls="scout",
        floor=4,
        ceiling=4,
        scope="project",
        cwd=repo,
        config_dir=cfg,
        apply=True,
        expect=preview["revision"],
        present=ALL_HARNESSES,
        meters=EMPTY_METERS,
    )
    project_doc = catalog.load_json(os.path.join(repo, ".delegate", "routing.json"))
    global_doc = catalog.load_json(os.path.join(cfg, "routing.json"))
    record(
        "10.5b project Range writes both bounds and does not leak into global routing",
        project_doc["classes"]["scout"] == {"floor": 4, "ceiling": 4}
        and file_bytes(os.path.join(cfg, "routing.json")) == global_before
        and global_doc["classes"]["scout"] == {"floor": 2, "ceiling": 3}
        and "project_order" not in global_doc,
        repr(project_doc),
    )
    msg = check_catalog_error(
        catalog.edit_catalog,
        "range",
        cls="scout",
        floor=4,
        ceiling=3,
        scope="project",
        cwd=repo,
        config_dir=cfg,
        present=ALL_HARNESSES,
        meters=EMPTY_METERS,
    )
    record(
        "10.5c floor above ceiling is rejected as a pair",
        msg is not None and "floor (4) cannot exceed ceiling (3)" in msg,
        msg,
    )


with tempfile.TemporaryDirectory() as td:
    cfg, repo, _real = make_edit_fixture(
        td,
        project={"project_order": ["flash-high@agy"], "note": "other tiers stay"},
    )
    preview = catalog.edit_catalog(
        "order",
        lane="grok46-high@grok",
        position=1,
        scope="global",
        cwd=repo,
        config_dir=cfg,
        present=ALL_HARNESSES,
        meters=EMPTY_METERS,
    )
    record(
        "10.6 same-Tier global Order renumbers only that Tier",
        preview["values"]["tier"] == 2
        and preview["values"]["sequence"]["original"] == ["terra-high@codex", "grok46-high@grok"]
        and preview["values"]["sequence"]["resulting"] == ["grok46-high@grok", "terra-high@codex"]
        and preview["changed"] == ["lanes.grok46-high@grok.order", "lanes.terra-high@codex.order"],
        repr(preview["values"]),
    )
    catalog.edit_catalog(
        "order",
        lane="grok46-high@grok",
        position=1,
        scope="global",
        cwd=repo,
        config_dir=cfg,
        apply=True,
        expect=preview["revision"],
        present=ALL_HARNESSES,
        meters=EMPTY_METERS,
    )
    lanes_doc = catalog.load_json(os.path.join(cfg, "lanes.json"))
    project_doc = catalog.load_json(os.path.join(repo, ".delegate", "routing.json"))
    record(
        "10.6b global Order does not write project_order or other Tiers",
        lanes_doc["lanes"]["grok46-high@grok"]["order"] == 1
        and lanes_doc["lanes"]["terra-high@codex"]["order"] == 2
        and lanes_doc["lanes"]["luna-low@codex"]["order"] == 1
        and lanes_doc["lanes"]["flash-high@agy"]["order"] == 2
        and "project_order" not in lanes_doc
        and project_doc["project_order"] == ["flash-high@agy"]
        and project_doc["note"] == "other tiers stay",
    )

    rev = catalog.catalog_revision(cwd=repo, config_dir=cfg)
    preview_p = catalog.edit_catalog(
        "order",
        lane="terra-high@codex",
        position=1,
        scope="project",
        cwd=repo,
        config_dir=cfg,
        present=ALL_HARNESSES,
        meters=EMPTY_METERS,
    )
    catalog.edit_catalog(
        "order",
        lane="terra-high@codex",
        position=1,
        scope="project",
        cwd=repo,
        config_dir=cfg,
        apply=True,
        expect=preview_p["revision"],
        present=ALL_HARNESSES,
        meters=EMPTY_METERS,
    )
    project_doc = catalog.load_json(os.path.join(repo, ".delegate", "routing.json"))
    global_lanes = catalog.load_json(os.path.join(cfg, "lanes.json"))
    effective = catalog.load_catalog(cwd=repo, config_dir=cfg)
    tier1 = [
        name for name, lane in sorted(
            ((n, l) for n, l in effective["lanes"].items() if l["tier"] == 1),
            key=lambda item: item[1]["order"],
        )
    ]
    record(
        "10.6c project Order rewrites only the selected Tier and keeps global lanes",
        project_doc["project_order"]
            == ["flash-high@agy", "terra-high@codex", "grok46-high@grok"]
        and project_doc["note"] == "other tiers stay"
        and global_lanes["lanes"]["grok46-high@grok"]["order"] == 1
        and global_lanes["lanes"]["terra-high@codex"]["order"] == 2
        and tier1[0] == "flash-high@agy"
        and preview_p["revision"] == rev,
        repr(project_doc),
    )


with tempfile.TemporaryDirectory() as td:
    cfg, repo, _real = make_edit_fixture(td, dotted=True)
    field = "lanes.gpt-5.6-luna-low@codex.tier"
    kind, name = catalog.parse_set_field(field)
    preview = catalog.edit_catalog(
        "set",
        field=field,
        value=2,
        scope="global",
        cwd=repo,
        config_dir=cfg,
        present=ALL_HARNESSES,
        meters=EMPTY_METERS,
    )
    record(
        "10.7 dotted lane names use the prefix and final field",
        kind == "lane_tier"
        and name == "gpt-5.6-luna-low@codex"
        and preview["values"]["lane"] == "gpt-5.6-luna-low@codex"
        and preview["values"]["original"]["tier"] == 1
        and preview["values"]["resulting"]["tier"] == 2
        and preview["values"]["resulting"]["order"]
            == 1 + max(
                lanes_sample["lanes"]["terra-high@codex"].get("order") or 0,
                2,
            ),
        repr(preview["values"]),
    )
    catalog.edit_catalog(
        "set",
        field=field,
        value=2,
        scope="global",
        cwd=repo,
        config_dir=cfg,
        apply=True,
        expect=preview["revision"],
        present=ALL_HARNESSES,
        meters=EMPTY_METERS,
    )
    written = catalog.load_json(os.path.join(cfg, "lanes.json"))
    record(
        "10.7b dotted lane Tier move appends to the new Tier Order",
        written["lanes"]["gpt-5.6-luna-low@codex"]["tier"] == 2
        and written["lanes"]["gpt-5.6-luna-low@codex"]["order"] == 3
        and written["lanes"]["terra-high@codex"]["order"] == 1
        and written["lanes"]["grok46-high@grok"]["order"] == 2,
        repr(written["lanes"]["gpt-5.6-luna-low@codex"]),
    )


with tempfile.TemporaryDirectory() as td:
    cfg, repo, _real = make_edit_fixture(td)
    env = isolated_cli_env(td, meters_doc={})
    helper = catalog.edit_catalog(
        "set",
        field="routing.margin",
        value=0.4,
        scope="global",
        cwd=repo,
        config_dir=cfg,
        present=ALL_HARNESSES,
        meters=EMPTY_METERS,
    )
    res = catalog_cli(
        [
            "set", "routing.margin", "0.4",
            "--scope", "global",
            "--cwd", repo,
            "--config-dir", cfg,
        ],
        env,
    )
    cli = json.loads(res.stdout)
    record(
        "10.8 CLI preview matches helper picks with no vendor probe",
        res.returncode == 0
        and cli["picks"] == helper["picks"]
        and cli["leaders"] == helper["leaders"]
        and cli["revision"] == helper["revision"]
        and cli["observations"] == "missing"
        and cli["unavailable_harnesses"] == [],
        res.stderr + res.stdout[:500],
    )
    res_apply = catalog_cli(
        [
            "set", "routing.margin", "0.4",
            "--scope", "global",
            "--cwd", repo,
            "--config-dir", cfg,
            "--apply",
            "--expect", cli["revision"],
        ],
        env,
    )
    applied = json.loads(res_apply.stdout)
    after_picks, after_leaders = expected_picks_leaders(repo, cfg)
    record(
        "10.8b CLI apply before/after predictions match rank on the fixture",
        res_apply.returncode == 0
        and applied["written"] is True
        and applied["picks"]["after"] == after_picks
        and applied["leaders"]["after"] == after_leaders
        and catalog.load_json(os.path.join(cfg, "routing.json"))["margin"] == 0.4,
        res_apply.stderr,
    )
    res_bad = catalog_cli(
        [
            "set", "routing.margin", "0.4",
            "--scope", "global",
            "--cwd", repo,
            "--config-dir", cfg,
            "--apply",
        ],
        env,
    )
    record(
        "10.8c apply without --expect is refused",
        res_bad.returncode == 1 and "--apply requires --expect" in res_bad.stderr,
        res_bad.stderr,
    )

    absent_rev = catalog.catalog_revision(cwd=repo, config_dir=cfg)
    os.makedirs(os.path.join(repo, ".delegate"), exist_ok=True)
    catalog.write_json(os.path.join(repo, ".delegate", "routing.json"), {"gate": 0.2})
    present_rev = catalog.catalog_revision(cwd=repo, config_dir=cfg)
    record(
        "10.9 absent project file is part of the revision",
        absent_rev != present_rev,
        f"{absent_rev} == {present_rev}",
    )
    msg = check_catalog_error(
        catalog.edit_catalog,
        "set",
        field="routing.margin",
        value=0.5,
        scope="global",
        cwd=repo,
        config_dir=cfg,
        apply=True,
        expect=absent_rev,
        present=ALL_HARNESSES,
        meters=EMPTY_METERS,
    )
    record(
        "10.9b creating the project file invalidates the previous revision",
        msg is not None and "intervening edit" in msg,
        msg,
    )

    env_partial = isolated_cli_env(td, harnesses=("codex",), meters_doc={})
    # isolated_cli_env writes a second usage.json in the same td; rebuild PATH only
    env_partial = env.copy()
    bindir = os.path.join(td, "one-harness")
    os.makedirs(bindir, exist_ok=True)
    with open(os.path.join(bindir, "codex"), "w", encoding="utf-8") as f:
        f.write("#!/bin/sh\nexit 0\n")
    os.chmod(os.path.join(bindir, "codex"), 0o755)
    env_partial["PATH"] = bindir
    res_unavail = catalog_cli(
        ["set", "routing.gate", "0.1", "--scope", "global", "--cwd", repo, "--config-dir", cfg],
        env_partial,
    )
    unavail = json.loads(res_unavail.stdout)
    record(
        "10.10 unavailable harnesses are reported from PATH without probing",
        res_unavail.returncode == 0
        and unavail["unavailable_harnesses"] == ["agy", "claude", "grok"]
        and unavail["noop"] is True,
        res_unavail.stderr + repr(unavail.get("unavailable_harnesses")),
    )



# A destination Tier can contain legacy Lanes without Order.
with tempfile.TemporaryDirectory() as td:
    cfg, repo, _ = make_edit_fixture(td)
    path = os.path.join(cfg, "lanes.json")
    doc = catalog.load_json(path)
    moving = "terra-high@codex"
    dest = doc["lanes"]["luna-low@codex"]["tier"]
    for item in doc["lanes"].values():
        if item["tier"] == dest:
            item.pop("order", None)
    catalog.write_json(path, doc)
    preview = catalog.edit_catalog("set", scope="global", cwd=repo, config_dir=cfg,
        field=f"lanes.{moving}.tier", value=dest, meters={}, present=ALL_HARNESSES)
    catalog.edit_catalog("set", scope="global", cwd=repo, config_dir=cfg,
        field=f"lanes.{moving}.tier", value=dest, meters={}, present=ALL_HARNESSES,
        apply=True, expect=preview["revision"])
    after = catalog.load_json(path)["lanes"]
    record("10.11 Tier move follows unordered destination Lanes",
          catalog._carried_in_tier(after, dest)[-1] == moving, preview)

with tempfile.TemporaryDirectory() as td:
    cfg, repo, _ = make_edit_fixture(td)
    preview = catalog.edit_catalog("set", scope="global", cwd=repo, config_dir=cfg,
        field="routing.gate", value=0.2, meters={}, present=ALL_HARNESSES)
    original_preview = catalog._rank_preview
    path = os.path.join(cfg, "routing.json")
    def intervening_write(*args):
        doc = catalog.load_json(path)
        doc["note"] = "intervening edit during preview"
        catalog.write_json(path, doc)
        return original_preview(*args)
    catalog._rank_preview = intervening_write
    try:
        msg = check_catalog_error(lambda: catalog.edit_catalog("set", scope="global",
            cwd=repo, config_dir=cfg, field="routing.gate", value=0.2, meters={},
            present=ALL_HARNESSES, apply=True, expect=preview["revision"]))
    finally:
        catalog._rank_preview = original_preview
    record("10.12 Re-read immediately before write rejects intervening change",
          msg is not None and "intervening edit" in msg and
          catalog.load_json(path)["gate"] == routing_sample["gate"], msg)

with tempfile.TemporaryDirectory() as td:
    cfg, repo, _ = make_edit_fixture(td)
    project_dir = os.path.join(repo, ".delegate")
    os.makedirs(project_dir)
    path = os.path.join(project_dir, "routing.json")
    with open(path, "w") as f:
        f.write("null\n")
    msg = check_catalog_error(catalog.edit_catalog, "set", scope="project", cwd=repo,
        config_dir=cfg, field="routing.gate", value=0.2, meters={}, present=ALL_HARNESSES)
    record("10.13 Present null project is invalid, not an absent overlay",
        msg is not None and "must be a JSON object" in msg and file_bytes(path) == b"null\n", msg)
# 11. routing.meters: validators, default on, project override, no-op absence.
doc_m = copy.deepcopy(routing_sample)
record("11.1 legacy routing without meters defaults on",
       "meters" not in doc_m and catalog.meters_enabled(doc_m) is True
       and catalog.validate_routing(doc_m) is not None)

doc_m["meters"] = False
record("11.2 meters false is valid and effective off",
       catalog.validate_routing(doc_m) is not None and catalog.meters_enabled(doc_m) is False)

doc_m["meters"] = True
record("11.3 meters true is valid and effective on",
       catalog.validate_routing(doc_m) is not None and catalog.meters_enabled(doc_m) is True)

for bad in (0, 1, "false", None, 0.0):
    doc_bad = copy.deepcopy(routing_sample)
    doc_bad["meters"] = bad
    msg_bad = check_catalog_error(catalog.validate_routing, doc_bad)
    record(
        f"11.4 meters rejects {bad!r}",
        msg_bad is not None and "meters" in msg_bad and "boolean" in msg_bad,
        msg_bad,
    )

with tempfile.TemporaryDirectory() as td:
    cfg, repo, _real = make_edit_fixture(td)
    routing_path = os.path.join(cfg, "routing.json")
    before = file_bytes(routing_path)
    preview = catalog.edit_catalog(
        "set", field="routing.meters", value=True, scope="global",
        cwd=repo, config_dir=cfg, present=ALL_HARNESSES, meters=EMPTY_METERS,
    )
    applied = catalog.edit_catalog(
        "set", field="routing.meters", value=True, scope="global",
        cwd=repo, config_dir=cfg, apply=True, expect=preview["revision"],
        present=ALL_HARNESSES, meters=EMPTY_METERS,
    )
    after_doc = catalog.load_json(routing_path)
    record(
        "11.5 no-op true on legacy routing preserves absence and file bytes",
        preview["noop"] is True and applied["written"] is False
        and "meters" not in after_doc
        and file_bytes(routing_path) == before
        and preview["values"]["original"]["effective"] is True
        and preview["values"]["resulting"]["effective"] is True,
        repr(preview),
    )

with tempfile.TemporaryDirectory() as td:
    cfg, repo, _real = make_edit_fixture(td, project={"meters": False})
    cat = catalog.load_catalog(cwd=repo, config_dir=cfg)
    record(
        "11.6 project meters false overrides global default on",
        catalog.meters_enabled(cat["routing"]) is False
        and "meters" not in catalog.load_json(os.path.join(cfg, "routing.json")),
        repr(cat["routing"].get("meters")),
    )
    preview = catalog.edit_catalog(
        "set", field="routing.meters", value=True, scope="project",
        cwd=repo, config_dir=cfg, present=ALL_HARNESSES, meters=EMPTY_METERS,
    )
    catalog.edit_catalog(
        "set", field="routing.meters", value=True, scope="project",
        cwd=repo, config_dir=cfg, apply=True, expect=preview["revision"],
        present=ALL_HARNESSES, meters=EMPTY_METERS,
    )
    project_doc = catalog.load_json(os.path.join(repo, ".delegate", "routing.json"))
    cat_after = catalog.load_catalog(cwd=repo, config_dir=cfg)
    record(
        "11.6b project meters true restores on without writing global",
        project_doc.get("meters") is True
        and catalog.meters_enabled(cat_after["routing"]) is True
        and "meters" not in catalog.load_json(os.path.join(cfg, "routing.json")),
        repr(project_doc),
    )

with tempfile.TemporaryDirectory() as td:
    cfg, repo, real_cfg = make_edit_fixture(td, symlink=True)
    preview = catalog.edit_catalog(
        "set", field="routing.meters", value=False, scope="global",
        cwd=repo, config_dir=cfg, present=ALL_HARNESSES, meters=EMPTY_METERS,
    )
    catalog.edit_catalog(
        "set", field="routing.meters", value=False, scope="global",
        cwd=repo, config_dir=cfg, apply=True, expect=preview["revision"],
        present=ALL_HARNESSES, meters=EMPTY_METERS,
    )
    routing_link = os.path.join(cfg, "routing.json")
    record(
        "11.7 meters apply preserves the routing symlink",
        os.path.islink(routing_link)
        and catalog.load_json(os.path.join(real_cfg, "routing.json"))["meters"] is False,
    )

sys.exit(1 if fails else 0)
