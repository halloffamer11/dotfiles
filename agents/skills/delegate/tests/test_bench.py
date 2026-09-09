#!/usr/bin/env python3
"""test_bench.py — CLI tests for bench.py. Run: python3 tests/test_bench.py"""
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DELEGATE_DIR = os.path.abspath(os.path.join(HERE, "..", "scripts"))
SAMPLES_DIR = os.path.abspath(os.path.join(HERE, "..", "assets", "samples"))
BENCH_PY = os.path.join(DELEGATE_DIR, "bench.py")

HEADER = (
    "model_id,benchmark_id,performance,benchmark,benchmark_release_date,"
    "model,model_version,Model,date,source"
)
FIELDS = HEADER.split(",")

fails = 0


def record(name, ok, detail=""):
    global fails
    if ok:
        print(f"PASS {name}")
    else:
        fails += 1
        print(f"FAIL {name}: {detail}")


def write_epoch_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            full = {k: "" for k in FIELDS}
            full.update(row)
            writer.writerow(full)


def epoch_row(slug, effort, benchmark, performance, source="epoch", display=None):
    version = f"{slug}_{effort}" if effort else slug
    name = display or slug
    return {
        "model_id": slug,
        "benchmark_id": benchmark.lower().replace(" ", "-"),
        "performance": performance,
        "benchmark": benchmark,
        "benchmark_release_date": "2026-01-01",
        "model": name,
        "model_version": version,
        "Model": name,
        "date": "2026-09-01",
        "source": source,
    }


def fixture_rows():
    """Catalog models at max and some at high; one duplicate; one extra model; no Gemini.

    Hand-computed three-model, two-benchmark ranks (DeepSWE, FrontierCode):
      DeepSWE:      sol 0.90 r1, terra 0.80 r2, grok 0.70 r3
      FrontierCode: sol 0.85 r1, terra 0.85 r1, grok 0.60 r3  (tie shares rank 1; grok is 3)
      mean: sol 1.0 (n=2), terra 1.5 (n=2), grok 3.0 (n=2)
    sol high 0.90 is kept over sol max 0.99 and over the duplicate high 0.88.
    """
    return [
        epoch_row("gpt-5.6-sol", "high", "DeepSWE", "0.90", "alpha", "GPT-5.6 Sol"),
        epoch_row("gpt-5.6-sol", "high", "DeepSWE", "0.88", "beta", "GPT-5.6 Sol"),
        epoch_row("gpt-5.6-sol", "max", "DeepSWE", "0.99", "alpha", "GPT-5.6 Sol"),
        epoch_row("gpt-5.6-sol", "high", "FrontierCode", "0.85", "alpha", "GPT-5.6 Sol"),
        epoch_row("gpt-5.6-terra", "max", "DeepSWE", "0.80", "alpha", "GPT-5.6 Terra"),
        epoch_row("gpt-5.6-terra", "max", "FrontierCode", "0.85", "alpha", "GPT-5.6 Terra"),
        epoch_row("grok-4.6", "high", "DeepSWE", "0.70", "alpha", "Grok 4.6"),
        epoch_row("grok-4.6", "max", "DeepSWE", "0.99", "alpha", "Grok 4.6"),
        epoch_row("grok-4.6", "high", "FrontierCode", "0.60", "alpha", "Grok 4.6"),
        epoch_row("gpt-5.6-luna", "max", "APEX-Agents", "0.40", "alpha", "GPT-5.6 Luna"),
        epoch_row("gpt-5.6-luna", "max", "Terminal Bench", "0.30", "alpha", "GPT-5.6 Luna"),
        epoch_row("gpt-5.6-luna", "max", "SWE-Bench verified", "0.20", "alpha", "GPT-5.6 Luna"),
        epoch_row("claude-fable-5-1", "max", "APEX-Agents", "0.95", "alpha", "Claude Fable 5.1"),
        epoch_row("claude-fable-5-1", "max", "Terminal Bench", "0.90", "alpha", "Claude Fable 5.1"),
        epoch_row("claude-fable-5-1", "max", "SWE-Bench verified", "0.88", "alpha", "Claude Fable 5.1"),
        epoch_row("not-in-catalog-xyz", "max", "DeepSWE", "0.50", "alpha", "ZZZExtraModel"),
    ]


