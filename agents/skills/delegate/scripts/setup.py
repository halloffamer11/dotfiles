#!/usr/bin/env python3
"""Interactive catalog setup wizard for delegate."""
import argparse
import copy
import json
import os
import subprocess
import sys
import tempfile

import bench
import bench_page
import catalog
import discover
import setup_tui
from catalog import CatalogError, CLASSES, HARNESSES, load_json, validate_lanes, validate_routing, write_json


class SetupAbort(Exception):
    """The operator ended interactive input before confirming a write."""


def default_ads_dir():
    return os.path.expanduser(os.environ.get("ADS_DIR", "~/.local/share/delegate/ads"))


def read_discovery(args):
    if args.discover_json:
        doc = load_json(args.discover_json)
    else:
        ads_dir = os.path.expanduser(args.ads_dir or default_ads_dir())
        script = os.path.join(ads_dir, "skills", "delegate-setup", "scripts", "discover.mjs")
        try:
            result = subprocess.run(
                ["node", script], capture_output=True, text=True, check=False
            )
        except OSError as e:
            raise CatalogError(f"discovery failed: {e}") from e
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
            raise CatalogError(f"discovery failed: {message}")
        try:
            doc = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise CatalogError(f"discovery failed: invalid JSON: {e}") from e

    if not isinstance(doc, dict) or not isinstance(doc.get("discovered"), list) or not isinstance(doc.get("missing"), list):
        raise CatalogError("discovery failed: expected discovered and missing lists")

    found = {}
    missing = {}
    for item in doc["discovered"]:
        if isinstance(item, dict) and item.get("key") in HARNESSES:
            found[item["key"]] = item
    for item in doc["missing"]:
        if isinstance(item, dict) and item.get("key") in HARNESSES:
            missing[item["key"]] = item

    for harness in HARNESSES:
        if harness in found:
            item = found[harness]
            print(
                f"discovered {harness}: version={item.get('version', 'unknown')} "
                f"authenticated={item.get('authenticated', None)}"
            )
        elif harness in missing:
            item = missing[harness]
            print(f"missing {harness}: {item.get('binary', harness)}")
    return set(found)


def load_or_propose(config_dir, discovered):
    lanes_path = os.path.join(config_dir, "lanes.json")
    routing_path = os.path.join(config_dir, "routing.json")
    if os.path.isfile(lanes_path):
        lanes_doc = load_json(lanes_path)
        routing_doc = load_json(routing_path)
        validate_lanes(lanes_doc, lanes_path)
        validate_routing(routing_doc, routing_path)
    else:
        samples_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "samples"))
        sample_lanes = load_json(os.path.join(samples_dir, "lanes.json"))
        lanes_doc = copy.deepcopy(sample_lanes)
        lanes_doc["lanes"] = {
            name: lane
            for name, lane in sample_lanes["lanes"].items()
            if lane["harness"] in discovered
        }
        meters_used = {lane["meter"] for lane in lanes_doc["lanes"].values()}
        lanes_doc["meters"] = {
            name: meter
            for name, meter in sample_lanes["meters"].items()
            if name in meters_used
        }
        routing_doc = load_json(os.path.join(samples_dir, "routing.json"))

    lane_harnesses = {lane["harness"] for lane in lanes_doc["lanes"].values()}
    for harness in HARNESSES:
        if harness in discovered and harness not in lane_harnesses:
            print(f"no sample lane for {harness}; add one to lanes.json by hand")
    for name, lane in lanes_doc["lanes"].items():
        if lane["harness"] not in discovered:
            print(f"{name}: {lane['harness']} CLI not found; the lane stays but rank.py will veto it")
    return lanes_doc, routing_doc, lanes_path, routing_path


def show_bench(args, lanes_doc, routing_doc):
    if args.no_bench:
        return
    if args.bench_report:
        try:
            with open(args.bench_report, "r", encoding="utf-8") as f:
                print(f.read(), end="")
        except OSError as e:
            print(f"bench: {e}")
        return

    with tempfile.TemporaryDirectory() as config_dir:
        write_json(os.path.join(config_dir, "lanes.json"), lanes_doc)
        write_json(os.path.join(config_dir, "routing.json"), routing_doc)
        command = [sys.executable, os.path.join(os.path.dirname(__file__), "bench.py"), "--config-dir", config_dir]
        if args.epoch_csv:
            command.extend(["--epoch-csv", args.epoch_csv])
        for path in args.effort_rows or ():
            command.extend(["--effort-rows", path])
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            print((result.stderr or result.stdout or f"bench: exit {result.returncode}").rstrip())
            return
        report_path = None
        for line in result.stdout.splitlines():
            if line.startswith("bench: wrote "):
                report_path = line[len("bench: wrote "):]
        if not report_path:
            print((result.stderr or result.stdout or "bench: did not report an output file").rstrip())
            return
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                print(f.read(), end="")
        except OSError as e:
            print(f"bench: {e}")


