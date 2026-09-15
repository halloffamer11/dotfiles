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

# Run from a fresh directory with no Git root above it, so that
# `catalog.find_git_root()` never finds the invoking checkout's own
# `.delegate/routing.json`. Every path this file needs comes from HERE.
_ISOLATED_CWD = tempfile.TemporaryDirectory(prefix="delegate-test-")
os.chdir(_ISOLATED_CWD.name)
DELEGATE_DIR = os.path.abspath(os.path.join(HERE, "..", "scripts"))
SAMPLES_DIR = os.path.abspath(os.path.join(HERE, "..", "assets", "samples"))
BENCH_PY = os.path.join(DELEGATE_DIR, "bench.py")
sys.path.insert(0, DELEGATE_DIR)

import bench  # noqa: E402  (after sys.path, as the other test files do)
import catalog  # noqa: E402

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


AA_URL = "https://artificialanalysis.ai/models/gpt-5-6-sol-high"


def aa_row(model, effort, benchmark, score, cost, composite=False):
    """One accepted row in the shape `effort.py aa` writes: the display name AA
    prints, the effort word of the variant, and the index's cost per task."""
    row = {"source": "aa", "url": AA_URL, "model": model, "effort": effort,
           "benchmark": benchmark, "score": score, "score_unit": None, "cost_usd": cost,
           "tokens": 1000.0, "observed": "2026-09-11", "provenance": "unlabelled",
           "uncertain": effort == "none", "variant": f"{model} ({effort})", "reasons": []}
    if composite:
        row["composite"] = True
    return row


def aa_rows():
    """Sample-catalog models at several efforts, the composite, a none row, an
    extra model, and a row of another source. No Gemini row.

    Model view, one effort per model (the strongest lane effort measured):
      Terminal-Bench 2.1: fable 0.90 r1, sol 0.80 r2, terra 0.70 r3, grok(medium) 0.50 r4, luna 0.30 r5
      GPQA Diamond:       sol 0.90 r1, terra 0.85 r2
      Omniscience:        fable -12.5 r1
      mean: sol 1.5 (n=2), terra 2.5 (n=2), fable 1.0 (n=2)
    """
    return [
        aa_row("GPT-5.6 Sol", "high", "Terminal-Bench 2.1", 0.80, 0.81),
        aa_row("GPT-5.6 Sol", "high", "GPQA Diamond", 0.90, 0.81),
        aa_row("GPT-5.6 Sol", "high", "Artificial Analysis Intelligence Index", 50.0, 0.81, composite=True),
        aa_row("GPT-5.6 Sol", "low", "Terminal-Bench 2.1", 0.60, 0.20),
        aa_row("GPT-5.6 Terra", "high", "Terminal-Bench 2.1", 0.70, 0.40),
        aa_row("GPT-5.6 Terra", "high", "GPQA Diamond", 0.85, 0.40),
        aa_row("GPT-5.6 Luna", "low", "Terminal-Bench 2.1", 0.30, 0.05),
        aa_row("Grok 4.6", "none", "Terminal-Bench 2.1", 0.99, 0.01),
        aa_row("Grok 4.6", "medium", "Terminal-Bench 2.1", 0.50, 0.30),
        aa_row("Claude Fable 5.1", "xhigh", "Terminal-Bench 2.1", 0.90, 2.50),
        aa_row("Claude Fable 5.1", "xhigh", "Omniscience", -12.5, 2.50),
        aa_row("Claude Fable 5.1", "low", "Terminal-Bench 2.1", 0.55, 0.90),
        aa_row("ZZZExtraModel", "high", "Terminal-Bench 2.1", 0.99, 0.10),
        {"source": "tbench", "model": "GPT-5.6 Sol", "effort": "high", "benchmark": "Terminal-Bench 4.0",
         "score": 40.0, "cost_usd": 100.0},
    ]


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


