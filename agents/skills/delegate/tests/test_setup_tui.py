#!/usr/bin/env python3
"""State-machine and pty smoke tests for setup_tui.py."""
import copy
import fcntl
import json
import os
import pty
import struct
import subprocess
import sys
import tempfile
import termios
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DELEGATE_DIR = os.path.abspath(os.path.join(HERE, "..", "scripts"))
FIXTURE = os.path.join(HERE, "fixture", "bench-epoch.csv")
sys.path.insert(0, DELEGATE_DIR)

import bench
import catalog
from setup_tui import Wizard

LANES = catalog.load_json(os.path.abspath(os.path.join(HERE, "..", "assets", "samples", "lanes.json")))
ROUTING = catalog.load_json(os.path.abspath(os.path.join(HERE, "..", "assets", "samples", "routing.json")))
DISCOVERED = set(catalog.HARNESSES)
fails = 0


def record(name, ok, detail=""):
    global fails
    if ok:
        print(f"PASS {name}")
    else:
        fails += 1
        print(f"FAIL {name}: {detail}")


def data():
    return bench.collect(copy.deepcopy(LANES), epoch_csv=FIXTURE, key_file=None)


def wizard(bench_data=True, message=""):
    return Wizard(copy.deepcopy(LANES), copy.deepcopy(ROUTING),
                  data() if bench_data else None, DISCOVERED,
                  "/tmp/lanes.json", "/tmp/routing.json", message)


def start(w):
    w.handle("enter")
    w.handle("enter")


def move_to(w, lane):
    for _ in range(len(w.view()["rows"]) + 1):
        row = next((r for r in w.view()["rows"] if r["cursor"]), None)
        if row and row["cells"][1] == lane:
            return
        w.handle("down")
    raise AssertionError(f"could not move to {lane}")


def finish(w):
    while w.screen == "tier":
        w.handle("enter")
    if w.screen == "routing":
        w.handle("enter")
    if w.screen == "confirm":
        w.handle("y")


try:
    collected = data()
    record("collect returns documented keys",
           set(collected) == {"models", "epoch_benchmarks", "aa_columns", "aa_skipped", "notes"})
except Exception as e:
    record("collect returns documented keys", False, repr(e))

try:
    w = wizard()
    start(w)
    v = w.view()
    active = [r for r in v["rows"] if not r["dimmed"]]
    models = [r["cells"][2] for r in active]
    fable = next(r for r in active if r["cells"][1] == "fable-xhigh@claude")
    sol = next(r for r in active if r["cells"][1] == "sol-high@codex")
    flash = next(r for r in active if r["cells"][1] == "flash-high@agy")
    record("1 tier 4 selection and benchmark order",
           v["tier"] == 4 and fable["marked"]
           and models[:2] == ["claude-fable-5-1", "gpt-5.6-sol"]
           and models[-1] == "gemini-3.8-flash-high"
           and "98.0" in fable["cells"] and "90.0" in sol["cells"]
           and all(x == "—" for x in flash["cells"][4:9])
           and flash["cells"][9].startswith("—"), str(v))
except Exception as e:
    record("1 tier 4 selection and benchmark order", False, repr(e))

try:
    w = wizard()
    start(w)
    finish(w)
    record("2 unchanged round trip", w.result() == (LANES, ROUTING), repr(w.result()))
except Exception as e:
    record("2 unchanged round trip", False, repr(e))

try:
    w = wizard()
    start(w)
    move_to(w, "sol-high@codex")
    w.handle("space")
    w.handle("enter")
    sol = next(r for r in w.view()["rows"] if r["cells"][1] == "sol-high@codex")
    dimmed = sol["dimmed"] and sol["tag"] == "tier 4"
    finish(w)
    lanes, _ = w.result()
    record("3 higher-tier lanes dim and persist",
           dimmed and lanes["lanes"]["sol-high@codex"]["tier"] == 4
           and lanes["lanes"]["terra-high@codex"]["tier"] == 2)
except Exception as e:
    record("3 higher-tier lanes dim and persist", False, repr(e))