def read_answer(prompt):
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt) as e:
        raise SetupAbort from e


def ask_int(label, current, low, high):
    rule = f"{label} must be an integer from {low} to {high}"
    while True:
        answer = read_answer(f"{label} [{current}]: ").strip()
        if not answer:
            return current
        try:
            value = int(answer)
        except ValueError:
            value = None
        if value is not None and low <= value <= high:
            return value
        print(rule)


def ask_fraction(label, current):
    rule = f"{label} must be a number between 0 and 1"
    while True:
        answer = read_answer(f"{label} [{current}]: ").strip()
        if not answer:
            return current
        try:
            value = float(answer)
        except ValueError:
            value = None
        if value is not None and 0.0 <= value <= 1.0:
            return value
        print(rule)


def ask_lanes(lanes_doc):
    for name, lane in lanes_doc["lanes"].items():
        print(name)
        print(f"  harness: {lane['harness']}")
        print(f"  model: {lane['model']}")
        print(f"  effort: {lane['effort']}")
        print(f"  meter: {lane['meter']}")
        print(f"  basis: {lane['basis']}")
        lane["tier"] = ask_int("tier", lane["tier"], 1, 4)


def show_routing(routing_doc):
    for name in CLASSES:
        cls_info = routing_doc["classes"][name]
        print(f"classes.{name}: floor={cls_info['floor']} ceiling={cls_info['ceiling']}")
    print(f"margin: {routing_doc['margin']}")
    print(f"gate: {routing_doc['gate']}")


def ask_routing(routing_doc):
    show_routing(routing_doc)
    if read_answer("keep routing as shown? [Y/n] ").strip().lower() != "n":
        return
    for name in CLASSES:
        cls_info = routing_doc["classes"][name]
        f = ask_int(f"{name} floor", cls_info["floor"], 1, 4)
        c = ask_int(f"{name} ceiling", max(f, cls_info["ceiling"]), f, 4)
        cls_info["floor"] = f
        cls_info["ceiling"] = c
    routing_doc["margin"] = ask_fraction("margin", routing_doc["margin"])
    routing_doc["gate"] = ask_fraction("gate", routing_doc["gate"])


def load_effort_rows(paths):
    """Every row from one file or several, in order. The pre-screen judges each
    source on its own rows, so files from different sources combine safely."""
    if not paths:
        return None, ""
    if isinstance(paths, str):
        paths = [paths]
    rows = []
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except OSError as e:
            return None, f"effort-rows: {e}"
        except json.JSONDecodeError as e:
            return None, f"effort-rows: {path}: invalid JSON: {e}"
        if not isinstance(data, list):
            return None, f"effort-rows: {path}: expected a JSON list"
        rows.extend(data)
    return rows, ""


