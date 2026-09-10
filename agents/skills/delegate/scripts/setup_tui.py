#!/usr/bin/env python3
"""Selectable terminal setup UI for delegate catalogs."""
import copy

from bench import EPOCH_BENCHMARKS
from catalog import CLASSES, HARNESSES

# These render as single lines in an 80-column terminal, where anything past
# column 79 is clipped. Keep each one under that; a legend cut mid-sentence
# explains nothing.
TIER_ONELINER = "Tier: capability 1-4, a ceiling — needing 3 means tier 3 or 4, never lower."
MARGIN_LEGEND = "margin: pace a lower lane must beat the pick by to steal the job (0.2 = by 0.2)"
GATE_LEGEND = "gate: meter-remaining floor; a lane below it is skipped (0.1 = under 10%)"
CLASSTIER_LEGEND = "classTier: a class needing N uses a lane of tier N or higher, never lower."


class Wizard:
    """Pure setup state.  Rendering and terminal input live in run_curses."""

    def __init__(self, lanes_doc, routing_doc, bench, discovered,
                 lanes_path, routing_path, initial_message="",
                 bench_page_path=None):
        self._original_lanes = copy.deepcopy(lanes_doc)
        self._original_routing = copy.deepcopy(routing_doc)
        self.lanes_doc = copy.deepcopy(lanes_doc)
        self.routing_doc = copy.deepcopy(routing_doc)
        self.bench = bench
        self.discovered = set(discovered)
        self.lanes_path = lanes_path
        self.routing_path = routing_path
        self.bench_page_path = bench_page_path
        self.screen = "start"
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
        if key == "o" and self.screen in ("start", "tier"):
            return
        if self.screen == "start":
            self.screen = "discovery"
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

    def _frame(self, screen, title, *, tier=None, columns=None, rows=None,
               footer="", body=None, legend=None):
        return {
            "screen": screen, "title": title, "tier": tier,
            "columns": columns or [], "rows": rows or [],
            "footer": footer, "message": self.message,
            "body": body or [], "legend": legend or [],
        }

    def _tier_map_lines(self):
        by_tier = {tier: [] for tier in range(1, 5)}
        for name, tier in self._assigned.items():
            by_tier[tier].append(name)
        lines = []
        for tier in range(1, 5):
            names = ", ".join(sorted(by_tier[tier])) or "(none)"
            lines.append(f"tier {tier}: {names}")
        return lines

    def view(self):
        if self.screen == "start":
            page = self.bench_page_path or "(not written)"
            body = [
                "You are assigning each lane a tier, from the best tier down,",
                "with benchmark numbers beside each row.",
                "Nothing is written until the confirm screen.",
                "q leaves without writing.",
                f"Will write {self.lanes_path}",
                f"Will write {self.routing_path}",
                f"Benchmark page: {page}",
                "",
                "Tier is capability, 1 to 4, and it is a ceiling:",
                "a class needing tier 3 can use a tier 3 or 4 lane and nothing lower.",
                "It is not computed; it is your judgement.",
                "Lanes alike on tier are equivalent, and ranking separates them by pace.",
            ]
            footer = ("any key: continue  o: open benchmark page  q: quit"
                      if self.bench_page_path else "any key: continue  q: quit")
            return self._frame(
                "start", "Delegate setup",
                footer=footer,
                body=body,
            )
        if self.screen == "discovery":
            return self._frame(
                "discovery", "Delegate setup: discovery",
                columns=["harness", "status"],
                rows=[{"cells": [name, "found" if name in self.discovered else "missing"],
                       "marked": False, "dimmed": name not in self.discovered,
                       "cursor": False, "tag": ""} for name in HARNESSES],
                footer="any key: continue  q: quit",
            )
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
            return self._frame(
                "tier", f"Assign tier {self.tier}", tier=self.tier,
                columns=columns, rows=rows,
                footer=(
                    "↑/↓ or j/k: move  space: mark  enter: next  b: back  "
                    "o: open benchmark page  q: quit"
                ),
                # The tier definition belongs where the decision is made, but it
                # and the key hints together overflow an 80-column footer, and a
                # truncated footer loses the keys. Last legend line renders
                # directly above the footer, so it reads as a second footer line.
                legend=[TIER_ONELINER],
            )
        if self.screen == "routing":
            values = [(f"classTier.{name}", self.routing_doc["classTier"][name]) for name in CLASSES]
            values.extend([("margin", self.routing_doc["margin"]), ("gate", self.routing_doc["gate"])])
            rows = [{"cells": [name, str(value)], "marked": False, "dimmed": False,
                     "cursor": i == self.cursor, "tag": ""}
                    for i, (name, value) in enumerate(values)]
            return self._frame(
                "routing", "Routing",
                columns=["setting", "value"], rows=rows,
                footer="↑/↓ or j/k: move  +/-: adjust  enter: confirm  b: back  q: quit",
                legend=[*self._tier_map_lines(), MARGIN_LEGEND, GATE_LEGEND],
            )
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
            return self._frame(
                "confirm", "Confirm changes",
                columns=["item", "value", ""], rows=rows,
                footer="y: write  n/q: quit without writing  b: back",
                legend=[CLASSTIER_LEGEND, MARGIN_LEGEND, GATE_LEGEND],
            )
        return self._frame(self.screen, "Delegate setup")


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
                if 0 <= y < height:
                    try:
                        stdscr.addnstr(y, 0, value, max(1, width - 1), attr)
                    except curses.error:
                        pass
            put(0, view["title"], curses.A_BOLD)
            body = view.get("body") or []
            legend = view.get("legend") or []
            footer_y = height - 3
            legend_y = footer_y - len(legend)
            y = 2
            for line in body:
                if y >= legend_y:
                    break
                put(y, line)
                y += 1
            if chosen and y < legend_y:
                if body:
                    y += 1
                if y < legend_y:
                    put(y, "  ".join(view["columns"][i][:w].ljust(w) for i, w in zip(chosen, widths)), curses.A_BOLD)
                    y += 1
                room = max(1, legend_y - y)
                cursor_index = next(
                    (i for i, row in enumerate(view["rows"]) if row["cursor"]), 0)
                first = 0
                if cursor_index >= room:
                    first = cursor_index - room + 1
                for row in view["rows"][first:]:
                    if y >= legend_y:
                        break
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
                    put(y, line, attr)
                    y += 1
            for offset, line in enumerate(legend):
                put(legend_y + offset, line)
            put(footer_y, view["footer"])
            put(height - 2, view["message"], curses.A_BOLD)
            stdscr.refresh()
            code = stdscr.getch()
            mapping = {curses.KEY_UP: "up", curses.KEY_DOWN: "down",
                       ord("k"): "up", ord("j"): "down", ord(" "): "space",
                       10: "enter", 13: "enter", curses.KEY_ENTER: "enter",
                       ord("b"): "b", ord("q"): "q", ord("y"): "y", ord("n"): "n",
                       ord("+"): "plus", ord("="): "plus", ord("-"): "minus",
                       ord("o"): "o", ord("O"): "o"}
            if ord("1") <= code <= ord("5"):
                key = chr(code)
            else:
                key = mapping.get(code, "other")
            if key == "o" and wizard.bench_page_path:
                try:
                    import pathlib
                    import webbrowser
                    webbrowser.open(pathlib.Path(wizard.bench_page_path).as_uri())
                except Exception:
                    pass
            wizard.handle(key)
        return wizard.result()

    return curses.wrapper(app)
