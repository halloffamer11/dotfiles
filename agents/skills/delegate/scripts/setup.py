#!/usr/bin/env python3
"""Interactive catalog setup wizard for delegate."""
import argparse
import copy
import json
import os
import sys
import tempfile
import threading
import time

import bench
import bench_page
import catalog
import discover
import effort
import setup_tui
from catalog import CatalogError, CLASSES, HARNESSES, load_json, validate_lanes, validate_routing, write_json

# The wizard refreshes the Artificial Analysis rows itself, so that one command
# is one command (ticket 33). The fetch goes where `effort.py aa` would put it.
AA_CACHE_DIR = os.path.expanduser("~/.cache/delegate/bench/aa")
AA_MAX_AGE = 24 * 60 * 60
# The rows a fixture run reads instead of fetching, beside the harness fixtures.
AA_FIXTURE = "aa-accepted.json"

# A claude lane runs as a subagent, so the lane is not live until the agent file
# beside it is (ticket 22). Those files are `agents/agents/` in the checkout this
# skill is part of, and `make delegate-wizard` relinks them into ~/.claude/agents
# after the wizard exits. realpath, because the skill is reached by a stow link.
NATIVE_AGENTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.realpath(__file__))))),
    "agents",
)
NATIVE_AGENT_BODY = (
    "You are a delegate worker. Read the prompt file named in your task and follow it "
    "exactly. Your final message is the return block that the prompt asks for."
)


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


def show_bench(args, lanes_doc, routing_doc, rows=None):
    """`rows` is the `(rows, message)` pair `load_effort_rows` gives, already
    read from the refreshed list; without one this reads the list on `args`."""
    if args.no_bench:
        return
    if args.bench_report:
        try:
            with open(args.bench_report, "r", encoding="utf-8") as f:
                print(f.read(), end="")
        except OSError as e:
            print(f"bench: {e}")
        return

    effort_rows, effort_message = rows if rows is not None else load_effort_rows(args.effort_rows)
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
    print(f"meters: {'on' if catalog.meters_enabled(routing_doc) else 'off'}")


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
    current = "on" if catalog.meters_enabled(routing_doc) else "off"
    answer = read_answer(f"meters [{current}]: ").strip().lower()
    if answer in ("off", "false", "n", "no"):
        routing_doc["meters"] = False
    elif answer in ("on", "true", "y", "yes"):
        if "meters" not in routing_doc:
            pass
        else:
            routing_doc["meters"] = True


def aa_rows_path(paths):
    """The `--effort-rows` file that holds Artificial Analysis rows, or None."""
    for path in paths or ():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, list) and any(
            isinstance(row, dict) and row.get("source") == effort.AA_SOURCE for row in data
        ):
            return path
    return None


def _with_aa_rows(paths, refreshed):
    """`paths` with the Artificial Analysis file replaced by `refreshed`."""
    here = aa_rows_path(paths)
    if here is None:
        return list(paths) + [refreshed]
    return [refreshed if path == here else path for path in paths]


def refresh_effort_rows(paths, cache_dir=None, fixture_dir=None, now=None,
                        max_age=AA_MAX_AGE, fetch=None):
    """(the `--effort-rows` list with the Artificial Analysis rows refreshed,
    one line saying where they came from).

    `make delegate-wizard` is the one command (ticket 33), so the wizard reads
    the rows itself rather than asking for `effort.py aa` first. A fetch from
    the last 24 hours is reused, and a fetch that fails keeps the repo's rows
    and says why: a leaderboard that is down must never stop a catalog edit.
    Terminal-Bench rows stay as they are, because extracting them needs a
    worker. `fixture_dir` reads a saved rows file beside the harness fixtures,
    so a test and a fixture run touch no network and no cache.
    """
    paths = list(paths or [])
    if fixture_dir is not None:
        fixture = os.path.join(fixture_dir, AA_FIXTURE)
        if not os.path.isfile(fixture):
            return paths, f"Benchmark rows: repo rows; no {AA_FIXTURE} in {fixture_dir}"
        return _with_aa_rows(paths, fixture), f"Benchmark rows: Artificial Analysis from {fixture}"
    cache_dir = cache_dir or AA_CACHE_DIR
    accepted = os.path.join(cache_dir, "accepted.json")
    now = time.time() if now is None else now
    if os.path.isfile(accepted):
        age = now - os.path.getmtime(accepted)
        if 0 <= age < max_age:
            return (_with_aa_rows(paths, accepted),
                    f"Benchmark rows: Artificial Analysis fetched {int(age // 3600)}h ago, "
                    "still fresh")
    try:
        (fetch or effort.run_aa)(cache_dir, quiet=True)
    except Exception as e:
        # Every failure here is the same failure to the operator: the rows are
        # the repo's, and the reason is on the start page.
        return paths, f"Benchmark rows: repo rows; the Artificial Analysis fetch failed: {e}"
    return _with_aa_rows(paths, accepted), "Benchmark rows: Artificial Analysis fetched just now"