def read_tier_lines(path):
    """The text of a `--tiers-from` file. A file that cannot be read stops the
    run before anything is shown: a flag that reads as accepted while nothing
    acts on it is worse than one that is refused."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError) as e:
        raise CatalogError(f"tiers-from: {e}") from e


def confirm_and_write(lanes_doc, routing_doc, lanes_path, routing_path):
    print(lanes_path)
    print(routing_path)
    for name, lane in lanes_doc["lanes"].items():
        print(f"{name}: tier {lane['tier']}")
    answer = read_answer("write both files? [y/N] ").strip()
    if answer not in ("y", "yes"):
        print("nothing written")
        return
    validate_lanes(lanes_doc, lanes_path)
    validate_routing(routing_doc, routing_path)
    write_json(lanes_path, lanes_doc)
    write_json(routing_path, routing_doc)
    print(f"wrote {lanes_path}")
    print(f"wrote {routing_path}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Interactively create or revise a delegate catalog.")
    parser.add_argument("--config-dir", default=catalog.CONFIG_DIR, help="directory for lanes.json and routing.json")
    parser.add_argument("--ads-dir", default=None, help="ADS checkout containing discover.mjs")
    parser.add_argument("--discover-json", default=None, help="saved discovery JSON instead of node discovery")
    parser.add_argument("--plain", action="store_true", help="use the prompt-driven interface")
    bench_group = parser.add_mutually_exclusive_group()
    bench_group.add_argument("--bench-report", default=None, help="existing benchmark report to display")
    bench_group.add_argument("--no-bench", action="store_true", help="skip benchmark display")
    parser.add_argument("--epoch-csv", default=None, help="local Epoch CSV for bench.py")
    parser.add_argument("--effort-rows", action="append", default=None,
                        help="effort.py accepted rows for the pre-screen, the benchmark page and "
                             "the Artificial Analysis columns; repeat to put several sources on one page")
    parser.add_argument("--tiers-from", default=None, metavar="FILE",
                        help="apply `<lane> <1-4|off>` lines, as the benchmark page copies them, "
                             "at start; the review page's v key reads the same lines from the clipboard")
    parser.add_argument("--no-discover", action="store_true", help="skip model discovery")
    parser.add_argument("--fixture-dir", default=None, help="fixture directory for harness discovery")
    args = parser.parse_args(argv)

    try:
        config_dir = os.path.abspath(os.path.expanduser(args.config_dir))
        tier_lines = read_tier_lines(args.tiers_from) if args.tiers_from else None
        discovered = read_discovery(args)
        lanes_doc, routing_doc, lanes_path, routing_path = load_or_propose(config_dir, discovered)
        plain = args.plain or not sys.stdin.isatty() or not sys.stdout.isatty()
        # Discovery shells out to three harness CLIs. It reports drift at the
        # moment the human is already deciding tiers, and it must never be
        # able to stop them getting there: any failure becomes the reason
        # string the start facts print. Both interfaces print the same facts.
        if args.no_discover:
            discovery_data = "skipped (--no-discover)"
        else:
            try:
                discovery_data = discover.discover(lanes_doc, fixture_dir=args.fixture_dir)
            except Exception as e:
                discovery_data = str(e)
        if plain:
            # the prompt-driven interface writes no benchmark page; it prints
            # the report instead, so the page line says (not written)
            for line in setup_tui.start_facts(lanes_path, routing_path, None, discovery_data,
                                              width=10_000):
                print(line)
            if tier_lines is not None:
                # the same parser and summary as the review page's `v`; the
                # tiers become the prompts' defaults, and an off line is written off
                parsed = setup_tui.parse_tier_lines(tier_lines, lanes_doc)
                setup_tui.apply_tier_lines_to_doc(lanes_doc, parsed)
                print(setup_tui.tier_lines_summary(parsed, lanes_doc))
            if args.effort_rows:
                # The pre-screen is a selectable screen; there is no prompt-driven
                # form of it yet. Saying so is the point: the instruction a human
                # is given names --effort-rows, and a flag that reads as accepted
                # while nothing acts on it is worse than one that is refused.
                print("note: --effort-rows drives the pre-screen, which the prompt-driven "
                      "interface does not have; no lane will be proposed off. Run on a "
                      "terminal without --plain to use it.")
            show_bench(args, lanes_doc, routing_doc)
            ask_lanes(lanes_doc)
            ask_routing(routing_doc)
            confirm_and_write(lanes_doc, routing_doc, lanes_path, routing_path)
        else:
            if args.bench_report:
                print("note: --bench-report is ignored in TUI mode")
            bench_data = None
            initial_message = ""
            effort_rows, effort_message = load_effort_rows(args.effort_rows)
            if not args.no_bench:
                try:
                    bench_data = bench.collect(
                        lanes_doc,
                        epoch_csv=args.epoch_csv,
                        effort_rows=effort_rows,
                    )
                except bench.BenchError as e:
                    initial_message = f"bench: {e}"
            if effort_message:
                initial_message = f"{initial_message}; {effort_message}" if initial_message else effort_message
            fd, page_path = tempfile.mkstemp(prefix="delegate-bench-", suffix=".html")
            os.close(fd)
            try:
                bench_page.write(page_path, bench_data, lanes_doc, effort_rows)
            except OSError as e:
                page_path = None
                page_message = f"benchmark page: {e}"
                initial_message = f"{initial_message}; {page_message}" if initial_message else page_message
            wizard = setup_tui.Wizard(
                lanes_doc, routing_doc, bench_data, discovered,
                lanes_path, routing_path, initial_message,
                bench_page_path=page_path,
                effort_rows=effort_rows,
                discovery=discovery_data,
            )
            if tier_lines is not None:
                summary = wizard.apply_tier_lines(tier_lines)
                wizard.message = f"{initial_message}; {summary}" if initial_message else summary
            result = setup_tui.run_curses(wizard)
            if result is None:
                print("nothing written")
            else:
                result_lanes, result_routing = result
                validate_lanes(result_lanes, lanes_path)
                validate_routing(result_routing, routing_path)
                write_json(lanes_path, result_lanes)
                write_json(routing_path, result_routing)
                print(f"wrote {lanes_path}")
                print(f"wrote {routing_path}")
    except SetupAbort:
        return 130
    except CatalogError as e:
        sys.stderr.write(f"setup: {e}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
