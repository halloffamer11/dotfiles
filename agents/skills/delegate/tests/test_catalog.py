#!/usr/bin/env python3
"""test_catalog.py — unit and CLI tests for catalog.py. Run: python3 tests/test_catalog.py"""
import copy
import io
import json
import os
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


sys.exit(1 if fails else 0)