def published_model_names(rows):
    """The model names the Artificial Analysis rows print.

    Claude Code lists no model, so these are the only list of claude models
    there is; the refresh reads a newer version of a level the catalog already
    runs out of them (ticket 33).
    """
    return sorted({
        row["model"] for row in rows or ()
        if isinstance(row, dict) and row.get("source") == effort.AA_SOURCE
        and isinstance(row.get("model"), str)
    })


def native_agent_text(lane_name, lane):
    """The agent file for one native claude lane, in the form the files beside
    it take. A model that takes no effort level carries no `effort` line."""
    lines = [
        "---",
        f"name: lane-{lane_name.split('@', 1)[0]}",
        f'description: "Delegate native lane {lane_name}. Use only when /delegate prints a '
        'native line that names this agent, or when Orin names this lane."',
        f"model: {lane['model']}",
    ]
    if discover.model_takes_effort("claude", lane["model"]):
        lines.append(f"effort: {lane['effort']}")
    lines += ["---", "", NATIVE_AGENT_BODY, ""]
    return "\n".join(lines)


def native_agents_dir(config_dir):
    """Where a native claude lane's agent file goes, or None.

    The agent files and the catalog have to stay in step, so they are written
    only when the catalog being written is this checkout's own, which is how
    `make delegate-wizard` runs the wizard. A catalog somewhere else — a test,
    a throwaway copy — gets none, because the files beside this script are not
    that catalog's.
    """
    root = os.path.dirname(NATIVE_AGENTS_DIR)
    here = os.path.abspath(os.path.expanduser(config_dir or ""))
    return NATIVE_AGENTS_DIR if here.startswith(root + os.sep) else None


def save_native_agents(refresh, lanes_doc, agents_dir):
    """Write the agent file of each new claude lane, remove each superseded
    one, and return the lines to print.

    A claude lane runs as a subagent, so a new lane is not live until its file
    is; `make delegate-wizard` relinks them after the wizard exits, so the one
    command stays one command (ticket 33).
    """
    if not refresh:
        return []
    lanes = lanes_doc.get("lanes") or {}
    if agents_dir is None:
        waiting = [name for name in refresh.get("new") or ()
                   if (lanes.get(name) or {}).get("harness") == "claude"]
        if not waiting:
            return []
        return [f"note: {len(waiting)} new claude lanes need an agent file; this catalog is "
                "not the checkout's own, so none was written"]
    lines = []
    for name in refresh.get("new") or ():
        lane = lanes.get(name)
        if not isinstance(lane, dict) or lane.get("harness") != "claude":
            continue
        os.makedirs(agents_dir, exist_ok=True)
        path = os.path.join(agents_dir, f"lane-{name.split('@', 1)[0]}.md")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(native_agent_text(name, lane))
        lines.append(f"wrote {path}")
    for name in refresh.get("removed") or ():
        if not name.endswith("@claude") or name in lanes:
            continue
        path = os.path.join(agents_dir, f"lane-{name.split('@', 1)[0]}.md")
        if os.path.isfile(path):
            os.remove(path)
            lines.append(f"removed {path}")
    return lines


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


def confirm_and_write(lanes_doc, routing_doc, lanes_path, routing_path, refresh=None,
                      agents_dir=None):
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
    for line in save_native_agents(refresh, lanes_doc, agents_dir):
        print(line)


