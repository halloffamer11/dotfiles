#!/usr/bin/env python3
"""Black-box tests for setup.py. Run: python3 tests/test_setup.py"""
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))

# Run from a fresh directory with no Git root above it, so that
# `catalog.find_git_root()` never finds the invoking checkout's own
# `.delegate/routing.json`. Every path this file needs comes from HERE.
_ISOLATED_CWD = tempfile.TemporaryDirectory(prefix="delegate-test-")
os.chdir(_ISOLATED_CWD.name)
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
        answers = "\n" * 6 + "n\n" + "\n" * 6 + "3\n3\n" + "\n" * 2 + "0.3\n\n\n" + "y\n"
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
    both output paths, the benchmark page line, where the benchmark rows came
    from, what the refresh proposes and the discovery notices, before the first
    prompt, and no definition of a term (tickets 25 and 33)."""
    import discover
    import setup
    import setup_tui
    fixture_dir = os.path.join(HERE, "fixtures", "discover")
    with tempfile.TemporaryDirectory() as td:
        cfg = os.path.join(td, "config")
        discover_path = os.path.join(td, "discover.json")
        saved = discover.discover(sample_proposal(catalog.HARNESSES), fixture_dir=fixture_dir)
        catalog.write_json(discover_path, saved)
        # the same refresh the wizard runs, so the facts are the same facts
        refreshed, refresh = discover.refresh_catalog(
            sample_proposal(catalog.HARNESSES), saved
        )
        _paths, rows_note = setup.refresh_effort_rows(None, fixture_dir=fixture_dir)
        result = subprocess.run(
            [sys.executable, SETUP_PY, "--config-dir", cfg, "--discover-json", discover_path,
             "--fixture-dir", fixture_dir, "--no-bench", "--plain"],
            input=default_answers(len(refreshed["lanes"])), capture_output=True, text=True,
            cwd=DELEGATE_DIR)
        facts = setup_tui.start_facts(os.path.join(cfg, "lanes.json"), os.path.join(cfg, "routing.json"),
                                      None, discover.map_lanes(saved, refreshed), width=10_000,
                                      refresh=refresh, rows_note=rows_note)
        first_prompt = result.stdout.find("tier [")
        positions = [result.stdout.find(line) for line in facts]
        ok = (result.returncode == 0 and len(facts) >= 4
              and all(0 <= p < first_prompt for p in positions)
              and "Benchmark page: (not written)" in result.stdout
              and any(line.startswith(("Model discovery", "Models with no lane", "Lanes with retired"))
                      for line in facts)
              and "Tier is capability" not in result.stdout)
        return ok, f"facts={facts} positions={positions} stdout={result.stdout[:500]!r}"


def case_tiers_from_applies_the_page_lines():
    """--tiers-from applies the benchmark page's lines with the review page's
    parser: a tier line becomes the lane's tier, an off line writes it off, a
    carried lane no line names is written off, the lines' order inside a tier is
    the order written, and the summary line is printed before the first prompt
    (tickets 27 and 28)."""
    with tempfile.TemporaryDirectory() as td:
        cfg = os.path.join(td, "config")
        discover_path = os.path.join(td, "discover.json")
        write_discover(discover_path, catalog.HARNESSES)
        lines = os.path.join(td, "tiers.txt")
        with open(lines, "w", encoding="utf-8") as f:
            f.write("grok46-high@grok 4\nterra-high@codex 4\n\nluna-low@codex off\nnobody@codex 2\n")
        result = run_setup(cfg, discover_path, default_answers(len(lanes_sample["lanes"])),
                           "--no-bench", "--plain", "--tiers-from", lines)
        lanes, _routing = load_written(cfg)
        summary = "Lines: 2 took a tier; 1 went off; 3 not named, so off; unknown, ignored: nobody@codex."
        ok = (result.returncode == 0
              and 0 <= result.stdout.find(summary) < result.stdout.find("tier [")
              and lanes["lanes"]["terra-high@codex"]["tier"] == 4
              and "enabled" not in lanes["lanes"]["terra-high@codex"]
              and lanes["lanes"]["grok46-high@grok"]["order"] == 1
              and lanes["lanes"]["terra-high@codex"]["order"] == 2
              and "terra-high@codex: tier 4, order 2" in result.stdout
              and lanes["lanes"]["luna-low@codex"]["enabled"] is False
              and all(lanes["lanes"][name]["enabled"] is False and "order" not in lanes["lanes"][name]
                      for name in ("sol-high@codex", "fable-xhigh@claude", "flash-high@agy", "luna-low@codex"))
              and lanes["lanes"]["sol-high@codex"]["tier"] == lanes_sample["lanes"]["sol-high@codex"]["tier"])
        return ok, f"code={result.returncode} stdout={result.stdout[:600]!r} stderr={result.stderr!r}"


def case_tiers_from_unreadable_file_writes_nothing():
    with tempfile.TemporaryDirectory() as td:
        cfg = os.path.join(td, "config")
        discover_path = os.path.join(td, "discover.json")
        write_discover(discover_path, catalog.HARNESSES)
        result = run_setup(cfg, discover_path, default_answers(len(lanes_sample["lanes"])),
                           "--no-bench", "--plain", "--tiers-from", os.path.join(td, "absent.txt"))
        ok = (result.returncode == 1 and "tiers-from" in result.stderr
              and not os.path.exists(os.path.join(cfg, "lanes.json")))
        return ok, f"code={result.returncode} stderr={result.stderr!r}"


def case_no_discover_skips_all_acquisition():
    """--no-discover must skip discover.discover and never call node."""
    import setup
    import discover as discover_mod
    hits = {"discover": 0, "node": 0}
    orig_discover = discover_mod.discover
    orig_run = getattr(setup, "subprocess", None)

    def wrapped_discover(*a, **k):
        hits["discover"] += 1
        return orig_discover(*a, **k)

    class Args:
        no_discover = True
        discover_json = None
        fixture_dir = None
        ads_dir = None

    discover_mod.discover = wrapped_discover
    try:
        discovered, data = setup.acquire_discovery({"lanes": {}}, Args())
    finally:
        discover_mod.discover = orig_discover
    return (
        data == "skipped (--no-discover)"
        and hits["discover"] == 0
        and discovered == set(catalog.HARNESSES)
        and orig_run is None
    ), f"data={data!r} hits={hits} discovered={discovered} subprocess={orig_run}"


def case_one_discovery_path_is_discover():
    """The default setup path acquires through discover.discover once, never node."""
    import setup
    import discover as discover_mod
    fixtures = os.path.join(HERE, "fixtures", "discover")
    hits = {"discover": 0, "node": 0}
    orig_discover = discover_mod.discover

    def wrapped_discover(*a, **k):
        hits["discover"] += 1
        return orig_discover(*a, **k)

    class Args:
        no_discover = False
        discover_json = None
        fixture_dir = fixtures
        ads_dir = None

    discover_mod.discover = wrapped_discover
    try:
        discovered, data = setup.acquire_discovery(sample_proposal(catalog.HARNESSES), Args())
    finally:
        discover_mod.discover = orig_discover
    ok = (
        hits["discover"] == 1
        and isinstance(data, dict)
        and "harnesses" in data
        and all(h in data["harnesses"] for h in ("codex", "agy", "grok", "claude"))
        and "discover.mjs" not in str(data)
    )
    return ok, f"hits={hits} discovered={discovered} harnesses={getattr(data, 'get', lambda *_: None)('harnesses')}"


def case_harness_error_keeps_existing_lanes():
    """A single harness failure is a notice; setup continues and existing lanes stay."""
    fixture_dir = os.path.join(HERE, "fixtures", "discover")
    with tempfile.TemporaryDirectory() as td:
        cfg = os.path.join(td, "config")
        os.makedirs(cfg)
        existing = copy.deepcopy(lanes_sample)
        catalog.write_json(os.path.join(cfg, "lanes.json"), existing)
        catalog.write_json(os.path.join(cfg, "routing.json"), routing_sample)
        broken = os.path.join(td, "fixtures")
        os.makedirs(broken)
        for name in os.listdir(fixture_dir):
            src = os.path.join(fixture_dir, name)
            dst = os.path.join(broken, name)
            if name == "codex-debug-models.json":
                with open(dst, "w", encoding="utf-8") as f:
                    f.write("{not json")
            else:
                with open(src, "r", encoding="utf-8") as f:
                    text = f.read()
                with open(dst, "w", encoding="utf-8") as f:
                    f.write(text)
        import discover
        saved = discover.discover(existing, fixture_dir=broken)
        refreshed, _refresh = discover.refresh_catalog(existing, saved)
        result = subprocess.run(
            [sys.executable, SETUP_PY, "--config-dir", cfg, "--fixture-dir", broken,
             "--no-bench", "--plain"],
            input=default_answers(len(refreshed["lanes"])),
            capture_output=True, text=True, cwd=DELEGATE_DIR,
        )
        lanes, _routing = load_written(cfg)
        notice = "discovery error" in result.stdout or "Harness codex: error" in result.stdout
        ok = (
            result.returncode == 0
            # the failing harness keeps every lane it has; the refresh may add
            # lanes on the harnesses that answered, never take one away here
            and set(lanes_sample["lanes"]) <= set(lanes["lanes"])
            and {name for name in lanes["lanes"] if name.endswith("@codex")}
            == {name for name in lanes_sample["lanes"] if name.endswith("@codex")}
            and notice
        )
        return ok, (
            f"code={result.returncode} lanes={set(lanes['lanes'])} "
            f"notice={notice} stdout={result.stdout[:500]!r} stderr={result.stderr!r}"
        )


def case_plain_collects_bench_in_process():
    """Plain setup renders collect() in process; it does not spawn bench.py."""
    import setup
    fixture = os.path.join(HERE, "fixture", "bench-epoch.csv")
    spawned = []

    class Args:
        no_bench = False
        bench_report = None
        epoch_csv = fixture
        effort_rows = None

    buf = []
    orig_print = setup.print if hasattr(setup, "print") else print

    def capture(*a, **k):
        buf.append(" ".join(str(x) for x in a))

    import builtins
    real_print = builtins.print
    builtins.print = capture
    try:
        setup.show_bench(Args(), sample_proposal(catalog.HARNESSES), routing_sample)
    finally:
        builtins.print = real_print
    text = "\n".join(buf)
    import inspect
    source = inspect.getsource(setup.show_bench)
    ok = (
        "Lane benchmark ranking" in text
        and "bench.py" not in source
        and "subprocess" not in source
        and spawned == []
    )
    return ok, f"text={text[:200]!r} source_has_bench={'bench.py' in source}"


def case_focused_screen_rejects_plain():
    with tempfile.TemporaryDirectory() as td:
        cfg = os.path.join(td, "config")
        os.makedirs(cfg)
        catalog.write_json(os.path.join(cfg, "lanes.json"), copy.deepcopy(lanes_sample))
        catalog.write_json(os.path.join(cfg, "routing.json"), copy.deepcopy(routing_sample))
        discover_path = os.path.join(td, "discover.json")
        write_discover(discover_path, catalog.HARNESSES)
        result = run_setup(cfg, discover_path, "", "--no-bench", "--plain", "--screen", "carry")
        return (
            result.returncode == 1
            and "catalog.py" in result.stderr
            and "set" in result.stderr
            and not (result.stdout or "").strip().endswith("wrote"),
            f"code={result.returncode} stderr={result.stderr!r}",
        )


def case_start_screen_keeps_plain_wizard():
    with tempfile.TemporaryDirectory() as td:
        cfg = os.path.join(td, "config")
        discover_path = os.path.join(td, "discover.json")
        write_discover(discover_path, catalog.HARNESSES)
        result = run_setup(
            cfg, discover_path, default_answers(len(lanes_sample["lanes"])),
            "--no-bench", "--screen", "start",
        )
        wrote = os.path.isfile(os.path.join(cfg, "lanes.json"))
        return (
            result.returncode == 0 and wrote,
            f"code={result.returncode} stdout={result.stdout[-200:]!r}",
        )


def case_saved_discovery_never_probes():
    import setup
    from unittest.mock import patch
    from types import SimpleNamespace
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "discovery.json")
        for document in (
            {"discovered": [{"key": "codex"}], "missing": [{"key": "agy"}]},
            {"harnesses": {"codex": {"status": "ok"}}, "models": [], "unmapped": [], "retired": []},
        ):
            catalog.write_json(path, document)
            args = SimpleNamespace(discover_json=path, no_discover=False, fixture_dir=None)
            with patch.object(setup.discover, "discover", side_effect=AssertionError("unexpected live probe")) as probe:
                found, result = setup.acquire_discovery(lanes_sample, args)
            if found != {"codex"} or probe.called or result["harnesses"]["codex"]["status"] != "ok":
                return False, repr((found, result))
    return True, "both saved formats supplied facts without a live acquisition"


# --- ticket 33: the wizard refreshes to the current generation --------------

REFRESH_DIR = os.path.join(HERE, "fixtures", "refresh-2026-09-22")
REPO_AGENTS = os.path.abspath(os.path.join(HERE, "..", "..", "..", "agents"))


def refresh_fixture():
    """(the frozen catalog, the refreshed catalog, the plan) on the 2026-09-22
    fixtures. The catalog is the frozen copy beside them, never the live one,
    which the refresh's own first run changes."""
    import discover
    import setup
    frozen = catalog.load_json(os.path.join(REFRESH_DIR, "lanes.json"))
    rows = catalog.load_json(os.path.join(REFRESH_DIR, "aa-accepted.json"))
    saved = discover.discover(frozen, fixture_dir=REFRESH_DIR)
    refreshed, plan = discover.refresh_catalog(
        frozen, saved, published_models=setup.published_model_names(rows)
    )
    return frozen, refreshed, plan