try:
    w = wizard()
    start(w)
    w.handle("enter")
    w.handle("enter")
    move_to(w, "grok46-high@grok")
    w.handle("4")
    finish(w)
    lanes, routing = w.result()
    record("4 digit keys are inert on the tier screen",
           lanes == LANES and routing == ROUTING)
except Exception as e:
    record("4 digit keys are inert on the tier screen", False, repr(e))

try:
    w = wizard()
    start(w)
    w.handle("enter")
    w.handle("enter")
    w.handle("enter")
    move_to(w, "luna-low@codex")
    w.handle("space")
    w.handle("enter")
    blocked = w.screen == "tier" and w.tier == 1 and w.view()["message"] == "every lane needs a tier"
    w.handle("space")
    w.handle("enter")
    record("5 tier 1 requires every lane", blocked and w.screen == "routing")
except Exception as e:
    record("5 tier 1 requires every lane", False, repr(e))

try:
    w = wizard()
    start(w)
    for _ in range(4):
        w.handle("enter")
    for _ in range(3):
        w.handle("down")
    w.handle("plus")
    for _ in range(2):
        w.handle("down")
    w.handle("plus")
    w.handle("enter")
    w.handle("y")
    lanes, routing = w.result()
    expected = copy.deepcopy(ROUTING)
    expected["classTier"]["review"] = 3
    expected["margin"] = 0.25
    record("6 routing edits are isolated", lanes == LANES and routing == expected, repr(routing))
except Exception as e:
    record("6 routing edits are isolated", False, repr(e))

try:
    w1 = wizard(); start(w1); finish(w1)
    # finish accepts, so use a fresh wizard stopped at confirm for decline.
    w1 = wizard(); start(w1)
    for _ in range(4): w1.handle("enter")
    w1.handle("enter"); w1.handle("n")
    w2 = wizard(); start(w2); w2.handle("q")
    record("7 decline and early quit return no result",
           w1.screen == "quit" and w1.result() is None
           and w2.screen == "quit" and w2.result() is None)
except Exception as e:
    record("7 decline and early quit return no result", False, repr(e))

try:
    w = wizard(); start(w); move_to(w, "sol-high@codex"); w.handle("space")
    w.handle("enter"); w.handle("b")
    sol = next(r for r in w.view()["rows"] if r["cells"][1] == "sol-high@codex")
    record("8 back restores prior tier marks",
           w.tier == 4 and sol["marked"] and not sol["dimmed"])
except Exception as e:
    record("8 back restores prior tier marks", False, repr(e))

try:
    w = wizard(False, "fixture unavailable")
    initial = w.view()["message"] == "fixture unavailable"
    start(w)
    row = w.view()["rows"][0]
    record("9 absent benchmarks render em dashes",
           initial and all(value == "—" for value in row["cells"][5:11]))
except Exception as e:
    record("9 absent benchmarks render em dashes", False, repr(e))

try:
    w = wizard()
    v = w.view()
    body = "\n".join(v.get("body") or [])
    record("11 start screen names both files",
           v["screen"] == "start" and v["columns"] == [] and v["rows"] == []
           and w.lanes_path in body and w.routing_path in body
           and "Nothing is written until the confirm screen" in body
           and "q leaves without writing" in body)
    w.handle("q")
    record("11b q on start quits without writing",
           w.screen == "quit" and w.result() is None)
except Exception as e:
    record("11 start screen names both files", False, repr(e))

try:
    w = wizard()
    w.handle("other")
    record("11c any unmapped key leaves start", w.screen == "discovery")
    w2 = wizard()
    w2.handle("o")
    record("11d o on start does not advance", w2.screen == "start")
except Exception as e:
    record("11c any unmapped key leaves start", False, repr(e))

try:
    w = wizard()
    start(w)
    # the tier definition renders as the last legend line, directly above the
    # key hints, so the two together are the footer block the human reads
    footer = w.view()["footer"] + "  " + "  ".join(w.view().get("legend") or [])
    record("12 tier footer carries the tier one-liner",
           w.screen == "tier"
           and "ceiling" in footer
           and "o: open benchmark page" in footer)
    before_cursor = w.cursor
    w.handle("x")
    w.handle("d")
    record("12b x and d are unbound on tier",
           w.screen == "tier" and w.cursor == before_cursor and w.tier == 4)
