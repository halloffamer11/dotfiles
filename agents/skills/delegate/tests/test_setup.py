#!/usr/bin/env python3
"""Black-box tests for setup.py. Run: python3 tests/test_setup.py"""
import copy
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DELEGATE_DIR = os.path.abspath(os.path.join(HERE, "..", "scripts"))
SETUP_PY = os.path.join(DELEGATE_DIR, "setup.py")
SAMPLES_DIR = os.path.abspath(os.path.join(HERE, "..", "assets", "samples"))

sys.path.insert(0, DELEGATE_DIR)
import catalog

fails = 0
lanes_sample = catalog.load_json(os.path.join(SAMPLES_DIR, "lanes.json"))
routing_sample = catalog.load_json(os.path.join(SAMPLES_DIR, "routing.json"))


def record(name, ok, detail=""):
    global fails
    if ok:
        print(f"PASS {name}")
    else:
        fails += 1
        print(f"FAIL {name}: {detail}")


def discovered(keys):
    return {
        "version": "delegate-discover.v1",
        "discovered": [
            {
                "key": key,
                "binary": key,
                "version": f"{key} test version",
                "path": f"/test/{key}",
                "authenticated": True,
                "models": {"status": "reported", "values": []},
            }
            for key in keys
        ],
        "missing": [],
    }


def write_discover(path, keys):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(discovered(keys), f)


def run_setup(config_dir, discover_path, answers, *extra):
    return subprocess.run(
        [
            sys.executable,
            SETUP_PY,
            "--config-dir",
            config_dir,
            "--discover-json",
            discover_path,
            # model discovery shells out to the real harness CLIs; these cases
            # are about the prompts, and the facts case below drives fixtures
            "--no-discover",
            *extra,
        ],
        input=answers,
        capture_output=True,
        text=True,
        cwd=DELEGATE_DIR,
    )


def default_answers(lane_count):
    # one blank per lane (tier), plus one for the "keep routing as shown?" prompt
    return "\n" * (lane_count + 1) + "y\n"


def load_written(config_dir):
    lanes_path = os.path.join(config_dir, "lanes.json")
    routing_path = os.path.join(config_dir, "routing.json")
    return catalog.load_json(lanes_path), catalog.load_json(routing_path)


def sample_proposal(harnesses):
    doc = copy.deepcopy(lanes_sample)
    doc["lanes"] = {
        name: lane for name, lane in doc["lanes"].items()
        if lane["harness"] in harnesses
    }
    used = {lane["meter"] for lane in doc["lanes"].values()}
    doc["meters"] = {
        name: meter for name, meter in doc["meters"].items() if name in used
    }
    return doc


def case_all_harnesses_write_canonical_samples():
    with tempfile.TemporaryDirectory() as td:
        cfg = os.path.join(td, "config")
        discover_path = os.path.join(td, "discover.json")
        write_discover(discover_path, catalog.HARNESSES)
        result = run_setup(cfg, discover_path, default_answers(len(lanes_sample["lanes"])), "--no-bench")
        lanes, routing = load_written(cfg)
        canonical = (
            open(os.path.join(cfg, "lanes.json"), "rb").read()
            == catalog.format_json(lanes).encode("utf-8")
            and open(os.path.join(cfg, "routing.json"), "rb").read()
            == catalog.format_json(routing).encode("utf-8")
        )
        expected = sample_proposal(catalog.HARNESSES)
        all_sample_values = all(
            lanes["lanes"][name]["tier"] == sample["tier"]
            for name, sample in lanes_sample["lanes"].items()
        )
        catalog.check_file(os.path.join(cfg, "lanes.json"))
        catalog.check_file(os.path.join(cfg, "routing.json"))
        return (
            result.returncode == 0
            and lanes == expected
            and routing == routing_sample
            and canonical
            and all_sample_values,
            f"code={result.returncode}, lanes={lanes == expected}, routing={routing == routing_sample}, canonical={canonical}, values={all_sample_values}, stderr={result.stderr!r}",
        )


