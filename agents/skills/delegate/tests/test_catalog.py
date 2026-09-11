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
DELEGATE_DIR = os.path.abspath(os.path.join(HERE, "..", "scripts"))
SAMPLES_DIR = os.path.abspath(os.path.join(HERE, "..", "assets", "samples"))
CATALOG_PY = os.path.join(DELEGATE_DIR, "catalog.py")

sys.path.insert(0, DELEGATE_DIR)
import catalog

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

# 1e. lane at each of the six efforts validates
for eff in ("low", "medium", "high", "xhigh", "max", "ultra"):
    doc_eff = copy.deepcopy(lanes_sample)
    doc_eff["lanes"]["fable-xhigh@claude"]["effort"] = eff
    val_eff = catalog.validate_lanes(doc_eff)
    record(
        f"effort {eff} validates",
        val_eff is not None and doc_eff["lanes"]["fable-xhigh@claude"]["effort"] == eff,
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
# and a field disagree with nobody noticing. bench.py's aa_match_info is where
# a suffixed published name is split, and it keeps the effort it split off.
record(
    "7.8 a suffix on the published side is not silently dropped",
    resolve("gpt-6-astra-max", {"lanes": {
        "a@codex": {"model": "gpt-6-astra", "effort": "high"},
    }}) is None
    and resolve("Gemini 3.8 Flash", {"lanes": {
        "a@agy": {"model": "gemini-3.8-flash-high", "effort": "high"},
    }}) == "gemini-3.8-flash-high",
)


sys.exit(1 if fails else 0)