def write_rows(path, source, model):
    with open(path, "w", encoding="utf-8") as f:
        json.dump([{"source": source, "model": model, "benchmark": "b", "score": 1}], f)
    return path


def case_a_fresh_fetch_is_not_fetched_again():
    """A fetch from the last 24 hours stands in for a new one, and the rows it
    holds replace the repo's Artificial Analysis rows (ticket 33)."""
    import setup
    with tempfile.TemporaryDirectory() as td:
        cache = os.path.join(td, "aa")
        os.makedirs(cache)
        accepted = write_rows(os.path.join(cache, "accepted.json"), "aa", "Grok 4.7")
        repo_aa = write_rows(os.path.join(td, "repo-aa.json"), "aa", "Grok 4.6")
        tbench = write_rows(os.path.join(td, "repo-tbench.json"), "tbench", "Grok 4.6")
        calls = []
        paths, note = setup.refresh_effort_rows(
            [repo_aa, tbench], cache_dir=cache, fetch=lambda *a, **k: calls.append(a)
        )
        ok = paths == [accepted, tbench] and calls == [] and "0h ago" in note
        return ok, f"paths={paths} calls={calls} note={note!r}"


def case_a_stale_fetch_is_fetched_again():
    """A cache older than 24 hours is fetched again, into the same directory."""
    import setup
    with tempfile.TemporaryDirectory() as td:
        cache = os.path.join(td, "aa")
        os.makedirs(cache)
        accepted = write_rows(os.path.join(cache, "accepted.json"), "aa", "Grok 4.6")
        old = time.time() - 48 * 60 * 60
        os.utime(accepted, (old, old))
        repo_aa = write_rows(os.path.join(td, "repo-aa.json"), "aa", "Grok 4.6")
        calls = []

        def fetch(out_dir, **kwargs):
            calls.append(out_dir)
            write_rows(os.path.join(out_dir, "accepted.json"), "aa", "Grok 4.7")

        paths, note = setup.refresh_effort_rows([repo_aa], cache_dir=cache, fetch=fetch)
        rows, _message = setup.load_effort_rows(paths)
        ok = (calls == [cache] and paths == [accepted]
              and rows == [{"source": "aa", "model": "Grok 4.7", "benchmark": "b", "score": 1}]
              and "fetched just now" in note)
        return ok, f"paths={paths} calls={calls} note={note!r}"


