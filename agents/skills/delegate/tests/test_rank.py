#!/usr/bin/env python3
"""test_rank.py — unit and CLI tests for rank.py. Run: python3 tests/test_rank.py"""
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DELEGATE_DIR = os.path.abspath(os.path.join(HERE, "..", "scripts"))
SAMPLES_DIR = os.path.abspath(os.path.join(HERE, "..", "assets", "samples"))
RANK_PY = os.path.join(DELEGATE_DIR, "rank.py")

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
    eligible1_ok = set(eligible_names) == {"terra-high@codex", "sol-high@codex", "grok46-high@grok", "fable-xhigh@claude"}
    vetoed1_ok = set(vetoed_names) == {"flash-high@agy", "luna-low@codex"}
    order1_ok = [r["lane"] for r in rows1] == [rows1[0]["lane"]] + [r["lane"] for r in rows1[1:] if r["eligible"]] + vetoed_names
    reasons1_ok = (
        all(r["reason"] == "eligible" for r in rows1[1:4]) and
        all(r["reason"] == "vetoed: ceiling (tier 1 < need 2)" for r in rows1[4:])
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
        "1. grok46-high@grok" in lines1[1] and lines1[1].endswith("pick") and
        "vetoed: ceiling (tier 1 < need 2)" in lines1[5] and
        "vetoed: ceiling (tier 1 < need 2)" in lines1[6]
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
    m3 = [
        meter("codex", weekly=0.55, five_h=0.55, pace=0.75, status="ok"),
        meter("grok", weekly=1.00, pace=0.80, status="ok"),
        meter("claude-fable", weekly=0.70, five_h=0.70, pace=1.00, status="ok"),
        meter("agy-gemini", weekly=0.61, five_h=0.61, pace=3.27, status="ok"),
    ]
    doc3 = write_meters_doc(meters_path, m3)

    rows3 = rank.rank("impl", cat, doc3, ALL_HARNESSES)
    pick3_ok = (
        rows3[0]["lane"] == "fable-xhigh@claude" and
        rows3[0]["pick"] is True and
        "stolen by pace: 1.0 >= 0.8 + 0.2" in rows3[0]["reason"]
    )
    record("case 3 rank() steal by higher tier", pick3_ok)

    res3 = subprocess.run(
        [sys.executable, RANK_PY, "impl", "--config-dir", cfg_dir, "--meters", meters_path, "--harnesses", ALL_HARNESSES_ARG],
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
        terra4["reason"] == "vetoed: gate (r 5% < 10%)" and
        sol4["reason"] == "vetoed: gate (r 5% < 10%)"
    )
    # Also verify scout (where luna has tier 1 >= 1, so luna gets vetoed: gate)
    rows4_scout = rank.rank("scout", cat, doc4, ALL_HARNESSES)
    luna4_scout = next(r for r in rows4_scout if r["lane"] == "luna-low@codex")
    luna_gate_ok = luna4_scout["reason"] == "vetoed: gate (r 5% < 10%)"
    record("case 4 rank() gate r 0.05", gate4_ok and luna_gate_ok)

    res4 = subprocess.run(
        [sys.executable, RANK_PY, "impl", "--config-dir", cfg_dir, "--meters", meters_path, "--harnesses", ALL_HARNESSES_ARG],
        capture_output=True,
        text=True,
    )
    cli4_ok = (
        res4.returncode == 0 and
        "1. grok46-high@grok" in res4.stdout and
        "vetoed: gate (r 5% < 10%)" in res4.stdout
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
        terra5["reason"] == "vetoed: gate (r 0% < 10%)" and
        sol5["reason"] == "vetoed: gate (r 0% < 10%)"
    )
    record("case 5 rank() gate uses r not weekly", gate5_ok)

    res5 = subprocess.run(
        [sys.executable, RANK_PY, "impl", "--config-dir", cfg_dir, "--meters", meters_path, "--harnesses", ALL_HARNESSES_ARG],
        capture_output=True,
        text=True,
    )
    cli5_ok = (res5.returncode == 0 and "vetoed: gate (r 0% < 10%)" in res5.stdout)
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
        lanes_order6 == ["grok46-high@grok", "fable-xhigh@claude", "terra-high@codex", "sol-high@codex"]
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
    cli7_rank_ok = (grok7["eligible"] is False and grok7["reason"] == "vetoed: cli absent (grok)")
    record("case 7 rank() CLI absent", cli7_rank_ok)

    res7 = subprocess.run(
        [sys.executable, RANK_PY, "impl", "--config-dir", cfg_dir, "--meters", meters_path, "--harnesses", "claude,codex,agy"],
        capture_output=True,
        text=True,
    )
    cli7_ok = (res7.returncode == 0 and "vetoed: cli absent (grok)" in res7.stdout)
    record("case 7 CLI absent", cli7_ok)

    # -------------------------------------------------------------
    # 8. Everything vetoed: hard-impl (need 3), codex r 0.05, no claude
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
    # 9. scout (need 1): tier 1 holds flash-high@agy and luna-low@codex
    # Part A: equal paces -> the tie falls to lane name, so flash wins
    m9a = [
        meter("codex", weekly=1.00, five_h=1.00, pace=1.00, status="ok"),
        meter("agy-gemini", weekly=1.00, five_h=1.00, pace=1.00, status="ok"),
        meter("grok", weekly=1.00, pace=1.00, status="ok"),
        meter("claude-fable", weekly=1.00, five_h=1.00, pace=1.00, status="ok"),
    ]
    doc9a = write_meters_doc(meters_path, m9a)
    rows9a = rank.rank("scout", cat, doc9a, ALL_HARNESSES)
    scout9a_ok = (rows9a[0]["lane"] == "flash-high@agy" and rows9a[0]["pick"] is True)

    # Part B: with agy pace 3.27 flash is pick either way
    m9b = [
        meter("codex", weekly=0.55, five_h=0.55, pace=0.75, status="ok"),
        meter("agy-gemini", weekly=0.61, five_h=0.61, pace=3.27, status="ok"),
        meter("grok", weekly=1.00, pace=0.90, status="ok"),
        meter("claude-fable", weekly=0.70, five_h=0.70, pace=0.85, status="ok"),
    ]
    doc9b = write_meters_doc(meters_path, m9b)
    rows9b = rank.rank("scout", cat, doc9b, ALL_HARNESSES)
    scout9b_ok = (rows9b[0]["lane"] == "flash-high@agy" and rows9b[0]["pick"] is True)

    # Part C: with luna pace 3.60 and flash 3.27, luna leads its tier on pace
    m9c = [
        meter("codex", weekly=0.90, five_h=0.90, pace=3.60, status="ok"),
        meter("agy-gemini", weekly=0.61, five_h=0.61, pace=3.27, status="ok"),
        meter("grok", weekly=1.00, pace=0.90, status="ok"),
        meter("claude-fable", weekly=0.70, five_h=0.70, pace=0.85, status="ok"),
    ]
    doc9c = write_meters_doc(meters_path, m9c)
    rows9c = rank.rank("scout", cat, doc9c, ALL_HARNESSES)
    scout9c_ok = (
        rows9c[0]["lane"] == "luna-low@codex" and
        rows9c[0]["pick"] is True and
        rows9c[0]["reason"] == "pick"
    )
    record("case 9 rank() scout tie-break and pace order", scout9a_ok and scout9b_ok and scout9c_ok)

    res9 = subprocess.run(
        [sys.executable, RANK_PY, "scout", "--config-dir", cfg_dir, "--meters", meters_path, "--harnesses", ALL_HARNESSES_ARG],
        capture_output=True,
        text=True,
    )
    lines9 = res9.stdout.strip().splitlines()
    cli9_ok = (
        res9.returncode == 0 and
        "1. luna-low@codex" in lines9[1] and
        lines9[1].endswith("pick")
    )
    record("case 9 CLI scout pace order", cli9_ok)

    # -------------------------------------------------------------
    # 10. Project override: fake git root with .delegate/routing.json
    fake_git = os.path.join(td, "repo")
    os.makedirs(fake_git)
    open(os.path.join(fake_git, ".git"), "w").close()
    p_dir = os.path.join(fake_git, ".delegate")
    p_file = os.path.join(p_dir, "routing.json")
    catalog.write_json(p_file, {"classTier": {"review": 3}})

    cat10 = catalog.load_catalog(cwd=fake_git, config_dir=cfg_dir)
    rows10 = rank.rank("review", cat10, doc1, ALL_HARNESSES)
    review10_ok = (rows10[0]["lane"] == "sol-high@codex" and rows10[0]["pick"] is True)
    record("case 10 rank() project override", review10_ok)

    res10 = subprocess.run(
        [sys.executable, RANK_PY, "review", "--cwd", fake_git, "--config-dir", cfg_dir, "--meters", meters_path, "--harnesses", ALL_HARNESSES_ARG],
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
        "lane", "harness", "model", "effort", "tier", "meter",
        "pace", "r", "remaining_weekly", "meter_status", "eligible", "pick", "reason"
    }
    top_keys_ok = all(k in data12 for k in ("class", "need", "margin", "gate", "pick", "rows"))
    pick_matches = (data12["pick"] == data12["rows"][0]["lane"] and data12["rows"][0]["pick"] is True)
    all_keys_ok = all(set(r.keys()) == required_row_keys for r in data12["rows"])
    record("case 12 CLI --json output schema", res12.returncode == 0 and top_keys_ok and pick_matches and all_keys_ok)

sys.exit(1 if fails else 0)