def aa_row_for(report, model):
    in_aa = False
    for line in report.splitlines():
        if line.startswith("## Artificial Analysis"):
            in_aa = True
            continue
        if in_aa and line.startswith("## "):
            break
        if in_aa and line.startswith("|") and model in line.split("|")[2]:
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
    rows_json = os.path.join(td, "aa-accepted.json")
    with open(rows_json, "w", encoding="utf-8") as f:
        json.dump(aa_rows(), f)

    common = [
        "--config-dir", cfg,
        "--out-dir", out_dir,
        "--date", "2026-09-09",
        "--epoch-csv", epoch_csv,
    ]

    res = run_bench(common + ["--effort-rows", rows_json], home)
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
    # replaces "both attribution lines present with --aa-json" (ticket 19)
    record(
        "both attribution lines present with --effort-rows",
        "Source: Epoch AI, Benchmarking Hub, https://epoch.ai/data/eci_benchmarks.csv, CC-BY 4.0, fetched 2026-09-09" in report
        and f"Source: Artificial Analysis, {AA_URL}, per-effort rows accepted by effort.py aa, observed 2026-09-11" in report
        and "free API" not in report,
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

    # replaces "missing key file skips AA and still renders Epoch": there is
    # no key any more, so the case where AA cannot be read is no rows given
    skip_out = os.path.join(td, "out-skip")
    os.makedirs(skip_out)
    res_skip = run_bench(
        ["--config-dir", cfg, "--out-dir", skip_out, "--date", "2026-09-09", "--epoch-csv", epoch_csv],
        home,
    )
    skip_path = os.path.join(skip_out, "2026-09-09.md")
    skip_report = ""
    if os.path.isfile(skip_path):
        with open(skip_path, encoding="utf-8") as f:
            skip_report = f.read()
    record(
        "no effort rows skips AA with the reason and still renders Epoch",
        res_skip.returncode == 0
        and f"Artificial Analysis: skipped ({bench.AA_NO_ROWS})" in skip_report
        and "## Epoch AI" in skip_report
        and "DeepSWE" in skip_report
        and "gpt-5.6-sol" in skip_report
        and "Source: Artificial Analysis" not in skip_report,
        f"code={res_skip.returncode} stderr={res_skip.stderr!r} report={skip_report[:900]}",
    )

    # replaces "AA key detection names nested and top-level keys": which
    # fields become columns is now which benchmarks the rows carry
    aa_header = next((l for l in report[report.find("## Artificial Analysis"):].splitlines()
                      if l.startswith("| Lane(s)")), "")
    record(
        "AA columns are the component benchmarks, in row order, with cost per task; the composite is not one",
        aa_header == "| Lane(s) | Model | Effort | Terminal-Bench 2.1 | GPQA Diamond | Omniscience "
                     "| Cost/task (USD) | Mean rank |"
        and "Intelligence Index" not in report,
        aa_header,
    )

    # replaces "AA JSON with no metric keys prints first object key names": a
    # rows file that holds no AA row says why AA is missing
    other_json = os.path.join(td, "tbench-only.json")
    with open(other_json, "w", encoding="utf-8") as f:
        json.dump([r for r in aa_rows() if r["source"] != "aa"], f)
    other_out = os.path.join(td, "out-other")
    os.makedirs(other_out)
    res_other = run_bench(
        ["--config-dir", cfg, "--out-dir", other_out, "--date", "2026-09-09",
         "--epoch-csv", epoch_csv, "--effort-rows", other_json],
        home,
    )
    other_report = ""
    if os.path.isfile(os.path.join(other_out, "2026-09-09.md")):
        with open(os.path.join(other_out, "2026-09-09.md"), encoding="utf-8") as f:
            other_report = f.read()
    record(
        "effort rows with no Artificial Analysis row skip AA and name the flag that gives them",
        res_other.returncode == 0 and "Artificial Analysis: skipped" in other_report
        and "--effort-rows" in other_report,
        other_report[:600],
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
            "--effort-rows", rows_json,
        ],
        home,
    )
    record(
        "CSV without expected header exits 1 with bench: message",
        res_bad.returncode == 1 and res_bad.stderr.startswith("bench: "),
        f"code={res_bad.returncode} stderr={res_bad.stderr!r}",
    )

    bad_rows = os.path.join(td, "bad-rows.json")
    with open(bad_rows, "w", encoding="utf-8") as f:
        f.write('{"not": "a list"}')
    res_bad_rows = run_bench(common + ["--out-dir", bad_out, "--effort-rows", bad_rows], home)
    record(
        "an effort rows file that is not a JSON list exits 1 with bench: message",
        res_bad_rows.returncode == 1 and res_bad_rows.stderr.startswith("bench: ")
        and "expected a JSON list" in res_bad_rows.stderr,
        f"code={res_bad_rows.returncode} stderr={res_bad_rows.stderr!r}",
    )

    sol_aa = aa_row_for(report, "gpt-5.6-sol")
    fable_aa = aa_row_for(report, "claude-fable-5-1")
    luna_aa = aa_row_for(report, "gpt-5.6-luna")
    grok_aa = aa_row_for(report, "grok-4.6")
    sol_aa_parts = [p.strip() for p in sol_aa.split("|")]
    fable_aa_parts = [p.strip() for p in fable_aa.split("|")]

    # replaces "AA matching: suffixed-only slug gpt-5-6-sol-low matches gpt-5.6-sol"
    record(
        "AA rows resolve a display name to its lane model (GPT-5.6 Sol -> gpt-5.6-sol)",
        res.returncode == 0 and "0.800" in sol_aa
        and "gpt-5.6-sol absent from Artificial Analysis" not in gaps,
        f"sol_aa={sol_aa!r} gaps={gaps}",
    )

    # replaces "AA matching: exact slug claude-fable-5-1 wins over suffixed sibling"
    record(
        "AA model view uses the lane's own effort, not another measured effort",
        len(sol_aa_parts) > 5 and sol_aa_parts[3] == "high" and sol_aa_parts[4] == "0.800"
        and "0.600" not in sol_aa
        and len(fable_aa_parts) > 5 and fable_aa_parts[3] == "xhigh" and "0.550" not in fable_aa,
        f"sol_aa={sol_aa!r} fable_aa={fable_aa!r}",
    )

    # replaces "AA matching: xhigh suffix gpt-6-astra-xhigh matches"
    record(
        "AA figures measured at xhigh reach the xhigh model, a signed component printed as signed",
        "0.900" in fable_aa and "-12.5" in fable_aa and "1.0 (n=2)" in fable_aa
        and "claude-fable-5-1 absent from Artificial Analysis" not in gaps,
        f"fable_aa={fable_aa!r}",
    )

    # replaces "AA matching: non-reasoning slug is never selected"
    record(
        "AA rows at effort none never stand for a model",
        "0.990" not in grok_aa and len(grok_aa.split("|")) > 4 and grok_aa.split("|")[3].strip() == "medium",
        f"grok_aa={grok_aa!r}",
    )

    record(
        "AA matching: model with no AA row stays absent (gemini-3.8-flash-high)",
        "gemini-3.8-flash-high absent from Artificial Analysis" in gaps,
        gaps,
    )

    # replaces "AA notes: effort note appears when matched effort differs from
    # lane effort": ticket 19 retired that note; what remains is saying a
    # model's AA figures belong to no lane
    record(
        "no 'Artificial Analysis used effort' note; a model measured only at efforts no lane runs says so",
        "Artificial Analysis used effort" not in report
        and "grok-4.6 Artificial Analysis figures are at effort medium; no lane runs that effort" in gaps
        and "gpt-5.6-sol Artificial Analysis figures are at effort" not in gaps,
        gaps,
    )

    # replaces "AA notes: effort note omitted when matched effort agrees with lane effort"
    record(
        "an AA figure at a lane's effort appears with its cost per task and mean rank",
        "0.300" in luna_aa and "| 0.05 |" in luna_aa
        and "| 0.81 | 1.5 (n=2) |" in sol_aa,
        f"luna_aa={luna_aa!r} sol_aa={sol_aa!r}",
    )

    record(
        "bench.py has no free API fetch, key loader or key-file argument",
        not hasattr(bench, "AA_URL") and not hasattr(bench, "load_key") and not hasattr(bench, "load_aa")
        and run_bench(common + ["--key-file", os.path.join(td, "aa-key")], home).returncode == 2
        and run_bench(common + ["--aa-json", rows_json], home).returncode == 2,
        str([n for n in ("AA_URL", "load_key", "load_aa") if hasattr(bench, n)]),
    )


