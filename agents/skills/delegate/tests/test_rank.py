#!/usr/bin/env python3
"""test_rank.py — unit and CLI tests for rank.py. Run: python3 tests/test_rank.py"""
import copy
import inspect
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
RANK_PY = os.path.join(DELEGATE_DIR, "rank.py")

sys.path.insert(0, DELEGATE_DIR)
import catalog
import rank
import usage

fails = 0


def record(name, ok, detail=""):
    global fails
    if ok:
        print(f"PASS {name}")
    else:
        fails += 1
        print(f"FAIL {name}: {detail}")


def meter(name, weekly=None, five_h=None, pace=None, status="ok", note=None):
    known = [x for x in (five_h, weekly) if x is not None]
    r = min(known) if known else None
    binding = None
    if r is not None:
        binding = "weekly" if (weekly is not None and (five_h is None or weekly <= five_h)) else "5h"
    harness = name.split("-")[0] if "-" in name else name
    meter_sub = name.split("-", 1)[1] if "-" in name else None
    return {
        "lane": name,
        "harness": harness,
        "meter": meter_sub,
        "remaining_5h": five_h,
        "remaining_weekly": weekly,
        "r": r,
        "binding": binding,
        "reset_5h": None,
        "reset_weekly": None,
        "reset_binding": None,
        "cycle_left": None,
        "pace": pace,
        "score": pace if pace is not None else r,
        "status": status,
        "rollover_soon": False,
        "note": note,
    }


def write_meters_doc(path, meters_list):
    doc = {"probed_at": 1700000000, "lanes": meters_list}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    return doc


ALL_HARNESSES = {"claude", "codex", "agy", "grok"}
ALL_HARNESSES_ARG = "claude,codex,agy,grok"

