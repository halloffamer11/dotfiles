#!/usr/bin/env python3
"""Interactive catalog setup wizard for delegate."""
import argparse
import copy
import json
import os
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


def present_from_discover_doc(doc):
    """Harness names present in a --discover-json fixture.

    Accepts the ADS `{discovered, missing}` shape used by existing tests, or
    the `discover.discover` result `{harnesses: {name: {status, ...}}}`.
    """
    if not isinstance(doc, dict):
        raise CatalogError("discovery failed: expected a JSON object")
    if isinstance(doc.get("discovered"), list) and isinstance(doc.get("missing"), list):
        found, missing = {}, {}
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
        return set(found), False
    if isinstance(doc.get("harnesses"), dict):
        found = {
            name for name, info in doc["harnesses"].items()
            if isinstance(info, dict) and info.get("status") == "ok"
        }
        return found, True
    raise CatalogError("discovery failed: expected discovered and missing lists")


def acquire_discovery(lanes_doc, args):
    """One discovery result for setup. Never shells out to discover.mjs.

    `--discover-json` is a fixture, not a live probe. `--no-discover` skips
    every live acquisition. A missing or failing harness is a notice: this
    function does not raise on a missing binary.
    Returns (discovered_set, discovery_data).
    """
    present = None
    fixture_result = None
    if args.discover_json:
        doc = load_json(args.discover_json)
        present, is_discover_result = present_from_discover_doc(doc)
        if is_discover_result:
            fixture_result = doc
        else:
            # The legacy snapshot contains Harness facts only; do not turn
            # absent model facts into permission for a live discovery call.
            fixture_result = {
                "harnesses": {name: {"status": "ok" if name in present else "missing"}
                              for name in HARNESSES},
                "models": [], "unmapped": [], "retired": [],
                "model_facts_available": False,
            }
    if args.no_discover:
        discovered = present if present is not None else set(HARNESSES)
        return discovered, "skipped (--no-discover)"
    if fixture_result is not None:
        return present, fixture_result
    try:
        discovery = discover.discover(
            lanes_doc,
            present=present,
            fixture_dir=args.fixture_dir,
        )
    except Exception as e:
        discovered = present if present is not None else set(HARNESSES)
        return discovered, str(e)
    discovered = {
        name for name, info in (discovery.get("harnesses") or {}).items()
        if isinstance(info, dict) and info.get("status") == "ok"
    }
    if present is not None:
        discovered = present
    return discovered, discovery


def read_discovery(args):
    """Compatibility wrapper: harness names only, from a fixture or a live probe."""
    discovered, _discovery = acquire_discovery({"lanes": {}}, args)
    return discovered


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


def note_undiscovered_lanes(lanes_doc, discovery_data):
    """A missing or failing harness is a notice; existing lanes stay."""
    if not isinstance(discovery_data, dict):
        return
    harnesses = discovery_data.get("harnesses") or {}
    for name, lane in lanes_doc["lanes"].items():
        info = harnesses.get(lane["harness"]) if isinstance(harnesses.get(lane["harness"]), dict) else {}
        status = info.get("status")
        if status == "missing":
            print(f"{name}: {lane['harness']} CLI not found; the lane stays but rank.py will veto it")
        elif status == "error":
            err = info.get("error") or "unknown error"
            print(f"{name}: {lane['harness']} discovery error ({err}); the lane stays")


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

    effort_rows, effort_message = load_effort_rows(args.effort_rows)
    if effort_message:
        print(effort_message)
        return
    try:
        data = bench.collect(
            lanes_doc,
            epoch_csv=args.epoch_csv,
            effort_rows=effort_rows,
        )
    except bench.BenchError as e:
        print(f"bench: {e}")
        return
    print(bench.format_collection(data, effort_rows=effort_rows), end="")


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
        order = f", order {lane['order']}" if "order" in lane else ""
        off = ", off" if lane.get("enabled") is False else ""
        print(f"{name}: tier {lane['tier']}{order}{off}")
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
    parser.add_argument("--ads-dir", default=None, help="unused; kept so existing callers still parse")
    parser.add_argument("--discover-json", default=None, help="saved discovery JSON instead of probing harnesses")
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
                             "at start; a carried lane no line names goes off, and the lines' order "
                             "inside a tier is the starting order; the review page's v key reads the "
                             "same lines from the clipboard")
    parser.add_argument("--no-discover", action="store_true", help="skip model discovery")
    parser.add_argument("--fixture-dir", default=None, help="fixture directory for harness discovery")
    args = parser.parse_args(argv)

    try:
        config_dir = os.path.abspath(os.path.expanduser(args.config_dir))
        tier_lines = read_tier_lines(args.tiers_from) if args.tiers_from else None
        existing = os.path.isfile(os.path.join(config_dir, "lanes.json"))
        # Start from the editable catalog, acquire once, then filter only a
        # first-time proposal. Existing catalog decisions survive probe errors.
        lanes_doc, routing_doc, lanes_path, routing_path = load_or_propose(
            config_dir, set(HARNESSES)
        )
        discovered, discovery_data = acquire_discovery(lanes_doc, args)
        if not existing:
            lanes_doc, routing_doc, lanes_path, routing_path = load_or_propose(
                config_dir, discovered
            )
        else:
            note_undiscovered_lanes(lanes_doc, discovery_data)
        plain = args.plain or not sys.stdin.isatty() or not sys.stdout.isatty()
        # Discovery reports drift at the moment the human is already deciding
        # tiers, and it must never be able to stop them getting there: any
        # failure becomes the reason string the start facts print. Both
        # interfaces print the same facts.
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
                dropped = setup_tui.apply_tier_lines_to_doc(lanes_doc, parsed)
                print(setup_tui.tier_lines_summary(parsed, dropped))
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
            if tier_lines is not None:
                # no review page here: the lines' order inside each tier is the
                # order written (ticket 28)
                setup_tui.write_order_from_lines(lanes_doc, parsed)
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