def case_a_failed_fetch_keeps_the_repo_rows():
    """A leaderboard that is down never stops a catalog edit: the repo's rows
    stand, and the start page carries the reason."""
    import setup
    with tempfile.TemporaryDirectory() as td:
        cache = os.path.join(td, "aa")
        repo_aa = write_rows(os.path.join(td, "repo-aa.json"), "aa", "Grok 4.6")

        def fetch(out_dir, **kwargs):
            raise RuntimeError("the page could not be read")

        paths, note = setup.refresh_effort_rows([repo_aa], cache_dir=cache, fetch=fetch)
        ok = (paths == [repo_aa] and "repo rows" in note
              and "the page could not be read" in note)
        return ok, f"paths={paths} note={note!r}"


def case_native_agent_files_follow_the_claude_lanes():
    """The save writes an agent file for each new claude lane, in the form the
    files beside it take, and removes each superseded one (ticket 33)."""
    import setup
    _frozen, refreshed, plan = refresh_fixture()
    shape_path = os.path.join(REPO_AGENTS, "lane-opus-high.md")
    with open(shape_path, encoding="utf-8") as f:
        shape = f.read()
    with tempfile.TemporaryDirectory() as td:
        agents = os.path.join(td, "agents")
        os.makedirs(agents)
        for effort in ("low", "medium", "high", "xhigh", "max"):
            with open(os.path.join(agents, f"lane-opus-{effort}.md"), "w") as f:
                f.write("superseded\n")
        lines = setup.save_native_agents(plan, refreshed, agents)
        written = sorted(os.listdir(agents))
        with open(os.path.join(agents, "lane-opus55-high.md"), encoding="utf-8") as f:
            text = f.read()
        expected = (shape.replace("lane-opus-high", "lane-opus55-high")
                         .replace("opus-high@claude", "opus55-high@claude")
                         .replace("model: claude-opus-5\n", "model: claude-opus-5-5\n"))
        ok = (written == sorted(f"lane-opus55-{e}.md"
                                for e in ("low", "medium", "high", "xhigh", "max"))
              and text == expected
              and os.path.realpath(setup.NATIVE_AGENTS_DIR) == os.path.realpath(REPO_AGENTS)
              and len(lines) == 10)
        return ok, f"written={written} lines={lines} text={text!r}"