def aa_doc():
    return {
        "data": [
            {
                "slug": "gpt-5.6-sol",
                "evaluations": {
                    "coding_index": 80,
                    "agentic_index": 75,
                    "terminal_bench_hard": 60,
                },
                "median_output_tokens_per_second": 100,
            },
            {
                "slug": "gpt-5.6-terra",
                "evaluations": {
                    "coding_index": 70,
                    "agentic_index": 70,
                    "terminal_bench_hard": 55,
                },
                "median_output_tokens_per_second": 90,
            },
            {
                "slug": "gpt-5.6-luna",
                "evaluations": {
                    "coding_index": 40,
                    "agentic_index": 35,
                    "terminal_bench_hard": 20,
                },
                "median_output_tokens_per_second": 200,
            },
            {
                "slug": "grok-4.6",
                "evaluations": {
                    "coding_index": 65,
                    "agentic_index": 60,
                    "terminal_bench_hard": 50,
                },
                "median_output_tokens_per_second": 80,
            },
            {
                "slug": "claude-fable-5-1",
                "evaluations": {
                    "coding_index": 85,
                    "agentic_index": 80,
                    "terminal_bench_hard": 70,
                },
                "median_output_tokens_per_second": 40,
            },
            {
                "slug": "not-in-catalog-xyz",
                "evaluations": {
                    "coding_index": 99,
                    "agentic_index": 99,
                    "terminal_bench_hard": 99,
                },
                "median_output_tokens_per_second": 9,
            },
        ]
    }


def copy_config(td):
    cfg = os.path.join(td, "cfg")
    os.makedirs(cfg)
    shutil.copy(os.path.join(SAMPLES_DIR, "lanes.json"), os.path.join(cfg, "lanes.json"))
    shutil.copy(os.path.join(SAMPLES_DIR, "routing.json"), os.path.join(cfg, "routing.json"))
    return cfg