with tempfile.TemporaryDirectory() as td:
    cfg_dir = os.path.join(td, "cfg")
    os.makedirs(cfg_dir)
    shutil.copy(os.path.join(SAMPLES_DIR, "lanes.json"), cfg_dir)
    shutil.copy(os.path.join(SAMPLES_DIR, "routing.json"), cfg_dir)
    cat = catalog.load_catalog(config_dir=cfg_dir)

    meters_path = os.path.join(td, "meters.json")

    # -------------------------------------------------------------
    # 1. Healthy meters
    # codex pace 0.75, grok pace 0.90, claude-fable 0.85, agy 3.27
    m1 = [
        meter("codex", weekly=0.55, five_h=0.55, pace=0.75, status="ok"),
        meter("grok", weekly=1.00, pace=0.90, status="ok"),
        meter("claude-fable", weekly=0.70, five_h=0.70, pace=0.85, status="ok"),
        meter("claude-general", weekly=0.70, five_h=0.70, pace=0.85, status="ok"),
        meter("agy-gemini", weekly=0.61, five_h=0.61, pace=3.27, status="ok"),
    ]
    doc1 = write_meters_doc(meters_path, m1)

    rows1 = rank.rank("impl", cat, doc1, ALL_HARNESSES)
    pick1_ok = (rows1[0]["lane"] == "grok46-high@grok" and rows1[0]["pick"] is True and rows1[0]["reason"] == "pick")
    eligible_names = [r["lane"] for r in rows1 if r["eligible"]]
    vetoed_names = [r["lane"] for r in rows1 if not r["eligible"]]
    eligible1_ok = set(eligible_names) == {"terra-high@codex", "sol-high@codex", "grok46-high@grok"}
    vetoed1_ok = set(vetoed_names) == {"flash-high@agy", "luna-low@codex", "fable-xhigh@claude"}
    order1_ok = [r["lane"] for r in rows1] == [rows1[0]["lane"]] + [r["lane"] for r in rows1[1:] if r["eligible"]] + vetoed_names
    fable1 = next(r for r in rows1 if r["lane"] == "fable-xhigh@claude")
    luna1 = next(r for r in rows1 if r["lane"] == "luna-low@codex")
    flash1 = next(r for r in rows1 if r["lane"] == "flash-high@agy")
    reasons1_ok = (
        all(r["reason"] == "eligible" for r in rows1[1:3]) and
        fable1["reason"] == "vetoed:ceiling, fable-xhigh@claude (tier 4) > impl ceiling (tier 3)" and
        luna1["reason"] == "vetoed:floor, luna-low@codex (tier 1) < impl floor (tier 2)" and
        flash1["reason"] == "vetoed:floor, flash-high@agy (tier 1) < impl floor (tier 2)"
    )
    record("case 1 rank() healthy meters", pick1_ok and eligible1_ok and vetoed1_ok and order1_ok and reasons1_ok)

    res1 = subprocess.run(
        [sys.executable, RANK_PY, "impl", "--config-dir", cfg_dir, "--meters", meters_path, "--harnesses", ALL_HARNESSES_ARG],
        capture_output=True,
        text=True,
    )
    lines1 = res1.stdout.strip().splitlines()
    cli1_ok = (
        res1.returncode == 0 and
        lines1[0].startswith("# impl") and
        "floor=2 ceiling=3" in lines1[0] and
        "1. grok46-high@grok" in lines1[1] and lines1[1].endswith("pick") and
        "vetoed:ceiling, fable-xhigh@claude (tier 4) > impl ceiling (tier 3)" in res1.stdout and
        "vetoed:floor, luna-low@codex (tier 1) < impl floor (tier 2)" in res1.stdout
    )
    record("case 1 CLI healthy meters", cli1_ok)

    # -------------------------------------------------------------
    # 2. No steal inside a tier (trust removed 2026-09-10)
    # Sorting is (tier asc, pace desc), so the highest-paced lane in the tier is
    # already eligible[0]. Nothing behind it in the same tier can out-pace it,
    # so the steal rule can only ever fire across tiers (case 3).
    # grok pace 1.06 against codex 0.75
    m2 = [
        meter("codex", weekly=0.55, five_h=0.55, pace=0.75, status="ok"),
        meter("grok", weekly=1.00, pace=1.06, status="ok"),
        meter("claude-fable", weekly=0.70, five_h=0.70, pace=0.85, status="ok"),
        meter("agy-gemini", weekly=0.61, five_h=0.61, pace=3.27, status="ok"),
    ]
    doc2 = write_meters_doc(meters_path, m2)

    rows2 = rank.rank("impl", cat, doc2, ALL_HARNESSES)
    pick2_ok = (
        rows2[0]["lane"] == "grok46-high@grok" and
        rows2[0]["pick"] is True and
        rows2[0]["reason"] == "pick"
    )
    terra2 = next(r for r in rows2 if r["lane"] == "terra-high@codex")
    terra2_ok = (terra2["eligible"] is True and terra2["pick"] is False and terra2["reason"] == "eligible")
    record("case 2 rank() no steal inside tier", pick2_ok and terra2_ok)

    res2 = subprocess.run(
        [sys.executable, RANK_PY, "impl", "--config-dir", cfg_dir, "--meters", meters_path, "--harnesses", ALL_HARNESSES_ARG],
        capture_output=True,
        text=True,
    )
    lines2 = res2.stdout.strip().splitlines()
    cli2_ok = (
        res2.returncode == 0 and
        "1. grok46-high@grok" in lines2[1] and
        lines2[1].endswith("pick") and
        "terra-high@codex" in lines2[2] and lines2[2].endswith("eligible")
    )
    record("case 2 CLI no steal inside tier", cli2_ok)

    # -------------------------------------------------------------
    # 3. Steal by a higher tier
    # claude-fable pace 1.00 against codex 0.75 and grok 0.80
    cat3 = copy.deepcopy(cat)
    cat3["routing"]["classes"]["impl"]["ceiling"] = 4
    cfg3_dir = os.path.join(td, "cfg3")
    os.makedirs(cfg3_dir, exist_ok=True)
    shutil.copy(os.path.join(cfg_dir, "lanes.json"), cfg3_dir)
    catalog.write_json(os.path.join(cfg3_dir, "routing.json"), cat3["routing"])

    m3 = [
        meter("codex", weekly=0.55, five_h=0.55, pace=0.75, status="ok"),
        meter("grok", weekly=1.00, pace=0.80, status="ok"),
        meter("claude-fable", weekly=0.70, five_h=0.70, pace=1.00, status="ok"),
        meter("agy-gemini", weekly=0.61, five_h=0.61, pace=3.27, status="ok"),
    ]
    doc3 = write_meters_doc(meters_path, m3)

    rows3 = rank.rank("impl", cat3, doc3, ALL_HARNESSES)
    pick3_ok = (
        rows3[0]["lane"] == "fable-xhigh@claude" and
        rows3[0]["pick"] is True and
        "stolen by pace: 1.0 >= 0.8 + 0.2" in rows3[0]["reason"]
    )
    record("case 3 rank() steal by higher tier", pick3_ok)

    res3 = subprocess.run(
        [sys.executable, RANK_PY, "impl", "--config-dir", cfg3_dir, "--meters", meters_path, "--harnesses", ALL_HARNESSES_ARG],
        capture_output=True,
        text=True,
    )
    lines3 = res3.stdout.strip().splitlines()
    cli3_ok = (
        res3.returncode == 0 and
        "1. fable-xhigh@claude" in lines3[1] and
        "stolen by pace:" in lines3[1]
    )
    record("case 3 CLI steal by higher tier", cli3_ok)

    # -------------------------------------------------------------
    # 4. Gate: codex meter r 0.05
    m4 = [
        meter("codex", weekly=0.05, five_h=0.05, pace=0.75, status="unavailable"),
        meter("grok", weekly=1.00, pace=0.90, status="ok"),
        meter("claude-fable", weekly=0.70, five_h=0.70, pace=0.85, status="ok"),
        meter("agy-gemini", weekly=0.61, five_h=0.61, pace=3.27, status="ok"),
    ]
    doc4 = write_meters_doc(meters_path, m4)

    rows4 = rank.rank("impl", cat, doc4, ALL_HARNESSES)
    terra4 = next(r for r in rows4 if r["lane"] == "terra-high@codex")
    sol4 = next(r for r in rows4 if r["lane"] == "sol-high@codex")
    gate4_ok = (
        rows4[0]["lane"] == "grok46-high@grok" and
        terra4["reason"] == "vetoed:gate, terra-high@codex: codex meter 5% left < gate 10%" and
        sol4["reason"] == "vetoed:gate, sol-high@codex: codex meter 5% left < gate 10%"
    )
    # Also verify mechanical (where luna has tier 1 >= 1, so luna gets vetoed: gate)
    rows4_mech = rank.rank("mechanical", cat, doc4, ALL_HARNESSES)
    luna4_mech = next(r for r in rows4_mech if r["lane"] == "luna-low@codex")
    luna_gate_ok = luna4_mech["reason"] == "vetoed:gate, luna-low@codex: codex meter 5% left < gate 10%"
    record("case 4 rank() gate r 0.05", gate4_ok and luna_gate_ok)

    res4 = subprocess.run(
        [sys.executable, RANK_PY, "impl", "--config-dir", cfg_dir, "--meters", meters_path, "--harnesses", ALL_HARNESSES_ARG],
        capture_output=True,
        text=True,
    )
    cli4_ok = (
        res4.returncode == 0 and
        "1. grok46-high@grok" in res4.stdout and
        "vetoed:gate, terra-high@codex: codex meter 5% left < gate 10%" in res4.stdout
    )
    record("case 4 CLI gate r 0.05", cli4_ok)

    # -------------------------------------------------------------
    # 5. Gate uses r, not weekly alone: codex weekly 0.65 but 5h 0.00
    m5 = [
        meter("codex", weekly=0.65, five_h=0.00, pace=0.75, status="unavailable"),
        meter("grok", weekly=1.00, pace=0.90, status="ok"),
        meter("claude-fable", weekly=0.70, five_h=0.70, pace=0.85, status="ok"),
        meter("agy-gemini", weekly=0.61, five_h=0.61, pace=3.27, status="ok"),
    ]
    doc5 = write_meters_doc(meters_path, m5)

    rows5 = rank.rank("impl", cat, doc5, ALL_HARNESSES)
    terra5 = next(r for r in rows5 if r["lane"] == "terra-high@codex")
    sol5 = next(r for r in rows5 if r["lane"] == "sol-high@codex")
    gate5_ok = (
        terra5["reason"] == "vetoed:gate, terra-high@codex: codex meter 0% left < gate 10%" and
        sol5["reason"] == "vetoed:gate, sol-high@codex: codex meter 0% left < gate 10%"
    )
    record("case 5 rank() gate uses r not weekly", gate5_ok)

    res5 = subprocess.run(
        [sys.executable, RANK_PY, "impl", "--config-dir", cfg_dir, "--meters", meters_path, "--harnesses", ALL_HARNESSES_ARG],
        capture_output=True,
        text=True,
    )
    cli5_ok = (res5.returncode == 0 and "vetoed:gate, terra-high@codex: codex meter 0% left < gate 10%" in res5.stdout)
    record("case 5 CLI gate uses r not weekly", cli5_ok)

    # -------------------------------------------------------------
    # 6. Unknown meter: codex r, pace, weekly None, status unknown
    m6 = [
        meter("codex", weekly=None, five_h=None, pace=None, status="unknown"),
        meter("grok", weekly=1.00, pace=0.90, status="ok"),
        meter("claude-fable", weekly=0.70, five_h=0.70, pace=0.85, status="ok"),
        meter("agy-gemini", weekly=0.61, five_h=0.61, pace=3.27, status="ok"),
    ]
    doc6 = write_meters_doc(meters_path, m6)

    rows6 = rank.rank("impl", cat, doc6, ALL_HARNESSES)
    terra6 = next(r for r in rows6 if r["lane"] == "terra-high@codex")
    sol6 = next(r for r in rows6 if r["lane"] == "sol-high@codex")
    lanes_order6 = [r["lane"] for r in rows6 if r["eligible"]]
    unknown6_ok = (
        rows6[0]["lane"] == "grok46-high@grok" and
        terra6["eligible"] is True and terra6["reason"] == "unknown meter, sorted last" and
        sol6["eligible"] is True and sol6["reason"] == "unknown meter, sorted last" and
        lanes_order6 == ["grok46-high@grok", "terra-high@codex", "sol-high@codex"]
    )
    # With every meter unknown:
    m6_all_unknown = [
        meter("codex", weekly=None, five_h=None, pace=None, status="unknown"),
        meter("grok", weekly=None, five_h=None, pace=None, status="unknown"),
        meter("claude-fable", weekly=None, five_h=None, pace=None, status="unknown"),
        meter("claude-general", weekly=None, five_h=None, pace=None, status="unknown"),
        meter("agy-gemini", weekly=None, five_h=None, pace=None, status="unknown"),
    ]
    doc6_all = write_meters_doc(meters_path, m6_all_unknown)
    rows6_all = rank.rank("impl", cat, doc6_all, ALL_HARNESSES)
    all_unknown6_ok = (
        rows6_all[0]["lane"] == "grok46-high@grok" and
        rows6_all[0]["pick"] is True and
        rows6_all[0]["reason"] == "pick"
    )
    record("case 6 rank() unknown meter", unknown6_ok and all_unknown6_ok)

    res6 = subprocess.run(
        [sys.executable, RANK_PY, "impl", "--config-dir", cfg_dir, "--meters", meters_path, "--harnesses", ALL_HARNESSES_ARG],
        capture_output=True,
        text=True,
    )
    cli6_ok = (
        res6.returncode == 0 and
        "1. grok46-high@grok" in res6.stdout and
        "pick" in res6.stdout
    )
    record("case 6 CLI unknown meter", cli6_ok)

    # -------------------------------------------------------------
    # 7. CLI absent: --harnesses claude,codex,agy
    doc7 = write_meters_doc(meters_path, m1)
    present7 = {"claude", "codex", "agy"}
    rows7 = rank.rank("impl", cat, doc7, present7)
    grok7 = next(r for r in rows7 if r["lane"] == "grok46-high@grok")
    cli7_rank_ok = (grok7["eligible"] is False and grok7["reason"] == "vetoed:cli, grok46-high@grok: grok not on PATH")
    record("case 7 rank() CLI absent", cli7_rank_ok)

    res7 = subprocess.run(
        [sys.executable, RANK_PY, "impl", "--config-dir", cfg_dir, "--meters", meters_path, "--harnesses", "claude,codex,agy"],
        capture_output=True,
        text=True,
    )
    cli7_ok = (res7.returncode == 0 and "vetoed:cli, grok46-high@grok: grok not on PATH" in res7.stdout)
    record("case 7 CLI absent", cli7_ok)

    # -------------------------------------------------------------
    # 8. Everything vetoed: hard-impl (3-3), codex r 0.05, no claude
    m8 = [
        meter("codex", weekly=0.05, five_h=0.05, pace=0.75, status="unavailable"),
        meter("grok", weekly=1.00, pace=0.90, status="ok"),
        meter("claude-fable", weekly=0.70, five_h=0.70, pace=0.85, status="ok"),
        meter("agy-gemini", weekly=0.61, five_h=0.61, pace=3.27, status="ok"),
    ]
    doc8 = write_meters_doc(meters_path, m8)
    present8 = {"codex", "agy", "grok"}
    rows8 = rank.rank("hard-impl", cat, doc8, present8)
    rank8_ok = (
        len([r for r in rows8 if r["eligible"]]) == 0 and
        all(r["reason"].startswith("vetoed:") for r in rows8)
    )
    record("case 8 rank() everything vetoed", rank8_ok)

    res8 = subprocess.run(
        [sys.executable, RANK_PY, "hard-impl", "--config-dir", cfg_dir, "--meters", meters_path, "--harnesses", "codex,agy,grok"],
        capture_output=True,
        text=True,
    )
    lines8 = res8.stdout.strip().splitlines()
    cli8_ok = (
        res8.returncode == 1 and
        lines8[0].startswith("STOP: no lane eligible for hard-impl") and
        all("vetoed:" in line for line in lines8[1:])
    )
    record("case 8 CLI everything vetoed", cli8_ok)

    # -------------------------------------------------------------
    # 9. mechanical (1-2): tier 1 holds flash-high@agy and luna-low@codex.
    # agy combined Remaining/Pace are unknown, so flash sorts last and cannot steal.
    m9a = [
        meter("codex", weekly=1.00, five_h=1.00, pace=1.00, status="ok"),
        meter("agy-gemini", weekly=1.00, five_h=1.00, pace=1.00, status="ok"),
        meter("grok", weekly=1.00, pace=1.00, status="ok"),
        meter("claude-fable", weekly=1.00, five_h=1.00, pace=1.00, status="ok"),
    ]
    doc9a = write_meters_doc(meters_path, m9a)
    rows9a = rank.rank("mechanical", cat, doc9a, ALL_HARNESSES)
    flash9a = next(r for r in rows9a if r["lane"] == "flash-high@agy")
    mech9a_ok = (
        rows9a[0]["lane"] == "luna-low@codex" and rows9a[0]["pick"] is True
        and flash9a["eligible"] is True and flash9a["pace"] is None
        and flash9a["reason"] == "unknown meter, sorted last"
    )

    # Part B: invented agy pace 3.27 cannot steal the pick
    m9b = [
        meter("codex", weekly=0.55, five_h=0.55, pace=0.75, status="ok"),
        meter("agy-gemini", weekly=0.61, five_h=0.61, pace=3.27, status="ok"),
        meter("grok", weekly=1.00, pace=0.90, status="ok"),
        meter("claude-fable", weekly=0.70, five_h=0.70, pace=0.85, status="ok"),
    ]
    doc9b = write_meters_doc(meters_path, m9b)
    rows9b = rank.rank("mechanical", cat, doc9b, ALL_HARNESSES)
    mech9b_ok = (
        rows9b[0]["lane"] == "luna-low@codex" and rows9b[0]["pick"] is True
        and rows9b[0]["reason"] == "pick"
    )

    # Part C: luna still leads on its own known pace
    m9c = [
        meter("codex", weekly=0.90, five_h=0.90, pace=3.60, status="ok"),
        meter("agy-gemini", weekly=0.61, five_h=0.61, pace=3.27, status="ok"),
        meter("grok", weekly=1.00, pace=0.90, status="ok"),
        meter("claude-fable", weekly=0.70, five_h=0.70, pace=0.85, status="ok"),
    ]
    doc9c = write_meters_doc(meters_path, m9c)
    rows9c = rank.rank("mechanical", cat, doc9c, ALL_HARNESSES)
    mech9c_ok = (
        rows9c[0]["lane"] == "luna-low@codex" and
        rows9c[0]["pick"] is True and
        rows9c[0]["reason"] == "pick"
    )
    record("case 9 rank() mechanical agy unknown-last, no invented-pace steal", mech9a_ok and mech9b_ok and mech9c_ok)

    res9 = subprocess.run(
        [sys.executable, RANK_PY, "mechanical", "--config-dir", cfg_dir, "--meters", meters_path, "--harnesses", ALL_HARNESSES_ARG],
        capture_output=True,
        text=True,
    )
    lines9 = res9.stdout.strip().splitlines()
    cli9_ok = (
        res9.returncode == 0 and
        "1. luna-low@codex" in lines9[1] and
        lines9[1].endswith("pick")
    )
    record("case 9 CLI mechanical pace order", cli9_ok)

    # -------------------------------------------------------------
    # 10. Project override: fake git root with .delegate/routing.json
    fake_git = os.path.join(td, "repo")
    os.makedirs(fake_git)
    open(os.path.join(fake_git, ".git"), "w").close()
    p_dir = os.path.join(fake_git, ".delegate")
    p_file = os.path.join(p_dir, "routing.json")
    catalog.write_json(p_file, {"classes": {"impl": {"floor": 3}}})

    cat10 = catalog.load_catalog(cwd=fake_git, config_dir=cfg_dir)
    rows10 = rank.rank("impl", cat10, doc1, ALL_HARNESSES)
    impl10_ok = (rows10[0]["lane"] == "sol-high@codex" and rows10[0]["pick"] is True)
    record("case 10 rank() project override", impl10_ok)

    res10 = subprocess.run(
        [sys.executable, RANK_PY, "impl", "--cwd", fake_git, "--config-dir", cfg_dir, "--meters", meters_path, "--harnesses", ALL_HARNESSES_ARG],
        capture_output=True,
        text=True,
    )
    lines10 = res10.stdout.strip().splitlines()
    cli10_ok = (
        res10.returncode == 0 and
        f"project override: {p_file}" in lines10[0] and
        "1. sol-high@codex" in lines10[1] and lines10[1].endswith("pick")
    )
    record("case 10 CLI project override", cli10_ok)

    # -------------------------------------------------------------
    # 11. Unknown class foo -> exit 2 and message lists classes
    res11 = subprocess.run(
        [sys.executable, RANK_PY, "foo", "--config-dir", cfg_dir, "--meters", meters_path, "--harnesses", ALL_HARNESSES_ARG],
        capture_output=True,
        text=True,
    )
    cli11_ok = (
        res11.returncode == 2 and
        all(c in res11.stderr for c in catalog.CLASSES)
    )
    record("case 11 CLI unknown class exit 2", cli11_ok)

    # -------------------------------------------------------------
    # 12. --json output parses, pick matches first row, every row has all keys
    res12 = subprocess.run(
        [sys.executable, RANK_PY, "impl", "--config-dir", cfg_dir, "--meters", meters_path, "--harnesses", ALL_HARNESSES_ARG, "--json"],
        capture_output=True,
        text=True,
    )
    data12 = json.loads(res12.stdout)
    required_row_keys = {
        "lane", "harness", "model", "effort", "tier", "order", "meter",
        "pace", "r", "remaining_weekly", "meter_status", "eligible", "pick", "reason"
    }
    top_keys_ok = all(k in data12 for k in ("class", "floor", "ceiling", "margin", "gate", "pick", "rows"))
    pick_matches = (data12["pick"] == data12["rows"][0]["lane"] and data12["rows"][0]["pick"] is True)
    all_keys_ok = all(set(r.keys()) == required_row_keys for r in data12["rows"])
    record("case 12 CLI --json output schema", res12.returncode == 0 and top_keys_ok and pick_matches and all_keys_ok)

    # -------------------------------------------------------------
    # 13. Disabled lane: enabled: false on the lane that would otherwise be the pick
    cat13 = copy.deepcopy(cat)
    cat13["lanes"]["grok46-high@grok"]["enabled"] = False
    # Also disable luna-low@codex (tier 1 < floor 2) to verify disabled check is first in veto chain
    cat13["lanes"]["luna-low@codex"]["enabled"] = False

    rows13 = rank.rank("impl", cat13, doc1, ALL_HARNESSES)

    # Pick moves to next lane (terra-high@codex instead of grok46-high@grok)
    pick13_ok = (
        rows13[0]["lane"] == "terra-high@codex" and
        rows13[0]["pick"] is True and
        rows13[0]["reason"] == "pick"
    )

    grok13 = next((r for r in rows13 if r["lane"] == "grok46-high@grok"), None)
    grok13_ok = (
        grok13 is not None and
        grok13["eligible"] is False and
        grok13["pick"] is False and
        grok13["reason"] == "vetoed:disabled, grok46-high@grok"
    )

    luna13 = next((r for r in rows13 if r["lane"] == "luna-low@codex"), None)
    luna13_ok = (
        luna13 is not None and
        luna13["eligible"] is False and
        luna13["pick"] is False and
        luna13["reason"] == "vetoed:disabled, luna-low@codex"
    )

    record("case 13 rank() disabled lane moves pick", pick13_ok and grok13_ok and luna13_ok)

    # CLI test with disabled lane
    cfg13_dir = os.path.join(td, "cfg13")
    os.makedirs(cfg13_dir, exist_ok=True)
    lanes13_doc = catalog.load_json(os.path.join(cfg_dir, "lanes.json"))
    lanes13_doc["lanes"]["grok46-high@grok"]["enabled"] = False
    lanes13_doc["lanes"]["luna-low@codex"]["enabled"] = False
    catalog.write_json(os.path.join(cfg13_dir, "lanes.json"), lanes13_doc)
    shutil.copy(os.path.join(cfg_dir, "routing.json"), cfg13_dir)

    res13 = subprocess.run(
        [sys.executable, RANK_PY, "impl", "--config-dir", cfg13_dir, "--meters", meters_path, "--harnesses", ALL_HARNESSES_ARG],
        capture_output=True,
        text=True,
    )
    lines13 = res13.stdout.strip().splitlines()
    cli13_ok = (
        res13.returncode == 0 and
        "1. terra-high@codex" in lines13[1] and
        lines13[1].endswith("pick") and
        any("grok46-high@grok" in line and "vetoed:disabled, grok46-high@grok" in line for line in lines13) and
        any("luna-low@codex" in line and "vetoed:disabled, luna-low@codex" in line for line in lines13)
    )
    record("case 13 CLI disabled lane moves pick", cli13_ok)

    # -------------------------------------------------------------
    # 14. Lane below floor exact reason
    rows14 = rank.rank("impl", cat, doc1, ALL_HARNESSES)
    luna14 = next(r for r in rows14 if r["lane"] == "luna-low@codex")
    record("case 14 vetoed:floor exact reason",
           luna14["reason"] == "vetoed:floor, luna-low@codex (tier 1) < impl floor (tier 2)")

    # -------------------------------------------------------------
    # 15. Lane above ceiling exact reason
    fable15 = next(r for r in rows14 if r["lane"] == "fable-xhigh@claude")
    record("case 15 vetoed:ceiling exact reason",
           fable15["reason"] == "vetoed:ceiling, fable-xhigh@claude (tier 4) > impl ceiling (tier 3)")

    # -------------------------------------------------------------
    # 16. Replay of 2026-09-11
    # Fixture: fable-xhigh@claude at tier 4 and pace 0.85, grok46-high@grok at tier 3 and pace 0.59,
    # codex lanes below the gate, scout at 3-3. The pick is grok, and Fable is vetoed:ceiling.
    cat16 = copy.deepcopy(cat)
    cat16["lanes"]["grok46-high@grok"]["tier"] = 3
    cat16["routing"]["classes"]["scout"] = {"floor": 3, "ceiling": 3}
    m16 = [
        meter("codex", weekly=0.05, five_h=0.05, pace=0.75, status="unavailable"),
        meter("grok", weekly=1.00, pace=0.59, status="ok"),
        meter("claude-fable", weekly=0.70, five_h=0.70, pace=0.85, status="ok"),
        meter("agy-gemini", weekly=0.61, five_h=0.61, pace=3.27, status="ok"),
    ]
    doc16 = write_meters_doc(meters_path, m16)
    rows16 = rank.rank("scout", cat16, doc16, ALL_HARNESSES)
    fable16 = next(r for r in rows16 if r["lane"] == "fable-xhigh@claude")
    replay16_ok = (
        rows16[0]["lane"] == "grok46-high@grok" and
        rows16[0]["pick"] is True and
        fable16["reason"] == "vetoed:ceiling, fable-xhigh@claude (tier 4) > scout ceiling (tier 3)"
    )
    record("case 16 replay of 2026-09-11", replay16_ok)

    # -------------------------------------------------------------
    # 17. tier= inside range narrows eligible; outside range raises ValueError
    rows17_base = rank.rank("impl", cat, doc1, ALL_HARNESSES)
    eligible17_base = [r["lane"] for r in rows17_base if r["eligible"]]
    rows17_tier3 = rank.rank("impl", cat, doc1, ALL_HARNESSES, tier=3)
    eligible17_tier3 = [r["lane"] for r in rows17_tier3 if r["eligible"]]
    grok17 = next(r for r in rows17_tier3 if r["lane"] == "grok46-high@grok")
    tier_narrows_ok = (
        len(eligible17_base) == 3 and
        eligible17_tier3 == ["sol-high@codex"] and
        grok17["reason"] == "vetoed:floor, grok46-high@grok (tier 2) < impl floor (tier 3)"
    )
    raised_below = False
    try:
        rank.rank("impl", cat, doc1, ALL_HARNESSES, tier=1)
    except ValueError:
        raised_below = True

    raised_above = False
    try:
        rank.rank("impl", cat, doc1, ALL_HARNESSES, tier=4)
    except ValueError:
        raised_above = True

    record("case 17 tier= narrows eligible and raises outside range", tier_narrows_ok and raised_below and raised_above)

    # -------------------------------------------------------------
    # 18. A catalog with no `order` field ranks exactly as before ticket 28.
    # The rule before ticket 28, restated here on its own: sort by
    # (unknown pace last, tier, pace desc, lane name), then the steal loop.
    def rank_before_order(cls, cat_doc, meters_doc, present):
        rows = rank.rank(cls, cat_doc, meters_doc, present)
        eligible = [r for r in rows if r["eligible"]]

        def key(item):
            unknown = 1 if item["pace"] is None else 0
            t = item["tier"] if item["tier"] is not None else 99
            p = item["pace"] if item["pace"] is not None else 0.0
            return (unknown, t, -p, item["lane"])

        ordered = sorted(eligible, key=key)
        if not ordered:
            return []
        pick = ordered[0]
        margin = cat_doc["routing"]["margin"]
        for r in ordered[1:]:
            if r["pace"] is not None and pick["pace"] is not None and r["pace"] >= pick["pace"] + margin:
                pick = r
        return [pick["lane"]] + [r["lane"] for r in ordered if r is not pick]

    no_order18 = not any("order" in lane for c in (cat, cat3, cat16) for lane in c["lanes"].values())
    mismatches18 = []
    compared18 = 0
    for c in (cat, cat3, cat16):
        for d in (doc1, doc2, doc3, doc4, doc5, doc6, doc6_all, doc9a, doc9b, doc9c, doc16):
            for cls in catalog.CLASSES:
                rows = rank.rank(cls, c, d, ALL_HARNESSES)
                got = [r["lane"] for r in rows if r["eligible"]]
                want = rank_before_order(cls, c, d, ALL_HARNESSES)
                compared18 += 1
                if got != want or any(r["order"] is not None for r in rows):
                    mismatches18.append((cls, got, want))
    # the text output carries no order column when no lane has an order
    write_meters_doc(meters_path, m1)
    res18 = subprocess.run(
        [sys.executable, RANK_PY, "impl", "--config-dir", cfg_dir, "--meters", meters_path, "--harnesses", ALL_HARNESSES_ARG],
        capture_output=True,
        text=True,
    )
    record("case 18 a catalog with no order ranks exactly as before, on every fixture and class",
           no_order18 and compared18 == 165 and not mismatches18
           and res18.returncode == 0 and "order=" not in res18.stdout,
           repr(mismatches18[:3]))

    # -------------------------------------------------------------
    # 19. `order` orders a tier ahead of pace; a steal by margin can now happen inside a tier.
    # impl (2-3): tier 2 holds grok46-high@grok and terra-high@codex, tier 3 sol-high@codex.
    cat19 = copy.deepcopy(cat)
    cat19["lanes"]["terra-high@codex"]["order"] = 1
    cat19["lanes"]["grok46-high@grok"]["order"] = 2
    # m1: grok pace 0.90, codex 0.75. Without order grok leads tier 2 on pace;
    # with order terra leads, and 0.90 < 0.75 + 0.2, so no steal.
    rows19a = rank.rank("impl", cat19, doc1, ALL_HARNESSES)
    order19a_ok = (
        [r["lane"] for r in rows19a if r["eligible"]] == ["terra-high@codex", "grok46-high@grok", "sol-high@codex"]
        and rows19a[0]["pick"] is True and rows19a[0]["reason"] == "pick"
        and rows19a[0]["order"] == 1
    )
    # m2: grok pace 1.06 >= 0.75 + 0.2, so grok, second in the order, steals inside tier 2
    rows19b = rank.rank("impl", cat19, doc2, ALL_HARNESSES)
    steal19b_ok = (
        rows19b[0]["lane"] == "grok46-high@grok" and rows19b[0]["pick"] is True
        and rows19b[0]["reason"] == "stolen by pace: 1.06 >= 0.75 + 0.2"
        and rows19b[0]["tier"] == 2
    )
    # equal paces: a lane with an order sorts ahead of one without, and order never crosses tiers
    cat19c = copy.deepcopy(cat)
    cat19c["lanes"]["sol-high@codex"]["order"] = 1
    cat19c["lanes"]["terra-high@codex"]["order"] = 5
    rows19c = rank.rank("impl", cat19c, doc9a, ALL_HARNESSES)
    order19c_ok = [r["lane"] for r in rows19c if r["eligible"]] == ["terra-high@codex", "grok46-high@grok", "sol-high@codex"]
    record("case 19 rank() orders a tier by order, then pace; a steal by margin can happen inside a tier",
           order19a_ok and steal19b_ok and order19c_ok,
           repr(([r["lane"] for r in rows19a], rows19b[0]["reason"], [r["lane"] for r in rows19c])))

    cfg19_dir = os.path.join(td, "cfg19")
    os.makedirs(cfg19_dir, exist_ok=True)
    lanes19_doc = catalog.load_json(os.path.join(cfg_dir, "lanes.json"))
    lanes19_doc["lanes"]["terra-high@codex"]["order"] = 1
    lanes19_doc["lanes"]["grok46-high@grok"]["order"] = 2
    catalog.write_json(os.path.join(cfg19_dir, "lanes.json"), lanes19_doc)
    shutil.copy(os.path.join(cfg_dir, "routing.json"), cfg19_dir)
    write_meters_doc(meters_path, m1)
    res19 = subprocess.run(
        [sys.executable, RANK_PY, "impl", "--config-dir", cfg19_dir, "--meters", meters_path, "--harnesses", ALL_HARNESSES_ARG, "--json"],
        capture_output=True,
        text=True,
    )
    data19 = json.loads(res19.stdout)
    res19t = subprocess.run(
        [sys.executable, RANK_PY, "impl", "--config-dir", cfg19_dir, "--meters", meters_path, "--harnesses", ALL_HARNESSES_ARG],
        capture_output=True,
        text=True,
    )
    lines19 = res19t.stdout.strip().splitlines()
    record("case 19 CLI order picks inside a tier and prints its order",
           res19.returncode == 0 and data19["pick"] == "terra-high@codex"
           and [r["order"] for r in data19["rows"] if r["eligible"]] == [1, 2, None]
           and "1. terra-high@codex" in lines19[1] and "order=1 " in lines19[1]
           and any("sol-high@codex" in line and "order=- " in line for line in lines19),
           res19.stdout[:400] + res19t.stdout)

    # -------------------------------------------------------------
    # 20. Exact-Tier previews use the canonical range rule and return only
    # lanes in that Tier. These fixture tiers and orders are deliberately local
    # to this test: no expectation depends on the live catalog's assignments.
    tier_cat = copy.deepcopy(cat)
    tier_layout = {
        "flash-high@agy": (1, 1),
        "luna-low@codex": (1, 2),
        "grok46-high@grok": (2, 1),
        "terra-high@codex": (2, 2),
        "sol-high@codex": (3, 1),
        "fable-xhigh@claude": (4, 1),
    }
    for lane_name, (tier, order) in tier_layout.items():
        tier_cat["lanes"][lane_name]["tier"] = tier
        tier_cat["lanes"][lane_name]["order"] = order

    tier_meters = {
        "probed_at": 1700000000,
        "lanes": [
            meter("codex", weekly=0.80, five_h=0.80, pace=0.80, status="ok"),
            meter("grok", weekly=0.80, pace=0.90, status="ok"),
            meter("claude-fable", weekly=0.80, five_h=0.80, pace=0.70, status="ok"),
            meter("agy-gemini", weekly=0.80, five_h=0.80, pace=0.85, status="ok"),
        ]
    }
    previews20 = rank.tier_leaders(tier_cat, tier_meters, ALL_HARNESSES)
    expected_leaders20 = ["luna-low@codex", "grok46-high@grok", "sol-high@codex", "fable-xhigh@claude"]
    shape20_ok = (
        [preview["tier"] for preview in previews20] == [1, 2, 3, 4]
        and [preview["leader"] for preview in previews20] == expected_leaders20
        and all(
            row["tier"] == preview["tier"]
            and isinstance(row["eligible"], bool)
            and bool(row["reason"])
            for preview in previews20
            for row in preview["rows"]
        )
    )
    record("case 20 tier_leaders() returns four exact-Tier previews", shape20_ok)

    # First in Order leads when the later lane is less than Margin ahead.
    tier2_20 = previews20[1]
    order20_ok = (
        tier2_20["leader"] == "grok46-high@grok"
        and [row["lane"] for row in tier2_20["rows"]] == ["grok46-high@grok", "terra-high@codex"]
        and tier2_20["rows"][0]["reason"] == "pick"
        and tier2_20["rows"][1]["reason"] == "eligible"
    )
    record("case 20 tier leader starts with first eligible lane in Order", order20_ok)

    # Gate veto: first-in-Order Grok is below Gate, so Terra leads.
    gate_meters20 = copy.deepcopy(tier_meters)
    grok_gate20 = next(row for row in gate_meters20["lanes"] if row["lane"] == "grok")
    grok_gate20.update({"r": 0.05, "remaining_weekly": 0.05, "status": "unavailable"})
    gate_preview20 = rank.tier_leaders(tier_cat, gate_meters20, ALL_HARNESSES)[1]
    grok_row20 = next(row for row in gate_preview20["rows"] if row["lane"] == "grok46-high@grok")
    gate20_ok = (
        gate_preview20["leader"] == "terra-high@codex"
        and not grok_row20["eligible"]
        and grok_row20["reason"] == "vetoed:gate, grok46-high@grok: grok meter 5% left < gate 10%"
    )
    record("case 20 tier leader skips a lane below Gate", gate20_ok)

    # Margin steal: the later Terra lane is at least Margin ahead of Grok.
    steal_meters20 = copy.deepcopy(tier_meters)
    next(row for row in steal_meters20["lanes"] if row["lane"] == "grok")["pace"] = 0.70
    next(row for row in steal_meters20["lanes"] if row["lane"] == "codex")["pace"] = 0.95
    steal_preview20 = rank.tier_leaders(tier_cat, steal_meters20, ALL_HARNESSES)[1]
    steal20_ok = (
        steal_preview20["leader"] == "terra-high@codex"
        and steal_preview20["rows"][0]["reason"] == "stolen by pace: 0.95 >= 0.7 + 0.2"
    )
    record("case 20 later lane steals Tier lead by Margin", steal20_ok)

    # Unknown observations remain eligible, sort last, and never invent pace.
    unknown_meters20 = copy.deepcopy(tier_meters)
    unknown_grok20 = next(row for row in unknown_meters20["lanes"] if row["lane"] == "grok")
    unknown_grok20.update({"r": None, "pace": None, "remaining_weekly": None, "status": "unknown"})
    unknown_preview20 = rank.tier_leaders(tier_cat, unknown_meters20, ALL_HARNESSES)[1]
    unknown_row20 = next(row for row in unknown_preview20["rows"] if row["lane"] == "grok46-high@grok")
    unknown20_ok = (
        unknown_preview20["leader"] == "terra-high@codex"
        and unknown_row20["eligible"]
        and unknown_row20["pace"] is None
        and unknown_row20["reason"] == "unknown meter, sorted last"
    )
    record("case 20 unknown Meter keeps safe ranking behavior", unknown20_ok)

    # Harness veto, name tie-break, and a Tier with no eligible lane.
    missing_preview20 = rank.tier_leaders(tier_cat, tier_meters, ALL_HARNESSES - {"claude"})[3]
    missing20_ok = (
        missing_preview20["leader"] is None
        and missing_preview20["rows"][0]["reason"] == "vetoed:cli, fable-xhigh@claude: claude not on PATH"
    )
    tie_cat20 = copy.deepcopy(tier_cat)
    tie_cat20["lanes"]["grok46-high@grok"].pop("order")
    tie_cat20["lanes"]["terra-high@codex"].pop("order")
    tie_meters20 = copy.deepcopy(tier_meters)
    next(row for row in tie_meters20["lanes"] if row["lane"] == "grok")["pace"] = 0.80
    tie_preview20 = rank.tier_leaders(tie_cat20, tie_meters20, ALL_HARNESSES)[1]
    tie20_ok = tie_preview20["leader"] == "grok46-high@grok"
    record("case 20 harness veto, empty Tier leader, and deterministic name tie", missing20_ok and tie20_ok)

    # Text and JSON CLI expose the same four previews. With no --meters, the
    # Tier command reads the named cache directly; a missing cache yields
    # unknown observations rather than invoking usage.py and probing vendors.
    cfg20_dir = os.path.join(td, "cfg20")
    os.makedirs(cfg20_dir, exist_ok=True)
    lanes20_doc = catalog.load_json(os.path.join(cfg_dir, "lanes.json"))
    for lane_name, (tier, order) in tier_layout.items():
        lanes20_doc["lanes"][lane_name]["tier"] = tier
        lanes20_doc["lanes"][lane_name]["order"] = order
    catalog.write_json(os.path.join(cfg20_dir, "lanes.json"), lanes20_doc)
    shutil.copy(os.path.join(cfg_dir, "routing.json"), cfg20_dir)
    write_meters_doc(meters_path, tier_meters["lanes"])
    res20_json = subprocess.run(
        [sys.executable, RANK_PY, "tiers", "--config-dir", cfg20_dir, "--meters", meters_path,
         "--harnesses", ALL_HARNESSES_ARG, "--json"],
        capture_output=True,
        text=True,
    )
    data20_json = json.loads(res20_json.stdout)
    res20_text = subprocess.run(
        [sys.executable, RANK_PY, "tiers", "--config-dir", cfg20_dir, "--meters", meters_path,
         "--harnesses", ALL_HARNESSES_ARG],
        capture_output=True,
        text=True,
    )
    missing_cache20 = os.path.join(td, "missing-usage.json")
    env20 = dict(os.environ, DELEGATE_CACHE=missing_cache20)
    res20_missing = subprocess.run(
        [sys.executable, RANK_PY, "tiers", "--config-dir", cfg20_dir,
         "--harnesses", ALL_HARNESSES_ARG, "--json"],
        capture_output=True,
        text=True,
        env=env20,
    )
    data20_missing = json.loads(res20_missing.stdout)
    cli20_ok = (
        res20_json.returncode == 0
        and [preview["tier"] for preview in data20_json["tiers"]] == [1, 2, 3, 4]
        and [preview["leader"] for preview in data20_json["tiers"]] == expected_leaders20
        and res20_text.returncode == 0
        and res20_text.stdout.count("preview; not a Class Pick") == 4
        and res20_missing.returncode == 0
        and all(
            row["meter_status"] == "unknown" and row["pace"] is None and row["r"] is None
            for preview in data20_missing["tiers"]
            for row in preview["rows"]
        )
    )
    record("case 20 Tier CLI text/JSON and missing-cache behavior", cli20_ok,
           res20_json.stderr + res20_text.stderr + res20_missing.stderr)

    # 21. All callers use one validity rule; malformed observations are unknown.
    legacy21 = {entry["lane"]: entry for entry in tier_meters["lanes"]}
    record("case 21 valid wrapped and legacy Meter inputs agree",
           rank.rank("review", tier_cat, legacy21, ALL_HARNESSES)
           == rank.rank("review", tier_cat, tier_meters, ALL_HARNESSES)
           and rank.tier_leaders(tier_cat, legacy21, ALL_HARNESSES)
           == rank.tier_leaders(tier_cat, tier_meters, ALL_HARNESSES))
    for field21, value21 in (("pace", "bad"), ("pace", float("inf")),
                             ("pace", 10 ** 400), ("r", True), ("status", 42)):
        bad21 = copy.deepcopy(tier_meters)
        bad21["lanes"].append({"lane": "unused", field21: value21})
        rows21 = rank.rank("review", tier_cat, bad21, ALL_HARNESSES)
        tiers21 = rank.tier_leaders(tier_cat, bad21, ALL_HARNESSES)
        observed21 = rows21 + [row for tier in tiers21 for row in tier["rows"]]
        record(f"case 21 malformed {field21} becomes unknown for Class and Tier ranking",
               all(row["r"] is None and row["pace"] is None
                   and row["meter_status"] == "unknown" for row in observed21))
        json.dumps(observed21, allow_nan=False)

    record("rank.rank has no unused effort parameter",
           "effort" not in inspect.signature(rank.rank).parameters)
    record("rank.meter_observations re-exports usage.observations",
           rank.meter_observations is usage.observations
           or rank.meter_observations({"lanes": []}) == usage.observations({"lanes": []}))

    # 22. Remaining equal to Gate is eligible; cached status is not a veto.
    m22 = [
        meter("codex", weekly=0.10, five_h=0.10, pace=0.75, status="unavailable"),
        meter("grok", weekly=1.00, pace=0.90, status="ok"),
        meter("claude-fable", weekly=0.70, five_h=0.70, pace=0.85, status="ok"),
        meter("agy-gemini", weekly=0.61, five_h=0.61, pace=3.27, status="ok"),
    ]
    doc22 = write_meters_doc(meters_path, m22)
    rows22 = rank.rank("impl", cat, doc22, ALL_HARNESSES)
    terra22 = next(r for r in rows22 if r["lane"] == "terra-high@codex")
    record("case 22 r equal to gate is eligible and status is ignored",
           terra22["eligible"] is True and terra22["reason"] in ("eligible", "pick", "unknown meter, sorted last"))

    # Project Gate override: r=0.20 passes global 0.10 and fails project 0.50.
    fake_git_gate = os.path.join(td, "repo-gate")
    os.makedirs(fake_git_gate)
    open(os.path.join(fake_git_gate, ".git"), "w").close()
    p_gate = os.path.join(fake_git_gate, ".delegate")
    os.makedirs(p_gate)
    catalog.write_json(os.path.join(p_gate, "routing.json"), {"gate": 0.5})
    cat_gate = catalog.load_catalog(cwd=fake_git_gate, config_dir=cfg_dir)
    m_gate = [
        meter("codex", weekly=0.20, five_h=0.20, pace=0.75, status="ok"),
        meter("grok", weekly=1.00, pace=0.90, status="ok"),
        meter("claude-fable", weekly=0.70, five_h=0.70, pace=0.85, status="ok"),
        meter("agy-gemini", weekly=0.61, five_h=0.61, pace=3.27, status="ok"),
    ]
    doc_gate = write_meters_doc(meters_path, m_gate)
    rows_global = rank.rank("impl", cat, doc_gate, ALL_HARNESSES)
    rows_project = rank.rank("impl", cat_gate, doc_gate, ALL_HARNESSES)
    terra_global = next(r for r in rows_global if r["lane"] == "terra-high@codex")
    terra_project = next(r for r in rows_project if r["lane"] == "terra-high@codex")
    record("case 22 project gate overrides global gate at meter granularity",
           terra_global["eligible"] is True
           and terra_project["eligible"] is False
           and "vetoed:gate" in terra_project["reason"]
           and "gate 50%" in terra_project["reason"])

    # 23. agy remains eligible unknown-last; picked when measured alternatives are unavailable.
    m23 = [
        meter("codex", weekly=0.05, five_h=0.05, pace=0.75, status="unavailable"),
        meter("agy-gemini", weekly=0.61, five_h=0.61, pace=3.27, status="ok"),
        meter("grok", weekly=0.05, pace=0.05, status="unavailable"),
        meter("claude-fable", weekly=0.70, five_h=0.70, pace=0.85, status="ok"),
    ]
    doc23 = write_meters_doc(meters_path, m23)
    rows23 = rank.rank("mechanical", cat, doc23, ALL_HARNESSES)
    flash23 = next(r for r in rows23 if r["lane"] == "flash-high@agy")
    record("case 23 agy is picked when measured alternatives are gated; windows stay on the row",
           rows23[0]["lane"] == "flash-high@agy" and rows23[0]["pick"] is True
           and flash23["r"] is None and flash23["pace"] is None
           and flash23["remaining_weekly"] == 0.61
           and flash23["eligible"] is True)

    # 24. Cache path and cached-only tiers: no vendor probe.
    record("load_cached_usage uses usage.get_cache_path",
           rank.load_cached_usage.__doc__ is not None)
    missing_cache24 = os.path.join(td, "missing-usage-24.json")
    os.environ["DELEGATE_CACHE"] = missing_cache24
    probed24 = []
    orig_probe = usage.probe
    origs = (usage.probe_codex, usage.probe_agy, usage.probe_claude, usage.probe_grok)
    def mark_probe(*a, **k):
        probed24.append("probe")
        return orig_probe(*a, **k)
    def boom_vendor(*a, **k):
        probed24.append("vendor")
        return [usage.lane("codex", None, note="stub")]
    usage.probe = mark_probe
    usage.probe_codex = usage.probe_agy = usage.probe_claude = usage.probe_grok = boom_vendor
    try:
        cached24 = rank.load_cached_usage()
        record("load_cached_usage on missing cache is {} and does not probe",
               cached24 == {} and probed24 == [])
        previews24 = rank.tier_leaders(tier_cat, cached24, ALL_HARNESSES)
        record("tier_leaders with missing cache does not probe",
               probed24 == [] and all(
                   row["r"] is None and row["pace"] is None
                   for preview in previews24 for row in preview["rows"]
               ))
    finally:
        usage.probe = orig_probe
        usage.probe_codex, usage.probe_agy, usage.probe_claude, usage.probe_grok = origs
        os.environ.pop("DELEGATE_CACHE", None)

sys.exit(1 if fails else 0)