def case_a_catalog_elsewhere_gets_no_agent_file():
    """The agent files belong to this checkout's catalog, so a catalog somewhere
    else gets none, and the run says so rather than writing into the repo."""
    import setup
    _frozen, refreshed, plan = refresh_fixture()
    with tempfile.TemporaryDirectory() as td:
        lines = setup.save_native_agents(plan, refreshed, setup.native_agents_dir(td))
        ok = (setup.native_agents_dir(td) is None
              and setup.native_agents_dir(
                  os.path.join(os.path.dirname(setup.NATIVE_AGENTS_DIR),
                               "stow", "delegate", ".config", "delegate"))
              == setup.NATIVE_AGENTS_DIR
              and len(lines) == 1 and "agent file" in lines[0])
        return ok, f"lines={lines}"


def case_the_refreshed_rows_reach_the_new_lanes():
    """The rows the refresh brings in are attributed to the lanes it adds:
    Claude Opus 5.5 to the opus55 lanes and Grok 4.7 high to grok47-high@grok,
    each at its own effort. A lane no source scored keeps no figures, which is
    what the carry page reports as no rows (ticket 33)."""
    import bench
    _frozen, refreshed, _plan = refresh_fixture()
    rows = catalog.load_json(os.path.join(REFRESH_DIR, "aa-accepted.json"))
    data = bench.collect(refreshed, effort_rows=rows)
    lanes = data["lanes"]

    def columns(name):
        return sorted((lanes[name].get("aa") or {}).get("cols", {}))

    ok = (columns("opus55-high@claude") and columns("opus55-max@claude")
          and columns("grok47-high@grok")
          and lanes["opus55-high@claude"]["aa"]["effort"] == "high"
          and lanes["grok47-high@grok"]["aa"]["effort"] == "high"
          # no source scores these yet, and none of the predecessor's rows leak
          and not columns("sol6-high@codex") and not columns("pro31-high@agy")
          and not columns("grok47fast-high@grok"))
    return ok, f"opus55={columns('opus55-high@claude')} grok47={columns('grok47-high@grok')}"


