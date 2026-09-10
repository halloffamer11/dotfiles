#!/usr/bin/env python3
"""Selectable terminal setup UI for delegate catalogs."""
import copy

from bench import EPOCH_BENCHMARKS
from catalog import CLASSES, HARNESSES


class Wizard:
    """Pure setup state.  Rendering and terminal input live in run_curses."""

    def __init__(self, lanes_doc, routing_doc, bench, discovered,
                 lanes_path, routing_path, initial_message=""):
        self._original_lanes = copy.deepcopy(lanes_doc)
        self._original_routing = copy.deepcopy(routing_doc)
        self.lanes_doc = copy.deepcopy(lanes_doc)
        self.routing_doc = copy.deepcopy(routing_doc)
        self.bench = bench
        self.discovered = set(discovered)
        self.lanes_path = lanes_path
        self.routing_path = routing_path
        self.screen = "discovery"
        self.tier = None
        self.cursor = 0
        self.message = initial_message or ("benchmark data unavailable" if bench is None else "")
        self._result = None
        self._assigned = {}
        self._marks = {
            tier: {name for name, lane in lanes_doc["lanes"].items()
                   if lane["tier"] == tier}
            for tier in range(1, 5)
        }

    def result(self):
        return self._result

    def _mean(self, lane_name):
        if self.bench is None:
            return None
        model = self.lanes_doc["lanes"][lane_name]["model"]
        rec = self.bench.get("models", {}).get(model)
        return rec["epoch"]["mean"] if rec else None

    def _tier_names(self):
        active = [name for name in self.lanes_doc["lanes"] if name not in self._assigned]
        active.sort(key=lambda name: (
            self._mean(name) is None,
            self._mean(name) if self._mean(name) is not None else 0,
            name,
        ))
        dimmed = [name for name in self.lanes_doc["lanes"] if name in self._assigned]
        dimmed.sort(key=lambda name: (-self._assigned[name], name))
        return active, dimmed

    def _enter_tier(self, tier):
        self.screen = "tier"
        self.tier = tier
        self.cursor = 0
        self.message = ""
        if tier == 1:
            active, _ = self._tier_names()
            self._marks[1].update(active)

    def _active_name(self):
        active, _ = self._tier_names()
        if not active:
            return None
        self.cursor = min(self.cursor, len(active) - 1)
        return active[self.cursor]

    def handle(self, key):
        if self.screen in ("done", "quit"):
            return
        if key == "q" and self.screen != "confirm":
            self.screen = "quit"
            self._result = None
            return
        if self.screen == "discovery":
            self._enter_tier(4)
            return
        if self.screen == "tier":
            active, _ = self._tier_names()
            if key == "up" and active:
                self.cursor = (self.cursor - 1) % len(active)
            elif key == "down" and active:
                self.cursor = (self.cursor + 1) % len(active)
            elif key == "space":
                name = self._active_name()
                if name:
                    if name in self._marks[self.tier]:
                        self._marks[self.tier].remove(name)
                    else:
                        self._marks[self.tier].add(name)
            elif key == "enter":
                active, _ = self._tier_names()
                if self.tier == 1 and any(name not in self._marks[1] for name in active):
                    self.message = "every lane needs a tier"
                    return
                for name in active:
                    if name in self._marks[self.tier]:
                        self._assigned[name] = self.tier
                if self.tier > 1:
                    self._enter_tier(self.tier - 1)
                else:
                    self.screen = "routing"
                    self.tier = None
                    self.cursor = 0
                    self.message = ""
            elif key == "b" and self.tier < 4:
                previous = self.tier + 1
                for name in list(self._assigned):
                    if self._assigned[name] == previous:
                        del self._assigned[name]
                self._enter_tier(previous)
            return
        if self.screen == "routing":
            count = len(CLASSES) + 2
            if key == "up":
                self.cursor = (self.cursor - 1) % count
            elif key == "down":
                self.cursor = (self.cursor + 1) % count
            elif key in ("plus", "minus"):
                delta = 1 if key == "plus" else -1
                if self.cursor < len(CLASSES):
                    name = CLASSES[self.cursor]
                    old = self.routing_doc["classTier"][name]
                    self.routing_doc["classTier"][name] = min(4, max(1, old + delta))
                else:
                    name = "margin" if self.cursor == len(CLASSES) else "gate"
                    old = self.routing_doc[name]
                    self.routing_doc[name] = round(min(1.0, max(0.0, old + delta * 0.05)), 2)
            elif key == "enter":
                self.screen = "confirm"
                self.cursor = 0
                self.message = ""
            elif key == "b":
                for name in list(self._assigned):
                    if self._assigned[name] == 1:
                        del self._assigned[name]
                self._enter_tier(1)
            return
        if self.screen == "confirm":
            if key == "y":
                result_lanes = copy.deepcopy(self._original_lanes)
                for name, lane in result_lanes["lanes"].items():
                    lane["tier"] = self._assigned[name]
                self._result = (result_lanes, copy.deepcopy(self.routing_doc))
                self.screen = "done"
            elif key in ("n", "q"):
                self._result = None
                self.screen = "quit"
            elif key == "b":
                self.screen = "routing"
                self.cursor = 0

    def _bench_cells(self, lane):
        epoch_names = (self.bench or {}).get("epoch_benchmarks", list(EPOCH_BENCHMARKS))
        model_rec = (self.bench or {}).get("models", {}).get(lane["model"])
        if model_rec:
            epoch = model_rec["epoch"]
            values = [
                "—" if name not in epoch["cells"] else f'{epoch["cells"][name]["performance"] * 100:.1f}'
                for name in epoch_names
            ]
            values.append(epoch["mean_s"])
        else:
            values = ["—"] * len(epoch_names) + ["—"]
        if self.bench is not None and self.bench.get("aa_skipped") is None:
            aa_names = self.bench["aa_columns"]
            aa = model_rec.get("aa") if model_rec else None
            for name in aa_names:
                value = aa["cols"].get(name) if aa else None
                values.append("—" if value is None else (str(int(value)) if value == int(value) else f"{value:.1f}"))
            values.append(aa["mean_s"] if aa else "—")
        return values

    def view(self):
        if self.screen == "discovery":
            return {
                "screen": "discovery", "title": "Delegate setup: discovery", "tier": None,
                "columns": ["harness", "status"],
                "rows": [{"cells": [name, "found" if name in self.discovered else "missing"],
                          "marked": False, "dimmed": name not in self.discovered,
                          "cursor": False, "tag": ""} for name in HARNESSES],
                "footer": "any key: continue  q: quit", "message": self.message,
            }
        if self.screen == "tier":
            epoch_names = (self.bench or {}).get("epoch_benchmarks", list(EPOCH_BENCHMARKS))
            columns = ["mark", "lane", "model", "effort", *epoch_names, "Epoch mean rank"]
            if self.bench is not None and self.bench.get("aa_skipped") is None:
                columns.extend([*self.bench["aa_columns"], "AA mean rank"])
            active, dimmed = self._tier_names()
            rows = []
            for index, name in enumerate(active + dimmed):
                lane = self.lanes_doc["lanes"][name]
                is_dim = name in self._assigned
                marked = name in self._marks[self.tier] if not is_dim else False
                rows.append({
                    "cells": ["[x]" if marked else "[ ]", name, lane["model"], lane["effort"],
                              *self._bench_cells(lane)],
                    "marked": marked, "dimmed": is_dim,
                    "cursor": not is_dim and index == self.cursor,
                    "tag": f"tier {self._assigned[name]}" if is_dim else "",
                })
            return {"screen": "tier", "title": f"Assign tier {self.tier}", "tier": self.tier,
                    "columns": columns, "rows": rows,
                    "footer": "↑/↓ or j/k: move  space: mark  enter: next  b: back  q: quit",
                    "message": self.message}
        if self.screen == "routing":
            values = [(f"classTier.{name}", self.routing_doc["classTier"][name]) for name in CLASSES]
            values.extend([("margin", self.routing_doc["margin"]), ("gate", self.routing_doc["gate"])])
            rows = [{"cells": [name, str(value)], "marked": False, "dimmed": False,
                     "cursor": i == self.cursor, "tag": ""}
                    for i, (name, value) in enumerate(values)]
            return {"screen": "routing", "title": "Routing", "tier": None,
                    "columns": ["setting", "value"], "rows": rows,
                    "footer": "↑/↓ or j/k: move  +/-: adjust  enter: confirm  b: back  q: quit",
                    "message": self.message}
        if self.screen == "confirm":
            rows = []
            for name in self.lanes_doc["lanes"]:
                rows.append({"cells": [name, f"tier {self._assigned[name]}", ""],
                             "marked": False, "dimmed": False, "cursor": False, "tag": ""})
            for name in CLASSES:
                rows.append({"cells": [f"classTier.{name}", str(self.routing_doc["classTier"][name]), ""],
                             "marked": False, "dimmed": False, "cursor": False, "tag": ""})
            for name in ("margin", "gate"):
                rows.append({"cells": [name, str(self.routing_doc[name]), ""], "marked": False,
                             "dimmed": False, "cursor": False, "tag": ""})
            for path in (self.lanes_path, self.routing_path):
                rows.append({"cells": ["file", path, ""], "marked": False,
                             "dimmed": False, "cursor": False, "tag": ""})
            return {"screen": "confirm", "title": "Confirm changes", "tier": None,
                    "columns": ["item", "value", ""], "rows": rows,
                    "footer": "y: write  n/q: quit without writing  b: back", "message": self.message}
        return {"screen": self.screen, "title": "Delegate setup", "tier": None,
                "columns": [], "rows": [], "footer": "", "message": self.message}


