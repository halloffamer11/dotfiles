#!/usr/bin/env python3
"""Selectable terminal setup UI for delegate catalogs."""
import copy

from bench import EPOCH_BENCHMARKS
from catalog import CLASSES, EFFORTS, HARNESSES

# These render as single lines in an 80-column terminal, where anything past
# column 79 is clipped. Keep each one under that; a legend cut mid-sentence
# explains nothing.
TIER_ONELINER = "Tier: capability 1-4, a ceiling — needing 3 means tier 3 or 4, never lower."
PACE_LEGEND = "pace = unspent quota vs time left in the week. Above 1.0 it will expire unused."
CLASSTIER_LEGEND = "classTier: a class needing N uses a lane of tier N or higher, never lower."
TIER_FOOTER = "↑/↓/j/k: move  space: mark  x: on/off  enter: next  b: back  o: bench  q: quit"
TIER_OFF_LEGEND = "dim: assigned a higher tier.  tag off: switched off (still takes a tier)."
PRESCREEN_FOOTER = "↑/↓ or j/k: move  x: flip  enter: continue  b: back  q: quit"
PRESCREEN_LEGEND = "ultra: always off.  Dominated: same model, ≥ score at ≤ cost.  Else on."
PRESCREEN_NODATA_LEGEND = "ultra is always off.  Absence of data is not evidence against a lane."
NO_DATA_MESSAGE = "No per-effort data was supplied, so nothing else could be judged."
CONFIRM_OFF_LEGEND = "off: written with enabled: false.  On lanes omit the key."
RECORDED_REASON = "as recorded in the catalog; the pre-screen does not undo your decision"
ULTRA_REASON = (
    "unscoreable (no source reports ultra); auto-delegation breaks worker preamble"
)


def _certain_effort_rows(effort_rows):
    """Rows that may dominate. Uncertain rows inform nothing: they must not
    dominate another lane, and they are not evidence against the lane they name.

    A row at an effort no lane can select is dropped for the same reason. The
    benchmark harnesses drive the API enum, which runs `none` to `max`, so every
    published sweep carries a `none` row — and no lane can be configured at
    `none`. Letting one dominate would switch off a real lane on the strength of
    a setting that cannot be chosen, which is exactly what it did to
    luna-low@codex: equal score to `none` at a tenth of a cent more.
    """
    certain = []
    for row in effort_rows or []:
        if not isinstance(row, dict) or row.get("uncertain"):
            continue
        if not row.get("model") or not row.get("effort"):
            continue
        if row["effort"] not in EFFORTS:
            continue
        score, cost = row.get("score"), row.get("cost_usd")
        if isinstance(score, bool) or isinstance(cost, bool):
            continue
        if not isinstance(score, (int, float)) or not isinstance(cost, (int, float)):
            continue
        certain.append(row)
    return certain


def _dominating_effort(lane, certain):
    """Return another effort of the same model that weakly Pareto-dominates this
    one (score >=, cost <=, strict in at least one), else None. Compared only
    within the same source and benchmark.
    """
    model, effort = lane["model"], lane["effort"]
    mine = [r for r in certain if r.get("model") == model and r.get("effort") == effort]
    others = [r for r in certain if r.get("model") == model and r.get("effort") != effort]
    for a in mine:
        scope = (a.get("source"), a.get("benchmark"))
        for b in others:
            if (b.get("source"), b.get("benchmark")) != scope:
                continue
            if b["score"] >= a["score"] and b["cost_usd"] <= a["cost_usd"]:
                if b["score"] > a["score"] or b["cost_usd"] < a["cost_usd"]:
                    return b["effort"]
    return None