def case_subset_filters_lanes_and_meters():
    with tempfile.TemporaryDirectory() as td:
        cfg = os.path.join(td, "config")
        discover_path = os.path.join(td, "discover.json")
        write_discover(discover_path, ("agy", "grok"))
        result = run_setup(cfg, discover_path, default_answers(2), "--no-bench")
        lanes, _routing = load_written(cfg)
        wanted_lanes = {"flash-high@agy", "grok46-high@grok"}
        wanted_meters = {"agy-gemini", "grok"}
        return (
            result.returncode == 0
            and set(lanes["lanes"]) == wanted_lanes
            and set(lanes["meters"]) == wanted_meters
            and "terra-high@codex" not in lanes["lanes"]
            and "sol-high@codex" not in lanes["lanes"],
            f"code={result.returncode}, lanes={lanes['lanes'].keys()}",
        )


def case_existing_values_are_prompt_defaults():
    with tempfile.TemporaryDirectory() as td:
        cfg = os.path.join(td, "config")
        os.makedirs(cfg)
        existing = copy.deepcopy(lanes_sample)
        existing["lanes"]["terra-high@codex"]["tier"] = 3
        catalog.write_json(os.path.join(cfg, "lanes.json"), existing)
        catalog.write_json(os.path.join(cfg, "routing.json"), routing_sample)
        discover_path = os.path.join(td, "discover.json")
        write_discover(discover_path, catalog.HARNESSES)
        result = run_setup(cfg, discover_path, default_answers(6), "--no-bench")
        lanes, _routing = load_written(cfg)
        return (
            result.returncode == 0
            and "tier [3]:" in result.stdout
            and lanes["lanes"]["terra-high@codex"]["tier"] == 3,
            f"code={result.returncode}, stdout={result.stdout!r}",
        )


def case_one_lane_values_change_only_that_lane():
    with tempfile.TemporaryDirectory() as td:
        cfg = os.path.join(td, "config")
        discover_path = os.path.join(td, "discover.json")
        write_discover(discover_path, catalog.HARNESSES)
        answers = "4\n" + "\n" * 6 + "y\n"
        result = run_setup(cfg, discover_path, answers, "--no-bench")
        lanes, _routing = load_written(cfg)
        changed = sample_proposal(catalog.HARNESSES)
        changed["lanes"]["fable-xhigh@claude"]["tier"] = 4
        return lanes == changed and result.returncode == 0, f"code={result.returncode}, lanes={lanes == changed}"


def case_bench_report_is_display_only():
    with tempfile.TemporaryDirectory() as td:
        cfg = os.path.join(td, "config")
        discover_path = os.path.join(td, "discover.json")
        report_path = os.path.join(td, "bench.md")
        write_discover(discover_path, catalog.HARNESSES)
        report_text = "terra-high@codex tier 1\nfixture benchmark report\n"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_text)
        result = run_setup(
            cfg,
            discover_path,
            default_answers(6),
            "--bench-report",
            report_path,
        )
        first_prompt = result.stdout.find("tier [")
        return (
            result.returncode == 0
            and result.stdout.find(report_text) != -1
            and result.stdout.find(report_text) < first_prompt
            and "tier [2]:" in result.stdout,
            f"code={result.returncode}, stdout={result.stdout!r}",
        )


def case_decline_writes_nothing():
    with tempfile.TemporaryDirectory() as td:
        cfg = os.path.join(td, "config")
        discover_path = os.path.join(td, "discover.json")
        write_discover(discover_path, catalog.HARNESSES)
        answers = "\n" * 13 + "n\n"
        result = run_setup(cfg, discover_path, answers, "--no-bench")
        return (
            result.returncode == 0
            and not os.path.exists(os.path.join(cfg, "lanes.json"))
            and not os.path.exists(os.path.join(cfg, "routing.json"))
            and result.stdout.rstrip().endswith("nothing written"),
            f"code={result.returncode}, stdout={result.stdout!r}",
        )


