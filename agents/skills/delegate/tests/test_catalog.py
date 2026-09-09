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

# 2.4 trust 0 and trust 6
doc = copy.deepcopy(lanes_sample)
doc["lanes"]["fable-xhigh@claude"]["trust"] = 0
msg0 = check_catalog_error(catalog.validate_lanes, doc)
doc["lanes"]["fable-xhigh@claude"]["trust"] = 6
msg6 = check_catalog_error(catalog.validate_lanes, doc)
record(
    "reject: trust 0 and trust 6",
    bool(msg0 and "fable-xhigh@claude" in msg0 and "trust" in msg0 and "1 to 5" in msg0 and
         msg6 and "fable-xhigh@claude" in msg6 and "trust" in msg6 and "1 to 5" in msg6),
    f"{msg0} | {msg6}",
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

# 2.15 unknown class in classTier
doc = copy.deepcopy(routing_sample)
doc["classTier"]["invalid_class"] = 2
msg = check_catalog_error(catalog.validate_routing, doc)
record(
    "reject: unknown class in classTier",
    bool(msg and "invalid_class" in msg and "unknown class" in msg),
    msg,
)

# 2.16 class tier 5
doc = copy.deepcopy(routing_sample)
doc["classTier"]["scout"] = 5
msg = check_catalog_error(catalog.validate_routing, doc)
record(
    "reject: class tier 5",
    bool(msg and "scout" in msg and "tier" in msg and "1 to 4" in msg),
    msg,
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
    catalog.write_json(p_file, {"classTier": {"review": 3}})

    r1, s1 = catalog.effective_routing(cwd=fake_git, config_dir=cfg_dir)
    review_ok = (
        r1["classTier"]["review"] == 3 and
        s1["classTier.review"] == p_file and
        r1["margin"] == 0.2 and
        s1["margin"] == g_file and
        r1["gate"] == 0.1 and
        s1["gate"] == g_file and
        all(r1["classTier"][c] == routing_sample["classTier"][c] for c in ("scout", "mechanical", "impl", "hard-impl")) and
        all(s1[f"classTier.{c}"] == g_file for c in ("scout", "mechanical", "impl", "hard-impl"))
    )
    record("override merge: classTier review only", review_ok)

    # Margin override
    catalog.write_json(p_file, {"margin": 0.5})
    r2, s2 = catalog.effective_routing(cwd=fake_git, config_dir=cfg_dir)
    margin_ok = (
        r2["margin"] == 0.5 and
        s2["margin"] == p_file and
        r2["classTier"]["review"] == routing_sample["classTier"]["review"] and
        s2["classTier.review"] == g_file
    )
    record("override merge: margin only", margin_ok)

    # No git root
    no_git = os.path.join(td, "no_git_dir")
    os.makedirs(no_git)
    r3, s3 = catalog.effective_routing(cwd=no_git, config_dir=cfg_dir)
    no_git_ok = (
        r3["classTier"]["review"] == routing_sample["classTier"]["review"] and
        s3["classTier.review"] == g_file and
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
        eff_r["classTier"] == routing_sample["classTier"]
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

sys.exit(1 if fails else 0)