def propose_enabled(lanes_doc, effort_rows):
    """Ticket-15 pre-screen rule. Returns {name: (enabled, reason)}."""
    certain = _certain_effort_rows(effort_rows)
    supplied = bool(effort_rows)
    out = {}
    for name, lane in lanes_doc["lanes"].items():
        if lane.get("effort") == "ultra":
            out[name] = (False, ULTRA_REASON)
            continue
        if "enabled" in lane:
            # An explicit `enabled` is a decision the human already recorded. The
            # pre-screen proposes for lanes that have no decision yet; it does not
            # undo one. Silently switching a lane back on would put it in front of
            # the ranker again without anyone saying so.
            out[name] = (bool(lane["enabled"]), RECORDED_REASON)
            continue
        other = _dominating_effort(lane, certain)
        if other is not None:
            out[name] = (False, f"dominated by {other} of the same model")
            continue
        if not supplied:
            out[name] = (True, "no per-effort data; absence is not evidence against")
        elif not any(
            isinstance(row, dict)
            and not row.get("uncertain")
            and row.get("model") == lane["model"]
            and row.get("effort") == lane["effort"]
            for row in effort_rows
        ):
            out[name] = (True, "no rows for this lane; absence is not evidence against")
        else:
            out[name] = (True, "not dominated")
    return out


# The run in order, for the marker on every screen. Tier is four screens, counted
# down from the best, so they are listed individually rather than as one step.
STEPS = (
    ("start", "start"),
    ("discovery", "harnesses"),
    ("prescreen", "carry"),
    ("tier4", "T4"),
    ("tier3", "T3"),
    ("tier2", "T2"),
    ("tier1", "T1"),
    ("routing", "routing"),
    ("confirm", "confirm"),
)