def case_no_discover_fetches_no_rows():
    """--no-discover skips every live acquisition, the benchmark-row fetch
    included: a run with it says nothing about where rows came from, because it
    went nowhere for them (ticket 33)."""
    with tempfile.TemporaryDirectory() as td:
        cfg = os.path.join(td, "config")
        discover_path = os.path.join(td, "discover.json")
        write_discover(discover_path, catalog.HARNESSES)
        result = run_setup(cfg, discover_path,
                           default_answers(len(lanes_sample["lanes"])), "--no-bench")
        ok = (result.returncode == 0
              and "Benchmark rows:" not in result.stdout
              and "Catalog refresh" not in result.stdout)
        return ok, f"code={result.returncode} stdout={result.stdout[:300]!r}"


def case_plain_prints_the_refresh_change_lines():
    """--plain states the refresh, one line per model, and the catalog it then
    writes passes catalog.py check (ticket 33)."""
    import setup_tui
    _frozen, refreshed, plan = refresh_fixture()
    with tempfile.TemporaryDirectory() as td:
        cfg = os.path.join(td, "config")
        os.makedirs(cfg)
        shutil.copy(os.path.join(REFRESH_DIR, "lanes.json"), os.path.join(cfg, "lanes.json"))
        catalog.write_json(os.path.join(cfg, "routing.json"), routing_sample)
        result = subprocess.run(
            [sys.executable, SETUP_PY, "--config-dir", cfg, "--fixture-dir", REFRESH_DIR,
             "--effort-rows", os.path.join(REFRESH_DIR, "aa-accepted.json"),
             "--no-bench", "--plain"],
            input=default_answers(len(refreshed["lanes"])),
            capture_output=True, text=True, cwd=DELEGATE_DIR,
        )
        expected = setup_tui.refresh_lines(plan, 10_000)
        check = subprocess.run(
            [sys.executable, os.path.join(DELEGATE_DIR, "catalog.py"), "check",
             os.path.join(cfg, "lanes.json")],
            capture_output=True, text=True,
        )
        written = catalog.load_json(os.path.join(cfg, "lanes.json"))
        ok = (result.returncode == 0
              and all(line in result.stdout for line in expected)
              and "gpt-5.6-sol → gpt-6-sol: sol6-*@codex replace sol-*@codex (6 Lanes)"
              in result.stdout
              and check.returncode == 0
              and "sol6-high@codex" in written["lanes"]
              and "sol-high@codex" not in written["lanes"]
              # the temp catalog is not this checkout's, so no agent file moved
              and "agent file" in result.stdout)
        return ok, (f"code={result.returncode} check={check.returncode} "
                    f"expected={expected} stdout={result.stdout[:600]!r}")