def run_bench(args, home):
    env = dict(os.environ)
    env["HOME"] = home
    return subprocess.run(
        [sys.executable, BENCH_PY, *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=DELEGATE_DIR,
    )


def epoch_row_for(report, model):
    in_epoch = False
    for line in report.splitlines():
        if line.startswith("## Epoch AI"):
            in_epoch = True
            continue
        if in_epoch and line.startswith("## "):
            break
        if in_epoch and line.startswith("|") and model in line.split("|")[2]:
            return line
    return ""


def gaps_section(report):
    idx = report.find("## Gaps and notes")
    return report[idx:] if idx >= 0 else ""


with tempfile.TemporaryDirectory() as td:
    home = os.path.join(td, "home")
    os.makedirs(home)
    cfg = copy_config(td)
    out_dir = os.path.join(td, "out")
    os.makedirs(out_dir)
    epoch_csv = os.path.join(td, "epoch.csv")
    write_epoch_csv(epoch_csv, fixture_rows())
    aa_json = os.path.join(td, "aa.json")
    with open(aa_json, "w", encoding="utf-8") as f:
        json.dump(aa_doc(), f)
    key_file = os.path.join(td, "aa-key")
    missing_key = os.path.join(td, "missing-aa-key")

    common = [
        "--config-dir", cfg,
        "--out-dir", out_dir,
        "--date", "2026-09-09",
        "--epoch-csv", epoch_csv,
        "--key-file", key_file,
    ]

    res = run_bench(common + ["--aa-json", aa_json], home)
    report_path = os.path.join(out_dir, "2026-09-09.md")
    report = ""
    if os.path.isfile(report_path):
        with open(report_path, encoding="utf-8") as f:
            report = f.read()
    record(
        "report written at <out-dir>/<date>.md",
        res.returncode == 0 and os.path.isfile(report_path) and f"bench: wrote {report_path}" in res.stdout,
        f"code={res.returncode} stdout={res.stdout!r} stderr={res.stderr!r} path_exists={os.path.isfile(report_path)}",
    )
    record(
        "both attribution lines present with --aa-json",
        "Source: Epoch AI, Benchmarking Hub, https://epoch.ai/data/eci_benchmarks.csv, CC-BY 4.0, fetched 2026-09-09" in report
        and "Source: Artificial Analysis, https://artificialanalysis.ai, free API, fetched 2026-09-09" in report,
        report[:800],
    )

    record(
        "only catalog models appear; extra model absent",
        "gpt-5.6-sol" in report
        and "ZZZExtraModel" not in report
        and "not-in-catalog-xyz" not in report,
        report,
    )

    gaps = gaps_section(report)
    record(
        "gemini-3.8-flash-high listed under gaps for Epoch and AA",
        "gemini-3.8-flash-high absent from Epoch AI" in gaps
        and "gemini-3.8-flash-high absent from Artificial Analysis" in gaps,
        gaps,
    )

    sol = epoch_row_for(report, "gpt-5.6-sol")
    terra = epoch_row_for(report, "gpt-5.6-terra")
    luna = epoch_row_for(report, "gpt-5.6-luna")
    grok = epoch_row_for(report, "grok-4.6")
    sol_parts = [p.strip() for p in sol.split("|")]
    terra_parts = [p.strip() for p in terra.split("|")]
    luna_parts = [p.strip() for p in luna.split("|")]
    record(
        "effort selection: high lane uses high not max",
        len(sol_parts) > 4 and sol_parts[3] == "high" and sol_parts[4] == "90.0" and "99.0" not in sol,
        sol,
    )
    record(
        "effort selection: only-max rows use max and notes say so",
        len(terra_parts) > 3 and terra_parts[3] == "max"
        and len(luna_parts) > 3 and luna_parts[3] == "max"
        and "gpt-5.6-terra DeepSWE used effort max (lane effort high)" in gaps
        and "gpt-5.6-luna APEX-Agents used effort max (lane effort low)" in gaps,
        f"terra={terra} luna={luna} gaps={gaps}",
    )

    record(
        "mean rank three-model two-benchmark case",
        "1.0 (n=2)" in sol and "1.5 (n=2)" in terra and "3.0 (n=2)" in grok,
        f"sol={sol} terra={terra} grok={grok}",
    )

    record(
        "duplicate (model, benchmark) keeps higher score and notes both",
        "90.0" in sol and "88.0" not in sol
        and "0.90 (alpha)" in gaps and "0.88 (beta)" in gaps,
        f"sol={sol} gaps={gaps}",
    )

    skip_out = os.path.join(td, "out-skip")
    os.makedirs(skip_out)
    res_skip = run_bench(
        [
            "--config-dir", cfg,
            "--out-dir", skip_out,
            "--date", "2026-09-09",
            "--epoch-csv", epoch_csv,
            "--key-file", missing_key,
        ],
        home,
    )
    skip_path = os.path.join(skip_out, "2026-09-09.md")
    skip_report = ""
    if os.path.isfile(skip_path):
        with open(skip_path, encoding="utf-8") as f:
            skip_report = f.read()
    record(
        "missing key file skips AA and still renders Epoch",
        res_skip.returncode == 0
        and "Artificial Analysis: skipped" in skip_report
        and "## Epoch AI" in skip_report
        and "DeepSWE" in skip_report
        and "gpt-5.6-sol" in skip_report
        and "Source: Artificial Analysis" not in skip_report,
        f"code={res_skip.returncode} stderr={res_skip.stderr!r} report={skip_report[:900]}",
    )

    record(
        "AA key detection names nested and top-level keys",
        "coding_index" in gaps
        and "agentic_index" in gaps
        and "terminal_bench_hard" in gaps
        and "median_output_tokens_per_second" in gaps,
        gaps,
    )

    empty_aa = os.path.join(td, "aa-empty.json")
    with open(empty_aa, "w", encoding="utf-8") as f:
        json.dump({"data": [{"slug": "gpt-5.6-sol", "foo_key": 1, "bar_key": 2}]}, f)
    empty_out = os.path.join(td, "out-empty-aa")
    os.makedirs(empty_out)
    res_empty = run_bench(
        [
            "--config-dir", cfg,
            "--out-dir", empty_out,
            "--date", "2026-09-09",
            "--epoch-csv", epoch_csv,
            "--aa-json", empty_aa,
            "--key-file", missing_key,
        ],
        home,
    )
    empty_path = os.path.join(empty_out, "2026-09-09.md")
    empty_report = ""
    if os.path.isfile(empty_path):
        with open(empty_path, encoding="utf-8") as f:
            empty_report = f.read()
    empty_gaps = gaps_section(empty_report)
    record(
        "AA JSON with no metric keys prints first object key names",
        res_empty.returncode == 0
        and "foo_key" in empty_gaps
        and "bar_key" in empty_gaps
        and "slug" in empty_gaps
        and "coding_index" not in empty_gaps,
        empty_gaps,
    )

    bad_csv = os.path.join(td, "bad.csv")
    with open(bad_csv, "w", encoding="utf-8") as f:
        f.write("foo,bar\n1,2\n")
    bad_out = os.path.join(td, "out-bad")
    os.makedirs(bad_out)
    res_bad = run_bench(
        [
            "--config-dir", cfg,
            "--out-dir", bad_out,
            "--date", "2026-09-09",
            "--epoch-csv", bad_csv,
            "--aa-json", aa_json,
            "--key-file", missing_key,
        ],
        home,
    )
    record(
        "CSV without expected header exits 1 with bench: message",
        res_bad.returncode == 1 and res_bad.stderr.startswith("bench: "),
        f"code={res_bad.returncode} stderr={res_bad.stderr!r}",
    )

sys.exit(1 if fails else 0)