except Exception as e:
    record("12 tier footer carries the tier one-liner", False, repr(e))

try:
    w = wizard()
    start(w)
    incoming_sol = LANES["lanes"]["sol-high@codex"]["tier"]
    move_to(w, "sol-high@codex")
    w.handle("space")
    w.handle("enter")
    while w.screen == "tier":
        w.handle("enter")
    legend = w.view().get("legend") or []
    t4 = next(line for line in legend if line.startswith("tier 4:"))
    t_incoming = next(line for line in legend if line.startswith(f"tier {incoming_sol}:"))
    prefixes = [line.split(":", 1)[0] for line in legend if line.startswith("tier ")]
    record("13 routing legend maps this session's assignments",
           w.screen == "routing"
           and incoming_sol != 4
           and "sol-high@codex" in t4
           and "sol-high@codex" not in t_incoming
           and prefixes[:4] == ["tier 1", "tier 2", "tier 3", "tier 4"]
           and any("margin:" in line for line in legend)
           and any("gate:" in line for line in legend)
           and any("0.2" in line for line in legend)
           and any("10%" in line for line in legend))
    w.handle("enter")
    confirm_legend = w.view().get("legend") or []
    record("14 confirm legend explains classTier, margin and gate",
           w.screen == "confirm"
           and any("classTier:" in line for line in confirm_legend)
           and any("margin:" in line for line in confirm_legend)
           and any("gate:" in line for line in confirm_legend)
           and any("0.2" in line for line in confirm_legend)
           and any("10%" in line for line in confirm_legend))
    w.handle("y")
    lanes, routing = w.result()
    record("15 key sequence write path is unchanged",
           lanes["lanes"]["sol-high@codex"]["tier"] == 4
           and routing == ROUTING)
except Exception as e:
    record("13 routing legend maps this session's assignments", False, repr(e))


def pty_smoke():
    with tempfile.TemporaryDirectory() as td:
        config_dir = os.path.join(td, "config")
        discover_path = os.path.join(td, "discover.json")
        discover = {
            "version": "delegate-discover.v1",
            "discovered": [{"key": key, "binary": key, "version": "test",
                            "authenticated": True} for key in catalog.HARNESSES],
            "missing": [],
        }
        with open(discover_path, "w", encoding="utf-8") as f:
            json.dump(discover, f)
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 140, 0, 0))
        env = dict(os.environ, TERM="xterm-256color", LINES="40", COLUMNS="140")
        proc = subprocess.Popen(
            [sys.executable, os.path.join(DELEGATE_DIR, "setup.py"),
             "--config-dir", config_dir, "--discover-json", discover_path,
             "--epoch-csv", FIXTURE],
            stdin=slave, stdout=slave, stderr=slave, cwd=DELEGATE_DIR, env=env,
            close_fds=True,
        )
        os.close(slave)
        output = bytearray()
        deadline = time.monotonic() + 30
        try:
            os.set_blocking(master, False)
            for key in [b"\n"] * 7 + [b"y"]:
                try:
                    while chunk := os.read(master, 65536):
                        output.extend(chunk)
                except BlockingIOError:
                    pass
                os.write(master, key)
                time.sleep(0.3)
            while proc.poll() is None and time.monotonic() < deadline:
                try:
                    while chunk := os.read(master, 65536):
                        output.extend(chunk)
                except BlockingIOError:
                    pass
                time.sleep(0.05)
        finally:
            os.close(master)
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        lanes_path = os.path.join(config_dir, "lanes.json")
        routing_path = os.path.join(config_dir, "routing.json")
        if proc.returncode != 0 or not os.path.isfile(lanes_path) or not os.path.isfile(routing_path):
            return False, (f"exit={proc.returncode} lanes={os.path.isfile(lanes_path)} "
                           f"routing={os.path.isfile(routing_path)} output={bytes(output[-1000:])!r}")
        catalog.check_file(lanes_path)
        catalog.check_file(routing_path)
        return True, ""


try:
    ok, detail = pty_smoke()
    record("10 pty smoke", ok, detail)
except OSError as e:
    print(f"SKIP pty smoke: {e}")
except Exception as e:
    record("10 pty smoke", False, repr(e))

sys.exit(1 if fails else 0)
