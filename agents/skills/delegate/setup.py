#!/usr/bin/env python3
"""Interactive catalog setup wizard for delegate."""
import argparse
import copy
import json
import os
import subprocess
import sys
import tempfile

import catalog
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
        samples_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples")
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
        if args.aa_json:
            command.extend(["--aa-json", args.aa_json])
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
        lane["trust"] = ask_int("trust", lane["trust"], 1, 5)


def show_routing(routing_doc):
    for name in CLASSES:
        print(f"classTier.{name}: {routing_doc['classTier'][name]}")
    print(f"margin: {routing_doc['margin']}")
    print(f"gate: {routing_doc['gate']}")


def ask_routing(routing_doc):
    show_routing(routing_doc)
    if read_answer("keep routing as shown? [Y/n] ").strip().lower() != "n":
        return
    for name in CLASSES:
        routing_doc["classTier"][name] = ask_int(
            f"{name} tier", routing_doc["classTier"][name], 1, 4
        )
    routing_doc["margin"] = ask_fraction("margin", routing_doc["margin"])
    routing_doc["gate"] = ask_fraction("gate", routing_doc["gate"])


def confirm_and_write(lanes_doc, routing_doc, lanes_path, routing_path):
    print(lanes_path)
    print(routing_path)
    for name, lane in lanes_doc["lanes"].items():
        print(f"{name}: tier {lane['tier']} trust {lane['trust']}")
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
    bench_group = parser.add_mutually_exclusive_group()
    bench_group.add_argument("--bench-report", default=None, help="existing benchmark report to display")
    bench_group.add_argument("--no-bench", action="store_true", help="skip benchmark display")
    parser.add_argument("--epoch-csv", default=None, help="local Epoch CSV for bench.py")
    parser.add_argument("--aa-json", default=None, help="local Artificial Analysis JSON for bench.py")
    args = parser.parse_args(argv)

    try:
        config_dir = os.path.abspath(os.path.expanduser(args.config_dir))
        discovered = read_discovery(args)
        lanes_doc, routing_doc, lanes_path, routing_path = load_or_propose(config_dir, discovered)
        show_bench(args, lanes_doc, routing_doc)
        ask_lanes(lanes_doc)
        ask_routing(routing_doc)
        confirm_and_write(lanes_doc, routing_doc, lanes_path, routing_path)
    except SetupAbort:
        return 130
    except CatalogError as e:
        sys.stderr.write(f"setup: {e}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