def _fit_table(view, width):
    """Return visible column indices and widths, preserving decision columns."""
    columns = view["columns"]
    if not columns:
        return [], []
    priority_names = ("mark", "lane", "Epoch mean rank")
    priority = [columns.index(name) for name in priority_names if name in columns]
    order = priority + [i for i in range(len(columns)) if i not in priority]
    chosen = []
    used = 0
    for i in order:
        max_cell = max([len(columns[i])] + [len(row["cells"][i]) for row in view["rows"] if i < len(row["cells"])])
        cell_width = min(max_cell, 24)
        if chosen and used + 2 + cell_width > max(1, width - 1):
            continue
        chosen.append(i)
        used += (2 if len(chosen) > 1 else 0) + cell_width
    chosen.sort()
    widths = []
    for i in chosen:
        widths.append(min(24, max([len(columns[i])] + [len(row["cells"][i]) for row in view["rows"] if i < len(row["cells"])])))
    return chosen, widths


def run_curses(wizard):
    """Run the curses renderer until the wizard is done or quit."""
    import curses

    def app(stdscr):
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        stdscr.keypad(True)
        while wizard.screen not in ("done", "quit"):
            stdscr.erase()
            height, width = stdscr.getmaxyx()
            if width < 80 or height < 16:
                try:
                    stdscr.addnstr(0, 0, "Please enlarge the terminal window (minimum 80x16).", max(1, width - 1))
                except curses.error:
                    pass
                stdscr.refresh()
                code = stdscr.getch()
                if code == curses.KEY_RESIZE:
                    continue
                if code in (ord("q"), ord("Q")):
                    wizard.handle("q")
                continue
            view = wizard.view()
            chosen, widths = _fit_table(view, width)
            def put(y, value, attr=0):
                if y < height:
                    try:
                        stdscr.addnstr(y, 0, value, max(1, width - 1), attr)
                    except curses.error:
                        pass
            put(0, view["title"], curses.A_BOLD)
            if chosen:
                put(2, "  ".join(view["columns"][i][:w].ljust(w) for i, w in zip(chosen, widths)), curses.A_BOLD)
            max_rows = max(0, height - 7)
            for offset, row in enumerate(view["rows"][:max_rows]):
                cells = []
                for i, w in zip(chosen, widths):
                    cell = row["cells"][i] if i < len(row["cells"]) else ""
                    cells.append(cell[:w].ljust(w))
                line = "  ".join(cells)
                if row["tag"]:
                    line += "  " + row["tag"]
                attr = curses.A_DIM if row["dimmed"] else 0
                if row["cursor"]:
                    attr |= curses.A_REVERSE | curses.A_BOLD
                put(3 + offset, line, attr)
            put(height - 3, view["footer"])
            put(height - 2, view["message"], curses.A_BOLD)
            stdscr.refresh()
            code = stdscr.getch()
            mapping = {curses.KEY_UP: "up", curses.KEY_DOWN: "down",
                       ord("k"): "up", ord("j"): "down", ord(" "): "space",
                       10: "enter", 13: "enter", curses.KEY_ENTER: "enter",
                       ord("b"): "b", ord("q"): "q", ord("y"): "y", ord("n"): "n",
                       ord("+"): "plus", ord("="): "plus", ord("-"): "minus"}
            if ord("1") <= code <= ord("5"):
                key = chr(code)
            else:
                key = mapping.get(code, "other")
            wizard.handle(key)
        return wizard.result()

    return curses.wrapper(app)