class Wizard:
    """Pure setup state.  Rendering and terminal input live in run_curses."""

    def __init__(self, lanes_doc, routing_doc, bench, discovered,
                 lanes_path, routing_path, initial_message="",
                 bench_page_path=None, effort_rows=None, discovery=None):
        self._original_lanes = copy.deepcopy(lanes_doc)
        self._original_routing = copy.deepcopy(routing_doc)
        self.lanes_doc = copy.deepcopy(lanes_doc)
        self.routing_doc = copy.deepcopy(routing_doc)
        self.bench = bench
        self.effort_rows = effort_rows
        self.discovered = set(discovered)
        self.discovery = discovery
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
        proposals = propose_enabled(self.lanes_doc, effort_rows)
        self._enabled = {name: enabled for name, (enabled, _) in proposals.items()}
        self._reasons = {name: reason for name, (_, reason) in proposals.items()}

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

    def _enter_prescreen(self):
        self.screen = "prescreen"
        self.tier = None
        self.cursor = 0
        self.message = "" if self.effort_rows else NO_DATA_MESSAGE

    def _lane_names(self):
        return list(self.lanes_doc["lanes"])

    def _toggle_enabled(self, name):
        if name:
            self._enabled[name] = not self._enabled[name]

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
        if key == "o" and self.screen in ("start", "tier", "prescreen"):
            return
        if self.screen == "start":
            self.screen = "discovery"
            return
        if self.screen == "discovery":
            # every other screen with a predecessor has `b`; this one advanced on
            # any key, so `b` moved forward, which is the one thing it must not do
            if key == "b":
                self.screen = "start"
                self.cursor = 0
                self.message = ""
            else:
                self._enter_prescreen()
            return
        if self.screen == "prescreen":
            names = self._lane_names()
            if key == "up" and names:
                self.cursor = (self.cursor - 1) % len(names)
            elif key == "down" and names:
                self.cursor = (self.cursor + 1) % len(names)
            elif key == "x" and names:
                self._toggle_enabled(names[min(self.cursor, len(names) - 1)])
            elif key == "enter":
                self._enter_tier(4)
            elif key == "b":
                self.screen = "discovery"
                self.cursor = 0
                self.message = ""
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
            elif key == "x":
                self._toggle_enabled(self._active_name())
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
            elif key == "b" and self.tier == 4:
                self._enter_prescreen()
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
                    if not self._enabled[name]:
                        lane["enabled"] = False
                    else:
                        lane.pop("enabled", None)
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
            "steps": self._step_marker(),
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

    @staticmethod
    def _fit(line):
        """One width rule for every start-screen line: the renderer clips at 79."""
        return line if len(line) <= 79 else line[:76] + "..."

    def _drift_line(self, label, items):
        """`label (n): a, b (+k more)`, filled to the width and no further."""
        total = len(items)
        if total == 1:
            return self._fit(f"{label}: {items[0]}")
        prefix = f"{label} ({total}): "
        chosen = []
        for index, item in enumerate(items):
            remaining = total - (index + 1)
            suffix = f" (+{remaining} more)" if remaining else ""
            if len(prefix + ", ".join(chosen + [item]) + suffix) > 79 and chosen:
                break
            chosen.append(item)
        remaining = total - len(chosen)
        suffix = f" (+{remaining} more)" if remaining else ""
        return self._fit(prefix + ", ".join(chosen) + suffix)

    def _margin_legend(self):
        value = self.routing_doc["margin"]
        return [
            f"margin {value} — a lane further down the order takes the job instead of",
            f"  the top pick only when its pace beats the pick's by more than {value}.",
        ]

    def _gate_legend(self):
        value = self.routing_doc["gate"]
        percent = f"{value * 100:g}%"
        return [
            f"gate {value} — a lane is skipped outright once its meter drops below",
            f"  {percent} remaining, however capable it is.",
        ]

    def _step_marker(self):
        """`start · harnesses · carry · T4 · [T3] · T2 · T1 · routing · confirm`.

        The bracketed step is the current one. Returns "" on the terminal screens,
        which have no step to be at.
        """
        if self.screen in ("done", "quit"):
            return ""
        here = f"tier{self.tier}" if self.screen == "tier" else self.screen
        parts = [f"[{label}]" if key == here else label for key, label in STEPS]
        return " · ".join(parts)

    def _discovery_notices(self):
        """Drift notices for the start screen.

        `discovery` is either the dict `discover.discover` returns or a string
        saying why it did not run. Discovery shells out to three harness CLIs, so
        it must never be able to stop the wizard: a notice is an aid, not a gate.
        A silent absence and a failed probe must not look the same, so the
        no-drift case says so in a line of its own.
        """
        if self.discovery is None:
            return [self._fit("Model discovery: did not run")]
        if isinstance(self.discovery, str):
            return [self._fit(f"Model discovery: did not run: {self.discovery}")]

        unmapped = self.discovery.get("unmapped") or []
        retired = self.discovery.get("retired") or []
        if not unmapped and not retired:
            return [self._fit("Model discovery: no drift")]

        notices = []
        if unmapped:
            notices.append(self._drift_line("Models with no lane", [
                f"{m.get('harness', '')} {m.get('slug', '')}".strip() for m in unmapped
            ]))
        if retired:
            notices.append(self._drift_line("Lanes with retired models", [
                f"{r.get('lane', '')} ({r.get('model', '')})" for r in retired
            ]))
        return notices

    def view(self):
        if self.screen == "start":
            page = self.bench_page_path or "(not written)"
            body = [
                "Assign each lane a tier, best tier down, benchmark numbers beside it.",
                "Nothing is written until the confirm screen; q leaves without writing.",
                self._fit(f"Will write {self.lanes_path}"),
                self._fit(f"Will write {self.routing_path}"),
                self._fit(f"Benchmark page: {page}"),
                *self._discovery_notices(),
                "",
                "Tier is capability, 1 to 4, and it is a ceiling: a class needing tier 3",
                "can use a tier 3 or 4 lane and nothing lower. It is not computed; it is",
                "your judgement. Lanes alike on tier are equivalent; pace separates them.",
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
                footer="any key: continue  b: back  q: quit",
            )
        if self.screen == "prescreen":
            names = self._lane_names()
            rows = []
            for index, name in enumerate(names):
                lane = self.lanes_doc["lanes"][name]
                on = self._enabled[name]
                rows.append({
                    "cells": [
                        "[x]" if on else "[ ]", name, lane["model"], lane["effort"],
                        "on" if on else "off", self._reasons[name],
                    ],
                    "marked": on, "dimmed": not on,
                    "cursor": index == self.cursor,
                    "tag": "" if on else "off",
                })
            legend = [PRESCREEN_LEGEND]
            if not self.effort_rows:
                legend = [PRESCREEN_NODATA_LEGEND, NO_DATA_MESSAGE]
            return self._frame(
                "prescreen", "Lanes to carry",
                columns=["mark", "lane", "model", "effort", "carry", "reason"],
                rows=rows,
                footer=PRESCREEN_FOOTER,
                legend=legend,
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
                is_assigned = name in self._assigned
                is_off = not self._enabled[name]
                marked = name in self._marks[self.tier] if not is_assigned else False
                if is_off and is_assigned:
                    tag = f"off, tier {self._assigned[name]}"
                elif is_off:
                    tag = "off"
                elif is_assigned:
                    tag = f"tier {self._assigned[name]}"
                else:
                    tag = ""
                rows.append({
                    "cells": ["[x]" if marked else "[ ]", name, lane["model"], lane["effort"],
                              *self._bench_cells(lane)],
                    "marked": marked, "dimmed": is_assigned or is_off,
                    "cursor": not is_assigned and index == self.cursor,
                    "tag": tag,
                })
            return self._frame(
                "tier", f"Assign tier {self.tier}", tier=self.tier,
                columns=columns, rows=rows,
                footer=TIER_FOOTER,
                # The tier definition belongs where the decision is made, but it
                # and the key hints together overflow an 80-column footer, and a
                # truncated footer loses the keys. Last legend line renders
                # directly above the footer, so it reads as a second footer line.
                legend=[TIER_OFF_LEGEND, TIER_ONELINER],
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
                # margin and gate first: they explain the values being edited on
                # this screen, so they are what must survive a short window. The
                # tier map is reference and gives way before they do.
                legend=[*self._margin_legend(), *self._gate_legend(),
                        PACE_LEGEND, *self._tier_map_lines()],
            )
        if self.screen == "confirm":
            rows = []
            for name in self.lanes_doc["lanes"]:
                off = not self._enabled[name]
                rows.append({"cells": [name, f"tier {self._assigned[name]}",
                                       "off" if off else ""],
                             "marked": False, "dimmed": off, "cursor": False,
                             "tag": "off" if off else ""})
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
                legend=[CLASSTIER_LEGEND, *self._margin_legend(),
                        *self._gate_legend(), CONFIRM_OFF_LEGEND],
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
            steps = view.get("steps") or ""
            steps_y = footer_y - 1 if steps else footer_y
            # The table is the thing you act on, so it keeps its room and the
            # legend gives way. The clear margin and gate wording runs to nine
            # lines on the routing screen, which at 80x16 left the table none.
            table_floor = 2 + (1 if view["columns"] else 0) + min(len(view["rows"]), 4)
            if legend and steps_y - len(legend) < table_floor:
                keep = max(0, steps_y - table_floor)
                if keep < len(legend):
                    legend = legend[:keep]
                    if keep:
                        legend[-1] = "… enlarge the window for the rest"
            legend_y = steps_y - len(legend)
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
            if steps:
                put(steps_y, steps, curses.A_BOLD)
            put(footer_y, view["footer"])
            put(height - 2, view["message"], curses.A_BOLD)
            stdscr.refresh()
            code = stdscr.getch()
            mapping = {curses.KEY_UP: "up", curses.KEY_DOWN: "down",
                       ord("k"): "up", ord("j"): "down", ord(" "): "space",
                       10: "enter", 13: "enter", curses.KEY_ENTER: "enter",
                       ord("b"): "b", ord("q"): "q", ord("y"): "y", ord("n"): "n",
                       ord("+"): "plus", ord("="): "plus", ord("-"): "minus",
                       ord("o"): "o", ord("O"): "o",
                       ord("x"): "x", ord("X"): "x"}
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
