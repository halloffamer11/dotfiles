#!/usr/bin/env python3
"""test_discover.py — unit and CLI tests for discover.py. Run: python3 tests/test_discover.py"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DELEGATE_DIR = os.path.abspath(os.path.join(HERE, "..", "scripts"))
SAMPLES_DIR = os.path.abspath(os.path.join(HERE, "..", "assets", "samples"))
FIXTURES_DIR = os.path.join(HERE, "fixtures", "discover")
DISCOVER_PY = os.path.join(DELEGATE_DIR, "discover.py")

sys.path.insert(0, DELEGATE_DIR)
import catalog
import discover

fails = 0


def record(name, ok, detail=""):
    global fails
    if ok:
        print(f"PASS {name}")
    else:
        fails += 1
        print(f"FAIL {name}: {detail}")


# -------------------------------------------------------------
# 1. Codex fixture parser: list visibility kept, hide visibility excluded
codex_fixture_path = os.path.join(FIXTURES_DIR, "codex-debug-models.json")
with open(codex_fixture_path, "r", encoding="utf-8") as f:
    codex_raw = f.read()

codex_models = discover.parse_codex_output(codex_raw)
codex_slugs = [m["slug"] for m in codex_models]
codex_ok = (
    codex_slugs == ["gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5"]
    and "gpt-reserve" not in codex_slugs
    and "codex-auto-review" not in codex_slugs
    and all(m["display_name"] is not None for m in codex_models)
)
record("codex fixture parsing excludes hide visibility", codex_ok, f"slugs={codex_slugs}")


# -------------------------------------------------------------
# 2. AGY fixture parser: skips header, extracts slugs and display names
agy_fixture_path = os.path.join(FIXTURES_DIR, "agy-models.txt")
with open(agy_fixture_path, "r", encoding="utf-8") as f:
    agy_raw = f.read()

agy_models = discover.parse_agy_output(agy_raw)
agy_slugs = [m["slug"] for m in agy_models]
agy_ok = (
    len(agy_models) == 14
    and "Fetching available models..." not in agy_slugs
    and agy_models[0]["slug"] == "gemini-3.8-flash-high"
    and agy_models[0]["display_name"] == "Gemini 3.8 Flash (High)"
    and "claude-sonnet-4-6" in agy_slugs
    and "gpt-oss-120b-medium" in agy_slugs
)
record("agy fixture parsing skips header and parses tabs", agy_ok, f"count={len(agy_models)}, slugs={agy_slugs[:3]}")


# -------------------------------------------------------------
# 3. Grok fixture parser: strips bullets and (default) suffix
grok_fixture_path = os.path.join(FIXTURES_DIR, "grok-models.txt")
with open(grok_fixture_path, "r", encoding="utf-8") as f:
    grok_raw = f.read()

grok_models = discover.parse_grok_output(grok_raw)
grok_slugs = [m["slug"] for m in grok_models]
grok_ok = (
    grok_slugs == ["grok-4.6", "grok-4.5"]
    and not any(s.startswith("*") or s.startswith("-") for s in grok_slugs)
    and not any("(default)" in s for s in grok_slugs)
)
record("grok fixture parsing strips bullets and default suffix", grok_ok, f"slugs={grok_slugs}")


# -------------------------------------------------------------
# 4. Discovery with fixtures against sample catalog
with tempfile.TemporaryDirectory() as td:
    cfg_dir = os.path.join(td, "cfg")
    os.makedirs(cfg_dir)
    shutil.copy(os.path.join(SAMPLES_DIR, "lanes.json"), cfg_dir)
    shutil.copy(os.path.join(SAMPLES_DIR, "routing.json"), cfg_dir)
    cat = catalog.load_catalog(config_dir=cfg_dir)

    all_harnesses = {"claude", "codex", "agy", "grok"}
    res = discover.discover(cat, present=all_harnesses, fixture_dir=FIXTURES_DIR)

    # Codex checks
    codex_entry = res["harnesses"]["codex"]
    codex_status_ok = codex_entry["status"] == "ok" and codex_entry["discovered_count"] == 5

    # Claude checks: hand-named, undiscoverable
    claude_models = [m for m in res["models"] if m["harness"] == "claude"]
    claude_ok = (
        len(claude_models) == 1
        and claude_models[0]["slug"] == "claude-fable-5-1"
        and claude_models[0]["lane"] == "fable-xhigh@claude"
        and claude_models[0]["reason"] == "hand-named, undiscoverable"
    )

    # Sample catalog has:
    # sol-high@codex -> gpt-5.6-sol
    # terra-high@codex -> gpt-5.6-terra
    # luna-low@codex -> gpt-5.6-luna
    # flash-high@agy -> gemini-3.8-flash-high
    # grok46-high@grok -> grok-4.6
    # fable-xhigh@claude -> claude-fable-5-1
    # Note: gpt-6-astra and gpt-5.5 have no lane in sample lanes.json!
    unmapped_slugs = {(u["harness"], u["slug"]) for u in res["unmapped"]}
    unmapped_ok = (
        ("codex", "gpt-6-astra") in unmapped_slugs
        and ("codex", "gpt-5.5") in unmapped_slugs
        and ("grok", "grok-4.5") in unmapped_slugs
        and ("agy", "gemini-3.8-flash-medium") in unmapped_slugs
        and ("codex", "gpt-5.6-sol") not in unmapped_slugs
        and ("agy", "gemini-3.8-flash-high") not in unmapped_slugs
        and ("grok", "grok-4.6") not in unmapped_slugs
    )

    # Retired should be empty with sample catalog (all sample lanes exist in fixtures)
    retired_ok = len(res["retired"]) == 0

    record("discover() full fixture evaluation against sample catalog", codex_status_ok and claude_ok and unmapped_ok and retired_ok)


# -------------------------------------------------------------
# 5. Retired slug tail: lane pointing to model that no longer appears in harness
with tempfile.TemporaryDirectory() as td:
    cfg_dir = os.path.join(td, "cfg")
    os.makedirs(cfg_dir)
    with open(os.path.join(SAMPLES_DIR, "lanes.json"), "r", encoding="utf-8") as f:
        lanes_doc = json.load(f)

    # Add a lane pointing to a retired model
    lanes_doc["lanes"]["old-codex@codex"] = {
        "harness": "codex",
        "model": "gpt-old-retired",
        "effort": "high",
        "meter": "codex",
        "meter_weight": 10,
        "timeout": "30m",
        "price": {"in": 1, "cache_read": 0.1, "cache_write": None, "out": 2},
        "tier": 2,
        "basis": "retired test model",
    }
    catalog.write_json(os.path.join(cfg_dir, "lanes.json"), lanes_doc)
    shutil.copy(os.path.join(SAMPLES_DIR, "routing.json"), cfg_dir)

    cat_retired = catalog.load_catalog(config_dir=cfg_dir)
    res_retired = discover.discover(cat_retired, present={"codex"}, fixture_dir=FIXTURES_DIR)

    ret_lanes = [r["lane"] for r in res_retired["retired"]]
    ret_models = [r["model"] for r in res_retired["retired"]]
    retired_detected = (
        "old-codex@codex" in ret_lanes
        and "gpt-old-retired" in ret_models
    )
    record("retired slug tail detects unoffered lane model", retired_detected, f"retired={res_retired['retired']}")

    # Formatted report carries the retired line
    report = discover.format_report(res_retired)
    report_retired_ok = (
        "# lanes whose model no longer appears in harness" in report
        and "old-codex@codex" in report
        and "model: gpt-old-retired" in report
    )
    record("format_report prints retired lane line", report_retired_ok)


# -------------------------------------------------------------
# 6. Missing harness binary path: reported as missing, not an error and no crash
with tempfile.TemporaryDirectory() as td:
    cfg_dir = os.path.join(td, "cfg")
    os.makedirs(cfg_dir)
    shutil.copy(os.path.join(SAMPLES_DIR, "lanes.json"), cfg_dir)
    shutil.copy(os.path.join(SAMPLES_DIR, "routing.json"), cfg_dir)
    cat = catalog.load_catalog(config_dir=cfg_dir)

    # Only agy is present; codex, grok, claude are absent
    res_missing = discover.discover(cat, present={"agy"}, fixture_dir=FIXTURES_DIR)
    h_doc = res_missing["harnesses"]

    missing_ok = (
        h_doc["agy"]["status"] == "ok"
        and h_doc["codex"]["status"] == "missing"
        and h_doc["grok"]["status"] == "missing"
        and h_doc["claude"]["status"] == "missing"
        and h_doc["codex"]["error"] is None
    )
    record("missing harness binary reported as missing", missing_ok, f"statuses={[(k, v['status']) for k, v in h_doc.items()]}")

    report_missing = discover.format_report(res_missing)
    report_missing_ok = (
        "codex   missing" in report_missing
        and "grok    missing" in report_missing
        and "claude  missing" in report_missing
        and "gemini-3.8-flash-high" in report_missing
    )
    record("format_report prints missing harness line", report_missing_ok)


# -------------------------------------------------------------
# 7. All harnesses missing path: exits 0, reports missing, no crash
with tempfile.TemporaryDirectory() as td:
    cfg_dir = os.path.join(td, "cfg")
    os.makedirs(cfg_dir)
    shutil.copy(os.path.join(SAMPLES_DIR, "lanes.json"), cfg_dir)
    shutil.copy(os.path.join(SAMPLES_DIR, "routing.json"), cfg_dir)
    cat = catalog.load_catalog(config_dir=cfg_dir)

    res_all_missing = discover.discover(cat, present=set(), fixture_dir=FIXTURES_DIR)
    all_missing_ok = (
        all(v["status"] == "missing" for v in res_all_missing["harnesses"].values())
        and len(res_all_missing["models"]) == 0
        and len(res_all_missing["unmapped"]) == 0
        and len(res_all_missing["retired"]) == 0
    )
    record("all harnesses missing produces empty results with status missing", all_missing_ok)


# -------------------------------------------------------------
# 8. Failing/unparseable harness command: reports error, other harnesses continue
def faulty_runner(harness):
    if harness == "codex":
        raise RuntimeError("simulated crash in codex execution")
    elif harness == "agy":
        return "not valid json or tab format: [[["
    elif harness == "grok":
        with open(os.path.join(FIXTURES_DIR, "grok-models.txt"), "r", encoding="utf-8") as f:
            return f.read()
    return ""

with tempfile.TemporaryDirectory() as td:
    cfg_dir = os.path.join(td, "cfg")
    os.makedirs(cfg_dir)
    shutil.copy(os.path.join(SAMPLES_DIR, "lanes.json"), cfg_dir)
    shutil.copy(os.path.join(SAMPLES_DIR, "routing.json"), cfg_dir)
    cat = catalog.load_catalog(config_dir=cfg_dir)

    res_faulty = discover.discover(cat, present={"codex", "agy", "grok"}, runner=faulty_runner)
    h_faulty = res_faulty["harnesses"]

    faulty_ok = (
        h_faulty["codex"]["status"] == "error"
        and "simulated crash" in h_faulty["codex"]["error"]
        and h_faulty["grok"]["status"] == "ok"
        and h_faulty["grok"]["discovered_count"] == 2
    )
    record("failing harness reports error line while others report", faulty_ok)


# -------------------------------------------------------------
# 9. CLI execution: plain text report with aligned columns and exit 0
with tempfile.TemporaryDirectory() as td:
    cfg_dir = os.path.join(td, "cfg")
    os.makedirs(cfg_dir)
    shutil.copy(os.path.join(SAMPLES_DIR, "lanes.json"), cfg_dir)
    shutil.copy(os.path.join(SAMPLES_DIR, "routing.json"), cfg_dir)

    res_cli = subprocess.run(
        [
            sys.executable, DISCOVER_PY,
            "--config-dir", cfg_dir,
            "--fixture-dir", FIXTURES_DIR,
            "--harnesses", "claude,codex,agy,grok",
        ],
        capture_output=True,
        text=True,
    )

    out = res_cli.stdout
    cli_ok = (
        res_cli.returncode == 0
        and "# models" in out
        and "# slugs with no lane" in out
        and "# lanes whose model no longer appears in harness" in out
        and "codex   gpt-6-astra" in out
        and "lane: none" in out
        and "codex   gpt-5.6-sol" in out
        and "lane: sol-high@codex" in out
        and "claude  claude-fable-5-1" in out
        and "lane: fable-xhigh@claude" in out
        and "(hand-named, undiscoverable)" in out
    )
    record("CLI plain text execution exits 0 and renders aligned report", cli_ok, f"rc={res_cli.returncode}, out={out[:200]}")


# -------------------------------------------------------------
# 10. CLI execution: --json emits valid JSON document matching schema
with tempfile.TemporaryDirectory() as td:
    cfg_dir = os.path.join(td, "cfg")
    os.makedirs(cfg_dir)
    shutil.copy(os.path.join(SAMPLES_DIR, "lanes.json"), cfg_dir)
    shutil.copy(os.path.join(SAMPLES_DIR, "routing.json"), cfg_dir)

    res_json = subprocess.run(
        [
            sys.executable, DISCOVER_PY,
            "--config-dir", cfg_dir,
            "--fixture-dir", FIXTURES_DIR,
            "--harnesses", "claude,codex,agy,grok",
            "--json",
        ],
        capture_output=True,
        text=True,
    )

    data = json.loads(res_json.stdout)
    top_keys = {"harnesses", "models", "unmapped", "retired"}
    model_keys = {"harness", "slug", "display_name", "lane", "lanes", "reason"}
    json_ok = (
        res_json.returncode == 0
        and set(data.keys()) == top_keys
        and all(set(m.keys()) == model_keys for m in data["models"])
        and len(data["models"]) == 5 + 14 + 2 + 1  # 5 codex + 14 agy + 2 grok + 1 claude
        and any(u["slug"] == "gpt-5.5" for u in data["unmapped"])
        and data["retired"] == []
    )
    record("CLI --json produces valid schema-compliant JSON document", json_ok, f"rc={res_json.returncode}")


# -------------------------------------------------------------
# 11. CLI execution: missing harness binary reported as missing
with tempfile.TemporaryDirectory() as td:
    cfg_dir = os.path.join(td, "cfg")
    os.makedirs(cfg_dir)
    shutil.copy(os.path.join(SAMPLES_DIR, "lanes.json"), cfg_dir)
    shutil.copy(os.path.join(SAMPLES_DIR, "routing.json"), cfg_dir)

    res_missing_cli = subprocess.run(
        [
            sys.executable, DISCOVER_PY,
            "--config-dir", cfg_dir,
            "--fixture-dir", FIXTURES_DIR,
            "--harnesses", "agy",
        ],
        capture_output=True,
        text=True,
    )

    out_missing = res_missing_cli.stdout
    missing_cli_ok = (
        res_missing_cli.returncode == 0
        and "codex   missing" in out_missing
        and "grok    missing" in out_missing
        and "claude  missing" in out_missing
        and "gemini-3.8-flash-high" in out_missing
    )
    record("CLI reports missing binary without error", missing_cli_ok, f"rc={res_missing_cli.returncode}")


# -------------------------------------------------------------
# 12. CLI execution: retired model tail in CLI output
with tempfile.TemporaryDirectory() as td:
    cfg_dir = os.path.join(td, "cfg")
    os.makedirs(cfg_dir)
    with open(os.path.join(SAMPLES_DIR, "lanes.json"), "r", encoding="utf-8") as f:
        lanes_doc = json.load(f)

    lanes_doc["lanes"]["retired-grok@grok"] = {
        "harness": "grok",
        "model": "grok-3.0-ancient",
        "effort": "high",
        "meter": "grok",
        "meter_weight": 1,
        "timeout": "30m",
        "price": {"in": 1, "cache_read": 0.1, "cache_write": None, "out": 2},
        "tier": 2,
        "basis": "ancient model test",
    }
    catalog.write_json(os.path.join(cfg_dir, "lanes.json"), lanes_doc)
    shutil.copy(os.path.join(SAMPLES_DIR, "routing.json"), cfg_dir)

    res_retired_cli = subprocess.run(
        [
            sys.executable, DISCOVER_PY,
            "--config-dir", cfg_dir,
            "--fixture-dir", FIXTURES_DIR,
            "--harnesses", "claude,codex,agy,grok",
        ],
        capture_output=True,
        text=True,
    )

    out_ret = res_retired_cli.stdout
    ret_cli_ok = (
        res_retired_cli.returncode == 0
        and "# lanes whose model no longer appears in harness" in out_ret
        and "retired-grok@grok" in out_ret
        and "model: grok-3.0-ancient" in out_ret
    )
    record("CLI reports retired model in tail", ret_cli_ok, f"rc={res_retired_cli.returncode}")

sys.exit(1 if fails else 0)