def case_out_of_range_retries_then_writes_value():
    with tempfile.TemporaryDirectory() as td:
        cfg = os.path.join(td, "config")
        discover_path = os.path.join(td, "discover.json")
        write_discover(discover_path, catalog.HARNESSES)
        answers = "9\n3\n" + "\n" * 6 + "y\n"
        result = run_setup(cfg, discover_path, answers, "--no-bench")
        lanes, _routing = load_written(cfg)
        return (
            result.returncode == 0
            and lanes["lanes"]["fable-xhigh@claude"]["tier"] == 3
            and result.stdout.count("tier must be an integer from 1 to 4") == 1,
            f"code={result.returncode}, stdout={result.stdout!r}",
        )


def case_eof_aborts_without_writing():
    with tempfile.TemporaryDirectory() as td:
        cfg = os.path.join(td, "config")
        discover_path = os.path.join(td, "discover.json")
        write_discover(discover_path, catalog.HARNESSES)
        result = run_setup(cfg, discover_path, "", "--no-bench")
        return (
            result.returncode == 130
            and not os.path.exists(os.path.join(cfg, "lanes.json"))
            and not os.path.exists(os.path.join(cfg, "routing.json")),
            f"code={result.returncode}, stdout={result.stdout!r}",
        )


def case_routing_edits_keep_other_classes():
    with tempfile.TemporaryDirectory() as td:
        cfg = os.path.join(td, "config")
        discover_path = os.path.join(td, "discover.json")
        write_discover(discover_path, catalog.HARNESSES)
        answers = "\n" * 6 + "n\n" + "\n" * 6 + "3\n3\n" + "\n" * 2 + "0.3\n\n" + "y\n"
        result = run_setup(cfg, discover_path, answers, "--no-bench")
        _lanes, routing = load_written(cfg)
        unchanged = all(
            routing["classes"][name] == routing_sample["classes"][name]
            for name in catalog.CLASSES
            if name != "review"
        )
        return (
            result.returncode == 0
            and routing["classes"]["review"] == {"floor": 3, "ceiling": 3}
            and routing["margin"] == 0.3
            and unchanged,
            f"code={result.returncode}, routing={routing}",
        )


def case_effort_rows_says_the_prompt_interface_has_no_prescreen():
    """--effort-rows is TUI-only. A pipe or --plain reads it and does nothing
    with it, and the instruction a human is handed names the flag, so silence
    would read as "the pre-screen ran and proposed nothing off"."""
    with tempfile.TemporaryDirectory() as td:
        cfg = os.path.join(td, "config")
        discover_path = os.path.join(td, "discover.json")
        write_discover(discover_path, catalog.HARNESSES)
        rows_path = os.path.join(td, "rows.json")
        with open(rows_path, "w", encoding="utf-8") as f:
            json.dump([{"source": "t", "model": "gpt-5.6-luna", "effort": "low",
                        "benchmark": "b", "score": 4.0, "cost_usd": 1.7,
                        "uncertain": False}], f)
        result = run_setup(cfg, discover_path, default_answers(len(lanes_sample["lanes"])),
                           "--no-bench", "--effort-rows", rows_path)
        said = "--effort-rows" in result.stdout and "pre-screen" in result.stdout
        wrote = os.path.isfile(os.path.join(cfg, "lanes.json"))
        lanes, _routing = load_written(cfg)
        untouched = all("enabled" not in lane for lane in lanes["lanes"].values())
        return (said and wrote and untouched,
                f"said={said} wrote={wrote} untouched={untouched} stdout={result.stdout[:300]!r}")