def write_focused(config_dir, revision, original_lanes, original_routing,
                  lanes, routing, lanes_path, routing_path):
    """Check the sources again and preserve links and unchanged document bytes."""
    if catalog.catalog_revision(config_dir=config_dir) != revision:
        raise CatalogError("intervening edit: catalog sources changed; reopen the focused screen")
    validate_lanes(lanes, lanes_path)
    validate_routing(routing, routing_path)
    written = False
    for path, old, new in ((lanes_path, original_lanes, lanes),
                           (routing_path, original_routing, routing)):
        if old != new:
            catalog._write_preserving_link(path, new)
            print(f"wrote {path}")
            written = True
    if not written:
        print("nothing changed; nothing written")


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
    parser.add_argument(
        "--screen",
        default="start",
        choices=("start", "carry", "tier1", "tier2", "tier3", "tier4", "review", "routing"),
        help="enter one setup screen; start is the full wizard",
    )
    args = parser.parse_args(argv)

    try:
        plain = args.plain or not sys.stdin.isatty() or not sys.stdout.isatty()
        if args.screen != "start" and plain:
            raise CatalogError(
                f"--screen {args.screen} needs a terminal; "
                "use catalog.py set, range, or order for non-interactive edits"
            )
        config_dir = os.path.abspath(os.path.expanduser(args.config_dir))
        focused_revision = catalog.catalog_revision(config_dir=config_dir) if args.screen != "start" else None
        tier_lines = read_tier_lines(args.tiers_from) if args.tiers_from else None
        existing = os.path.isfile(os.path.join(config_dir, "lanes.json"))
        # Start from the editable catalog, acquire once, then filter only a
        # first-time proposal. Existing catalog decisions survive probe errors.
        lanes_doc, routing_doc, lanes_path, routing_path = load_or_propose(
            config_dir, set(HARNESSES)
        )
        # The rows come off a web page and the models come off three CLIs;
        # neither waits on the other (ticket 33).
        rows_box = {}

        def fetch_rows():
            # --no-discover skips every live acquisition, the benchmark rows
            # included; a fixture run reads them beside the harness fixtures
            try:
                rows_box["value"] = (
                    (list(args.effort_rows or []), "") if args.no_discover
                    else refresh_effort_rows(args.effort_rows, fixture_dir=args.fixture_dir)
                )
            except Exception as e:
                # a thread that raises would print a traceback over the wizard
                rows_box["value"] = (args.effort_rows,
                                     f"Benchmark rows: repo rows; the refresh failed: {e}")

        fetcher = threading.Thread(target=fetch_rows, daemon=True)
        fetcher.start()
        discovered, discovery_data = acquire_discovery(lanes_doc, args)
        fetcher.join()
        effort_row_paths, rows_note = rows_box.get("value", (args.effort_rows, ""))
        rows = load_effort_rows(effort_row_paths)
        if not existing:
            lanes_doc, routing_doc, lanes_path, routing_path = load_or_propose(
                config_dir, discovered
            )
        else:
            note_undiscovered_lanes(lanes_doc, discovery_data)
        # The current generation, proposed in memory. Nothing is written until
        # the confirm, and quitting writes nothing.
        refresh = None
        if isinstance(discovery_data, dict) and discovery_data.get("models"):
            lanes_doc, refresh = discover.refresh_catalog(
                lanes_doc, discovery_data, published_models=published_model_names(rows[0])
            )
            discovery_data = discover.map_lanes(discovery_data, lanes_doc)
        # Discovery reports drift at the moment the human is already deciding
        # tiers, and it must never be able to stop them getting there: any
        # failure becomes the reason string the start facts print. Both
        # interfaces print the same facts.
        if plain:
            # the prompt-driven interface writes no benchmark page; it prints
            # the report instead, so the page line says (not written)
            for line in setup_tui.start_facts(lanes_path, routing_path, None, discovery_data,
                                              width=10_000, refresh=refresh,
                                              rows_note=rows_note):
                print(line)
            if tier_lines is not None:
                # the same parser and summary as the review page's `v`; the
                # tiers become the prompts' defaults, and an off line is written off
                parsed = setup_tui.parse_tier_lines(tier_lines, lanes_doc)
                dropped = setup_tui.apply_tier_lines_to_doc(lanes_doc, parsed)
                print(setup_tui.tier_lines_summary(parsed, dropped))
            if effort_row_paths:
                # The pre-screen is a selectable screen; there is no prompt-driven
                # form of it yet. Saying so is the point: the instruction a human
                # is given names --effort-rows, and a flag that reads as accepted
                # while nothing acts on it is worse than one that is refused.
                print("note: --effort-rows drives the pre-screen, which the prompt-driven "
                      "interface does not have; no lane will be proposed off. Run on a "
                      "terminal without --plain to use it.")
            show_bench(args, lanes_doc, routing_doc, rows=rows)
            ask_lanes(lanes_doc)
            if tier_lines is not None:
                # no review page here: the lines' order inside each tier is the
                # order written (ticket 28)
                setup_tui.write_order_from_lines(lanes_doc, parsed)
            ask_routing(routing_doc)
            confirm_and_write(lanes_doc, routing_doc, lanes_path, routing_path,
                              refresh=refresh, agents_dir=native_agents_dir(config_dir))
        else:
            if args.bench_report:
                print("note: --bench-report is ignored in TUI mode")
            bench_data = None
            initial_message = ""
            effort_rows, effort_message = rows
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
                focus=None if args.screen == "start" else args.screen,
                refresh=refresh,
                rows_note=rows_note,
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
                if args.screen != "start":
                    write_focused(config_dir, focused_revision, lanes_doc, routing_doc,
                                  result_lanes, result_routing, lanes_path, routing_path)
                else:
                    write_json(lanes_path, result_lanes)
                    write_json(routing_path, result_routing)
                    print(f"wrote {lanes_path}")
                    print(f"wrote {routing_path}")
                    for line in save_native_agents(refresh, result_lanes,
                                                   native_agents_dir(config_dir)):
                        print(line)
    except SetupAbort:
        return 130
    except CatalogError as e:
        sys.stderr.write(f"setup: {e}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