# --- attribution: a figure reaches only the lane that ran its effort ----------
# Ticket 17. Two lanes on one model at different efforts is the case that was
# wrong: every figure of the model landed on both, so the six astra lanes read
# the same three scores and a tier was assigned on numbers none of them
# produced. Driven through collect() from a CSV fixture; no network.

ATTRIB_LANES = {
    "version": "delegate-lanes.v1",
    "lanes": {
        "astra-high@codex": {"harness": "codex", "model": "gpt-6-astra", "effort": "high",
                             "tier": 4, "meter": "codex"},
        "astra-max@codex": {"harness": "codex", "model": "gpt-6-astra", "effort": "max",
                            "tier": 4, "meter": "codex"},
        "astra-low@codex": {"harness": "codex", "model": "gpt-6-astra", "effort": "low",
                            "tier": 4, "meter": "codex"},
        "sol-high@codex": {"harness": "codex", "model": "gpt-5.6-sol", "effort": "high",
                           "tier": 4, "meter": "codex"},
    },
}

with tempfile.TemporaryDirectory() as td:
    attrib_csv = os.path.join(td, "attrib.csv")
    write_epoch_csv(attrib_csv, [
        # one model, one benchmark, three efforts, one of them unstated
        epoch_row("gpt-6-astra", "high", "DeepSWE", "0.58", "alpha", "GPT-6 Astra"),
        epoch_row("gpt-6-astra", "max", "DeepSWE", "0.59", "alpha", "GPT-6 Astra"),
        epoch_row("gpt-6-astra", "", "DeepSWE", "0.47", "alpha", "GPT-6 Astra"),
        epoch_row("gpt-6-astra", "max", "FrontierCode", "0.66", "alpha", "GPT-6 Astra"),
        epoch_row("gpt-5.6-sol", "high", "DeepSWE", "0.90", "alpha", "GPT-5.6 Sol"),
    ])
    data = bench.collect(ATTRIB_LANES, epoch_csv=attrib_csv)
    cell = data["models"]["gpt-6-astra"]["epoch"]["cells"]["DeepSWE"]
    lanes = data["lanes"]

    record(
        "every measured effort survives collection, keyed by effort, unknown included",
        set(cell) == {"high", "max", bench.UNKNOWN_EFFORT}
        and cell["high"]["performance"] == 0.58
        and cell["max"]["performance"] == 0.59
        and cell[bench.UNKNOWN_EFFORT]["performance"] == 0.47,
        str(cell),
    )

    record(
        "two lanes on one model at different efforts each get their own figure",
        lanes["astra-high@codex"]["cells"]["DeepSWE"]["performance"] == 0.58
        and lanes["astra-max@codex"]["cells"]["DeepSWE"]["performance"] == 0.59
        and "FrontierCode" not in lanes["astra-high@codex"]["cells"]
        and lanes["astra-max@codex"]["cells"]["FrontierCode"]["performance"] == 0.66,
        str({k: v["cells"] for k, v in lanes.items()}),
    )

    record(
        "a lane whose effort nobody measured gets no figure, not its model's",
        lanes["astra-low@codex"]["cells"] == {}
        and lanes["astra-low@codex"]["n"] == 0
        and lanes["astra-low@codex"]["mean"] is None
        and lanes["astra-low@codex"]["mean_s"] == "— (n=0)",
        str(lanes["astra-low@codex"]),
    )

    record(
        "an unstated effort reaches no lane and is still in the model view",
        all(bench.UNKNOWN_EFFORT not in [f.get("effort") for f in rec["cells"].values()]
            for rec in lanes.values())
        and bench.UNKNOWN_EFFORT in cell,
        str({k: v["cells"] for k, v in lanes.items()}),
    )

    # ranks compare lane against lane at its own effort. On DeepSWE:
    # sol 0.90 r1, astra-max 0.59 r2, astra-high 0.58 r3. On FrontierCode only
    # astra-max has a figure, so it ranks 1 there and means (2+1)/2 = 1.5.
    record(
        "mean rank and n count only the figures attributed to that lane",
        lanes["astra-max@codex"]["n"] == 2
        and lanes["astra-max@codex"]["mean_s"] == "1.5 (n=2)"
        and lanes["astra-high@codex"]["n"] == 1
        and lanes["astra-high@codex"]["mean_s"] == "3.0 (n=1)"
        and lanes["sol-high@codex"]["mean_s"] == "1.0 (n=1)",
        str({k: v["mean_s"] for k, v in lanes.items()}),
    )

    # the Artificial Analysis figure carries its own effort through collect(),
    # so it can be attributed the same way an Epoch figure is
    attrib_rows = [
        aa_row("GPT-6 Astra", "max", "Terminal-Bench 2.1", 0.92, 3.10),
        aa_row("GPT-6 Astra", "max", "GPQA Diamond", 0.80, 3.10),
        aa_row("GPT-6 Astra", "high", "Terminal-Bench 2.1", 0.88, 2.20),
        aa_row("GPT-5.6 Sol", None, "Terminal-Bench 2.1", 0.80, 0.81),
    ]
    aa_data = bench.collect(ATTRIB_LANES, epoch_csv=attrib_csv, effort_rows=attrib_rows)
    aa_lanes = aa_data["lanes"]

    record(
        "an Artificial Analysis figure carries its measured effort through collect",
        aa_data["models"]["gpt-6-astra"]["aa"]["effort"] == "max"
        and aa_data["models"]["gpt-5.6-sol"]["aa"] is None,
        str({m: (r["aa"] or {}).get("effort") for m, r in aa_data["models"].items()}),
    )

    record(
        "an Artificial Analysis figure reaches only the lane that ran its effort",
        aa_lanes["astra-max@codex"]["aa"]["cols"]["Terminal-Bench 2.1"] == 0.92
        and aa_lanes["astra-high@codex"]["aa"]["cols"] == {"Terminal-Bench 2.1": 0.88}
        and aa_lanes["astra-low@codex"]["aa"] is None
        and aa_lanes["sol-high@codex"]["aa"] is None,
        str({k: v["aa"] for k, v in aa_lanes.items()}),
    )

    # Terminal-Bench 2.1 over lanes: astra-max 0.92 r1, astra-high 0.88 r2;
    # GPQA Diamond: astra-max r1. So astra-max means 1.0 (n=2).
    record(
        "an AA lane figure carries that lane's cost per task and a mean rank over lanes",
        aa_lanes["astra-max@codex"]["aa"]["cost_usd"] == 3.10
        and aa_lanes["astra-high@codex"]["aa"]["cost_usd"] == 2.20
        and aa_lanes["astra-max@codex"]["aa"]["mean_s"] == "1.0 (n=2)"
        and aa_lanes["astra-high@codex"]["aa"]["mean_s"] == "2.0 (n=1)"
        and aa_data["aa_columns"] == ["Terminal-Bench 2.1", "GPQA Diamond"],
        str({k: v["aa"] for k, v in aa_lanes.items()}),
    )

    # a column no lane has a figure for is not a column
    shown = bench.collect(ATTRIB_LANES, epoch_csv=attrib_csv, effort_rows=[
        aa_row("GPT-6 Astra", "max", "Terminal-Bench 2.1", 0.92, 3.10),
        aa_row("GPT-6 Astra", "xhigh", "IFBench", 0.70, 2.90),
    ])
    record(
        "an AA column no lane has a figure for is not shown",
        shown["aa_columns"] == ["Terminal-Bench 2.1"],
        str(shown["aa_columns"]),
    )

    # agy names one model per effort; a row resolves to the member at its effort
    agy_lanes = {"version": "delegate-lanes.v1", "lanes": {
        "flash-high@agy": {"harness": "agy", "model": "gemini-3.8-flash-high", "effort": "high",
                           "tier": 2, "meter": "agy-gemini"},
        "flash-medium@agy": {"harness": "agy", "model": "gemini-3.8-flash-medium", "effort": "medium",
                             "tier": 1, "meter": "agy-gemini"},
    }}
    agy_data = bench.collect(agy_lanes, epoch_csv=attrib_csv, effort_rows=[
        aa_row("Gemini 3.8 Flash", "high", "Terminal-Bench 2.1", 0.60, 0.30),
        aa_row("Gemini 3.8 Flash", "medium", "Terminal-Bench 2.1", 0.50, 0.20),
    ])
    record(
        "agy family members each get the AA rows measured at their own effort",
        agy_data["lanes"]["flash-high@agy"]["aa"]["cols"] == {"Terminal-Bench 2.1": 0.60}
        and agy_data["lanes"]["flash-medium@agy"]["aa"]["cols"] == {"Terminal-Bench 2.1": 0.50},
        str({k: v["aa"] for k, v in agy_data["lanes"].items()}),
    )

    record(
        "the notes name the measured efforts that reach no lane",
        "gpt-6-astra DeepSWE also measured at an unstated effort (0.47); "
        "no lane runs that effort" in data["notes"],
        str(data["notes"]),
    )

record(
    "ultra never stands for a model, even when a lane carries it",
    bench.lane_effort_of({"lanes": ["a", "b"], "efforts": ["ultra", "high"]}) == "high"
    and bench.lane_effort_of({"lanes": ["a"], "efforts": ["ultra"]}) == "ultra"
    and bench.choose_effort({"ultra": 1, "high": 1}, ["ultra", "high"]) == "high",
    str(bench.EFFORT_PREFERENCE),
)

record(
    "LANE_EFFORT_ORDER covers every effort a lane can carry",
    set(bench.LANE_EFFORT_ORDER) == set(catalog.EFFORTS),
    f"order={bench.LANE_EFFORT_ORDER} efforts={catalog.EFFORTS}",
)

sys.exit(1 if fails else 0)