def case_effort_rows_from_several_files_combine():
    """--effort-rows may be repeated, so two sources share one benchmark page.
    Every file's rows arrive in order, and a bad file is named, not skipped."""
    import setup
    row = {"source": "t", "model": "gpt-5.6-luna", "effort": "low", "benchmark": "b",
           "score": 4.0, "cost_usd": 1.7, "uncertain": False}
    with tempfile.TemporaryDirectory() as td:
        paths = []
        for i, source in enumerate(("aa", "tbench")):
            paths.append(os.path.join(td, f"rows{i}.json"))
            with open(paths[-1], "w", encoding="utf-8") as f:
                json.dump([dict(row, source=source)], f)
        bad = os.path.join(td, "bad.json")
        with open(bad, "w", encoding="utf-8") as f:
            json.dump({"not": "a list"}, f)
        rows, message = setup.load_effort_rows(paths)
        one, _ = setup.load_effort_rows(paths[0])
        refused, why = setup.load_effort_rows([paths[0], bad])
    ok = ([r["source"] for r in rows] == ["aa", "tbench"] and message == ""
          and [r["source"] for r in one] == ["aa"]
          and refused is None and bad in why and "expected a JSON list" in why)
    return ok, f"rows={rows} message={message!r} refused={refused} why={why!r}"


def case_plain_prints_the_start_facts():
    """--plain prints what the TUI's start page shows, from the same function:
    both output paths, the benchmark page line and the discovery notices, before
    the first prompt, and no definition of a term (ticket 25)."""
    import setup_tui
    fixture_dir = os.path.join(HERE, "fixtures", "discover")
    with tempfile.TemporaryDirectory() as td:
        cfg = os.path.join(td, "config")
        discover_path = os.path.join(td, "discover.json")
        write_discover(discover_path, catalog.HARNESSES)
        result = subprocess.run(
            [sys.executable, SETUP_PY, "--config-dir", cfg, "--discover-json", discover_path,
             "--fixture-dir", fixture_dir, "--no-bench", "--plain"],
            input=default_answers(len(lanes_sample["lanes"])), capture_output=True, text=True,
            cwd=DELEGATE_DIR)
        import discover
        facts = setup_tui.start_facts(os.path.join(cfg, "lanes.json"), os.path.join(cfg, "routing.json"),
                                      None, discover.discover(sample_proposal(catalog.HARNESSES),
                                                              fixture_dir=fixture_dir), width=10_000)
        first_prompt = result.stdout.find("tier [")
        positions = [result.stdout.find(line) for line in facts]
        ok = (result.returncode == 0 and len(facts) >= 4
              and all(0 <= p < first_prompt for p in positions)
              and "Benchmark page: (not written)" in result.stdout
              and any(line.startswith(("Model discovery", "Models with no lane", "Lanes with retired"))
                      for line in facts)
              and "Tier is capability" not in result.stdout)
        return ok, f"facts={facts} positions={positions} stdout={result.stdout[:500]!r}"


for name, case in (
    ("plain prints the start facts", case_plain_prints_the_start_facts),
    ("effort rows from several files combine", case_effort_rows_from_several_files_combine),
    ("all harnesses write canonical samples", case_all_harnesses_write_canonical_samples),
    ("subset filters lanes and meters", case_subset_filters_lanes_and_meters),
    ("existing values are prompt defaults", case_existing_values_are_prompt_defaults),
    ("one lane values change only that lane", case_one_lane_values_change_only_that_lane),
    ("bench report is display only", case_bench_report_is_display_only),
    ("decline writes nothing", case_decline_writes_nothing),
    ("out of range retries then writes value", case_out_of_range_retries_then_writes_value),
    ("EOF aborts without writing", case_eof_aborts_without_writing),
    ("routing edits keep other classes", case_routing_edits_keep_other_classes),
    ("effort rows say the prompt interface has no pre-screen",
     case_effort_rows_says_the_prompt_interface_has_no_prescreen),
):
    try:
        ok, detail = case()
    except Exception as e:
        ok, detail = False, repr(e)
    record(name, ok, detail)

sys.exit(1 if fails else 0)