for name, case in (
    ("saved discovery never probes", case_saved_discovery_never_probes),
    ("tiers-from applies the page lines", case_tiers_from_applies_the_page_lines),
    ("tiers-from with an unreadable file writes nothing", case_tiers_from_unreadable_file_writes_nothing),
    ("plain prints the start facts", case_plain_prints_the_start_facts),
    ("a fresh fetch is not fetched again", case_a_fresh_fetch_is_not_fetched_again),
    ("a stale fetch is fetched again", case_a_stale_fetch_is_fetched_again),
    ("a failed fetch keeps the repo rows", case_a_failed_fetch_keeps_the_repo_rows),
    ("native agent files follow the claude lanes",
     case_native_agent_files_follow_the_claude_lanes),
    ("a catalog elsewhere gets no agent file", case_a_catalog_elsewhere_gets_no_agent_file),
    ("the refreshed rows reach the new lanes", case_the_refreshed_rows_reach_the_new_lanes),
    ("no-discover fetches no rows", case_no_discover_fetches_no_rows),
    ("plain prints the refresh change lines", case_plain_prints_the_refresh_change_lines),
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
    ("no-discover skips all acquisition", case_no_discover_skips_all_acquisition),
    ("one discovery path is discover.discover", case_one_discovery_path_is_discover),
    ("a harness error keeps existing lanes", case_harness_error_keeps_existing_lanes),
    ("plain collects bench in process", case_plain_collects_bench_in_process),
    ("focused screen on a pipe names the surgical CLI", case_focused_screen_rejects_plain),
    ("full start on a pipe still runs the wizard", case_start_screen_keeps_plain_wizard),
):
    try:
        ok, detail = case()
    except Exception as e:
        ok, detail = False, repr(e)
    record(name, ok, detail)

try:
    import setup
    with tempfile.TemporaryDirectory() as td:
        cfg = os.path.join(td, "cfg")
        real = os.path.join(td, "real")
        os.makedirs(cfg); os.makedirs(real)
        for name, doc in (("lanes.json", lanes_sample), ("routing.json", routing_sample)):
            catalog.write_json(os.path.join(real, name), doc)
            os.symlink(os.path.join(real, name), os.path.join(cfg, name))
        lp, rp = os.path.join(cfg, "lanes.json"), os.path.join(cfg, "routing.json")
        before = {p: open(p, "rb").read() for p in (lp, rp)}
        rev = catalog.catalog_revision(config_dir=cfg)
        setup.write_focused(cfg, rev, lanes_sample, routing_sample, lanes_sample, routing_sample, lp, rp)
        record("focused no-op preserves bytes and stow links",
               all(os.path.islink(p) and open(p, "rb").read() == before[p] for p in (lp, rp)))
        proposed = copy.deepcopy(routing_sample); proposed["meters"] = False
        setup.write_focused(cfg, rev, lanes_sample, routing_sample, lanes_sample, proposed, lp, rp)
        record("focused routing write follows stow link and preserves Lane bytes",
               os.path.islink(rp) and catalog.load_json(rp)["meters"] is False
               and open(lp, "rb").read() == before[lp])
        try:
            setup.write_focused(cfg, rev, lanes_sample, routing_sample, lanes_sample, routing_sample, lp, rp)
            stale_rejected = False
        except catalog.CatalogError:
            stale_rejected = True
        record("focused save rejects intervening source changes", stale_rejected)
except Exception as e:
    record("focused writes preserve stow and revisions", False, repr(e))

sys.exit(1 if fails else 0)
