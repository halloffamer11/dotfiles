#!/usr/bin/env python3
"""Selectable terminal setup UI for delegate catalogs."""
import copy
import os
import subprocess
import textwrap
import time

import bench_page
from bench import (
    EPOCH_BENCHMARKS,
    KIND_DOMINATED,
    KIND_NO_ROWS,
    KIND_NOT_DOMINATED,
    KIND_RECORDED,
    KIND_UNAVAILABLE,
    KIND_ULTRA,
    NO_DATA_REASON,
    NO_ROWS_REASON,
    NOT_DOMINATED_REASON,
    ULTRA_REASON,
    bench_order_key,
    carry_reason,
    certain_effort_rows,
    dominated_reason,
    dominating_effort,
    dominating_row,
    effort_rank,
    fmt_aa_value,
    fmt_cost,
    group_lanes,
    is_dominated_reason,
    lane_order,
    model_families,
    model_group,
    propose_enabled,
    recorded_reason,
    resolve_effort_rows,
    unmatched_message,
)
from catalog import (
    CLASSES,
    HARNESSES,
    TIER_LINE_VALUES,
    apply_tier_lines_to_doc,
    meter_dependency_lines,
    meters_enabled,
    parse_tier_lines,
    tier_lines_summary,
    unnamed_carried,
    write_order_from_lines,
)
from catalog import default_class_guide_path as catalog_guide_path

# These render as single lines in an 80-column terminal, where anything past
# column 79 is clipped. Keep each one under that; a legend cut mid-sentence
# explains nothing.
TIER_ONELINER = "Tier: capability 1-4; a class takes lanes from its floor up to its ceiling."
# One gesture flips the box, and it is the same gesture on the carry screen and
# on the tier screens, so each footer names it the same way. The box means
# something different on each screen — the column header says which — but the
# key that moves it never changes.
FLIP_KEYS = "space/x: flip"
TIER_FOOTER = f"↑/↓/j/k: move  {FLIP_KEYS}  enter: next  b: back  o: bench  q: quit"
# The review page orders lanes inside each tier (ticket 28). Its footer is 79
# places, the most an 80-column line shows; the key help under the table
# spells the keys out, apart from the explanation and the warning.
REVIEW_FOOTER = "j/k: cursor  J/K: move lane  1-4: tier  v: paste  enter: next  b: back  q: quit"
REVIEW_ORDER_LEGEND = "Ranking tries 1 first; a lane lower down runs if its pace beats 1's by margin."
ROUTING_FOOTER = "j/k: move  +/-: adjust  space/x: meters  enter: confirm  b: back  q: quit"
PRESCREEN_FOOTER = f"↑/↓ or j/k: move  {FLIP_KEYS}  enter: continue  b: back  q: quit"
DISCOVERY_FOOTER = "any key: continue  b: back  q: quit"
DISCOVERY_RESCAN_FOOTER = "any key: continue  r: rescan  b: back  q: quit"
NO_DATA_MESSAGE = "No per-effort data was supplied, so nothing else could be judged."


def definition(term, text, value="", style="term"):
    """One entry of a definition list under a table: the term, its value if it
    has one, and what it means. `style` is the term's, so a term that names a
    colour in the table above can be drawn in that colour and read as a key.
    `layout_lines` aligns the entries of one page in two columns."""
    return {"term": term, "value": value, "text": text, "style": style}


# A reason has to fit the `why` column, and the column has to fit beside the
# lane, the model and the effort in 80 places. So each reason is a phrase that
# is whole at about twenty characters, and the sentence it stands for is a
# definition that appears only on the screens where that phrase appears. A
# reason cut mid-word explains no more than a definition cut mid-sentence does,
# so each text is under 63 places: the longest term, two spaces, then the text.
DOMINATED_DEF = definition("X wins on S", "effort X scores ≥ at ≤ cost on most of source S's benchmarks",
                           style="why-data")
NOT_DOMINATED_DEF = definition("not dominated", "no other effort of the model wins over it, so it stays on")
ABSENCE_DEF = definition("no rows", "absence of data is not evidence against a lane; it stays on")
RECORDED_DEF = definition("in the catalog", "you recorded that already; the pre-screen leaves it")
ULTRA_DEF = definition("ultra", "no source scores it; auto-delegation breaks the worker preamble")
# The review page's keys, spelled out: J/K is the footer's, shift-↑/↓ is not.
REVIEW_MOVE_DEFS = (
    definition("J/K, shift-↑/↓", "move the lane inside its tier", style="key"),
    definition("1-4", "move it to the end of that tier", style="key"),
)
CLASSES_DEF = definition("classes", "each class has a floor and a ceiling tier, 1 to 4")
CONFIRM_OFF_DEF = definition("off", "written with enabled: false; on lanes omit the key")
# The harness page counts claude's models, but Claude Code lists none: the
# count is the catalog's own (`discover.discover`).
CLAUDE_COUNT_LEGEND = "claude lists no model; its count is the catalog's own"


def class_descriptions(path=None):
    """{class: its first sentence} from the Class guide, `assets/classes.md`,
    for the routing page's group rows. The guide is the one place a class is
    described, so nothing here paraphrases it: the sentence is quoted, less its
    full stop. A guide that cannot be read gives every class "" and the page
    still draws; the guide is an aid to the routing page, not a gate."""
    try:
        with open(path or catalog_guide_path(), "r", encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError):
        return {name: "" for name in CLASSES}
    out = {name: "" for name in CLASSES}
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            current = line[3:].strip()
            continue
        if current in out and line and not out[current]:
            head = line.split(". ", 1)[0]
            out[current] = head[:-1] if head.endswith(".") else head
    return out


def hidden_legend(taken, off):
    """One line naming what a tier page left out, or "" when it left out nothing.

    A tier page lists only the lanes still open to it (ticket 25). A lane that
    vanished with no word would read as a lane lost, so the page counts them.
    """
    parts = []
    if taken:
        parts.append(f"{taken} taken at a higher tier")
    if off:
        parts.append(f"{off} not carried")
    return f"Not listed: {', '.join(parts)}." if parts else ""


# --- tier lines: catalog owns the parser; these names stay for callers ------


class ClipboardError(Exception):
    """The clipboard could not be read; the wizard says so and changes nothing."""


def read_clipboard():
    """The macOS clipboard as text, through `pbpaste`. Called only on `v`."""
    try:
        result = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5, check=False)
    except FileNotFoundError as e:
        raise ClipboardError("pbpaste not found") from e
    except (OSError, subprocess.SubprocessError) as e:
        raise ClipboardError(f"pbpaste failed: {e}") from e
    if result.returncode != 0:
        raise ClipboardError(f"pbpaste failed (exit {result.returncode})")
    return result.stdout


def fit_line(line, width=80):
    """One width rule for a line of prose: the renderer clips at width - 1."""
    room = max(4, width - 1)
    return line if len(line) <= room else line[: room - 3] + "..."


def list_line(label, items, width=80, always_count=False):
    """`label (n): a, b (+k more)`, filled to the width and no further.

    `always_count` keeps the count on a list of one, for a block of lines
    read together — the tier map — where a line without it reads as a
    different kind of line.
    """
    room = max(4, width - 1)
    total = len(items)
    if total == 1 and not always_count:
        return fit_line(f"{label}: {items[0]}", width)
    prefix = f"{label} ({total}): "
    chosen = []
    for index, item in enumerate(items):
        remaining = total - (index + 1)
        suffix = f" (+{remaining} more)" if remaining else ""
        if len(prefix + ", ".join(chosen + [item]) + suffix) > room and chosen:
            break
        chosen.append(item)
    remaining = total - len(chosen)
    suffix = f" (+{remaining} more)" if remaining else ""
    return fit_line(prefix + ", ".join(chosen) + suffix, width)


def discovery_notices(discovery, width=80):
    """Drift notices for the start page and for `--plain`.

    `discovery` is either the dict `discover.discover` returns or a string
    saying why it did not run. Discovery shells out to three harness CLIs, so
    it must never be able to stop the wizard: a notice is an aid, not a gate.
    A silent absence and a failed probe must not look the same, so the
    no-drift case says so in a line of its own.
    """
    if discovery is None:
        return [fit_line("Model discovery: did not run", width)]
    if isinstance(discovery, str):
        return [fit_line(f"Model discovery: did not run: {discovery}", width)]
    if not isinstance(discovery, dict):
        return [fit_line("Model discovery: did not run", width)]
    if discovery.get("error") and "harnesses" not in discovery:
        return [fit_line(f"Model discovery: did not run: {discovery['error']}", width)]
    notices = []
    if discovery.get("model_facts_available") is False:
        notices.append(fit_line("Model discovery: saved Harness facts only; model facts unavailable", width))
    for name, info in (discovery.get("harnesses") or {}).items():
        if not isinstance(info, dict):
            continue
        status = info.get("status")
        if status == "missing":
            notices.append(fit_line(f"Harness {name}: missing", width))
        elif status == "error":
            err = info.get("error") or "unknown error"
            notices.append(fit_line(f"Harness {name}: error: {err}", width))
    unmapped = discovery.get("unmapped") or []
    retired = discovery.get("retired") or []
    if unmapped:
        notices.append(list_line("Models with no lane", [
            f"{m.get('harness', '')} {m.get('slug', '')}".strip() for m in unmapped
        ], width))
    if retired:
        notices.append(list_line("Lanes with retired models", [
            f"{r.get('lane', '')} ({r.get('model', '')})" for r in retired
        ], width))
    if not notices:
        return [fit_line("Model discovery: no drift", width)]
    return notices


def plural(count, word):
    """`1 Lane`, `6 Lanes`."""
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def refresh_lines(refresh, width=80):
    """What the catalog refresh proposes, one line per model (ticket 33).

    A model that takes another's place reads
    `gpt-5.6-sol → gpt-6-sol: sol6-*@codex replace sol-*@codex (6 Lanes)`, and
    one that takes nobody's reads `new gemini-3.1-pro: pro31-*@agy (2 Lanes)`.
    A refresh that did not run says so rather than reading as no change.
    """
    if refresh is None:
        return []
    lines = []
    for item in refresh.get("models") or []:
        family = f"{item['stem']}-*@{item['harness']}"
        count = plural(len(item["new"]), "Lane")
        if item.get("predecessor"):
            replaced = len(set(item["replaced"]))
            tail = count if replaced == len(item["new"]) else f"{count} for {replaced}"
            lines.append(fit_line(
                f"{item['predecessor']} → {item['model']}: {family} replace "
                f"{item['predecessor_stem']}-*@{item['harness']} ({tail})", width))
        else:
            lines.append(fit_line(f"new {item['model']}: {family} ({count})", width))
    # a superseded lane with no successor at its effort leaves with no line of
    # its own above, so it is named here
    covered = {name for item in refresh.get("models") or [] for name in item["replaced"]}
    orphans = [name for name in refresh.get("removed") or [] if name not in covered]
    if orphans:
        lines.append(list_line("Superseded Lanes removed", orphans, width))
    if not lines:
        return [fit_line("Catalog refresh: every model is the current generation", width)]
    return lines


def start_facts(lanes_path, routing_path, page_path, discovery, width=80,
                refresh=None, rows_note=""):
    """What the start page says, and what `--plain` prints first: the two files
    it will write, the benchmark page, where the benchmark rows came from, what
    the refresh proposes, and the discovery notices. Facts only — the terms are
    defined in CONTEXT.md, and the people who run this know them (Orin,
    2026-09-11; tickets 25 and 33)."""
    return [
        fit_line(f"Will write {lanes_path}", width),
        fit_line(f"Will write {routing_path}", width),
        fit_line(f"Benchmark page: {page_path or '(not written)'}", width),
        *([fit_line(rows_note, width)] if rows_note else []),
        *refresh_lines(refresh, width),
        *discovery_notices(discovery, width),
    ]


# The run in order, for the trail on the top row of every screen. Tier is four
# screens, counted down from the best, so they are listed individually rather
# than as one step.
STEPS = (
    ("start", "start"),
    ("discovery", "harnesses"),
    ("prescreen", "carry"),
    ("tier4", "T4"),
    ("tier3", "T3"),
    ("tier2", "T2"),
    ("tier1", "T1"),
    ("review", "review"),
    ("routing", "routing"),
    ("confirm", "confirm"),
)


class Wizard:
    """Pure setup state.  Rendering and terminal input live in run_curses."""

    def __init__(self, lanes_doc, routing_doc, bench, discovered,
                 lanes_path, routing_path, initial_message="",
                 bench_page_path=None, effort_rows=None, discovery=None, clipboard=None,
                 focus=None, refresh=None, rows_note="", rescan=None, tier_lines=None,
                 clock=None, class_guide=None):
        # read only when `v` is pressed on the review page (ticket 27)
        self._clipboard = clipboard or read_clipboard
        self._original_routing = copy.deepcopy(routing_doc)
        self.routing_doc = copy.deepcopy(routing_doc)
        self.lanes_path = lanes_path
        self.routing_path = routing_path
        self.bench_page_path = bench_page_path
        # `r` on the harnesses page runs the launch scrub again through this,
        # and gets back what `_load` takes; None is a wizard that cannot
        self._rescan = rescan
        # the `--tiers-from` lines, applied again after a rescan as at launch
        self.tier_lines = tier_lines
        self._clock = clock or (lambda: time.strftime("%H:%M"))
        self.scanned = "at launch"
        # the routing page's class descriptions, from the Class guide
        self.class_guide = class_descriptions() if class_guide is None else class_guide
        self.focus = None if focus in (None, "start") else focus
        self.screen = "start"
        self.tier = None
        self._result = None
        self._width = 80
        self._load(lanes_doc, bench, discovered, effort_rows, discovery, refresh, rows_note)
        self.message = initial_message or ("benchmark data unavailable" if bench is None else "")
        if self.focus:
            self._enter_focus()

    def _load(self, lanes_doc, bench, discovered, effort_rows, discovery, refresh, rows_note):
        """Start from what one scrub found: the catalog with the current
        generation proposed, the benchmark data, the harnesses and their
        models. Every decision the pages after the harnesses page hold is
        derived here, so a rescan starts them over consistently."""
        self._original_lanes = copy.deepcopy(lanes_doc)
        self.lanes_doc = copy.deepcopy(lanes_doc)
        self.bench = bench
        self.effort_rows = effort_rows
        self.discovered = set(discovered)
        self.discovery = discovery
        # what the refresh proposed before the first screen, and where the
        # benchmark rows came from; both are start-page facts (ticket 33)
        self.refresh = refresh
        self.rows_note = rows_note
        self.cursor = 0
        self.message = ""
        self._review_order = []
        # Orin's order inside each tier, as the review page shows it (ticket 28),
        # and each lane's place in the last lines applied, which starts it
        self._tier_order = {tier: [] for tier in range(1, 5)}
        self._line_order = {}
        _rows, self._unmatched = resolve_effort_rows(self.lanes_doc, effort_rows)
        self._proposals = propose_enabled(self.lanes_doc, effort_rows)
        self._reasons = {name: carry_reason(decision) for name, decision in self._proposals.items()}
        # A focused screen starts from the catalog as it stands and never
        # applies carry proposals the operator has not seen.
        if self.focus:
            self._enabled = {
                name: lane.get("enabled", True)
                for name, lane in self.lanes_doc["lanes"].items()
            }
        else:
            self._enabled = {name: decision["enabled"] for name, decision in self._proposals.items()}
        # The catalog is the starting state of a rerun. A lane that the carry
        # page proposes off keeps its tier here, so switching it back on restores
        # the catalog default instead of making the operator place it from
        # scratch.
        self._assigned = {
            name: lane["tier"] for name, lane in self.lanes_doc["lanes"].items()
        }
        self._marks = {
            tier: {
                name for name, assigned in self._assigned.items()
                if assigned == tier and self._enabled[name]
            }
            for tier in range(1, 5)
        }

    def rescan_ready(self):
        """Whether `r` scrubs again here: on the harnesses page, with a scrub
        to run. The page comes before every carry and Tier decision, so a
        rescan throws none away; nowhere later offers it."""
        return self.screen == "discovery" and self._rescan is not None

    def rescan(self):
        """`r` on the harnesses page: the launch scrub again — the harnesses'
        models, the benchmark rows fetched afresh, the current generation
        proposed — and every later page starts over from what it found, with
        the `--tiers-from` lines applied again. A scrub that fails is a
        message and changes nothing; nothing here writes a file."""
        if not self.rescan_ready():
            return
        try:
            found = self._rescan()
        except Exception as e:  # the scrub shells out and fetches; any failure is one message
            self.message = f"rescan failed: {e}"
            return
        self._load(found["lanes_doc"], found.get("bench"), found.get("discovered") or (),
                   found.get("effort_rows"), found.get("discovery"), found.get("refresh"),
                   found.get("rows_note") or "")
        self.scanned = f"at {self._clock()}"
        refresh = self.refresh or {}
        message = (f"Rescanned {self.scanned}: {plural(len(refresh.get('new') or ()), 'new Lane')}, "
                   f"{len(refresh.get('removed') or ())} removed")
        if found.get("message"):
            message = f"{message}; {found['message']}"
        if self.tier_lines is not None:
            message = f"{message}; {self.apply_tier_lines(self.tier_lines)}"
        self.message = message

    def result(self):
        return self._result

    def _mean(self, lane_name):
        """This lane's mean rank over its own figures, never its model's.

        A model's figures are spread over the efforts a source measured, and
        only the ones measured at this lane's effort say anything about this
        lane (ticket 17).
        """
        if self.bench is None:
            return None
        rec = self.bench.get("lanes", {}).get(lane_name)
        return rec["mean"] if rec else None

    def _bench_order(self, name):
        return bench_order_key(self.bench, name, self.lanes_doc)

    def _carried(self):
        return [name for name in self.lanes_doc["lanes"] if self._enabled[name]]

    def current_lanes(self):
        """The catalog as this session holds it: the document it started from,
        with the carry and Tier decisions made so far. Not a save — the confirm
        screen's `y` is the save."""
        doc = copy.deepcopy(self._original_lanes)
        for name, lane in doc["lanes"].items():
            lane["tier"] = self._final_tier(name)
            if self._enabled[name]:
                lane.pop("enabled", None)
            else:
                lane["enabled"] = False
        return doc

    def rewrite_bench_page(self):
        """Write the benchmark page again from the catalog as it stands, and
        return "" or a message saying why it could not be.

        `o` used to reopen the file written at start, so a lane carried on the
        carry page reached the page only on the next run (ticket 35). The page's
        catalog key is its lane names, which no screen here changes, so the
        tiers already drawn in the browser survive the rewrite.
        """
        if not self.bench_page_path:
            return ""
        try:
            bench_page.write(self.bench_page_path, self.bench, self.current_lanes(),
                             self.effort_rows)
        except (OSError, ValueError) as e:
            return f"benchmark page: {e}"
        return ""

    def _tier_names(self):
        """The lanes open on this tier page: carried, and not placed higher.

        Current assignments at this tier stay visible and marked. Assignments
        below it stay visible and unmarked, so a rerun can move a lane up.
        A lane placed higher is hidden, not dimmed (ticket 25): a grey row that
        space still toggled was a decision offered twice.
        Benchmark order places each model's group; inside it the efforts run
        from most to least (ticket 26)."""
        active = [
            name for name in self._carried()
            if name not in self._assigned or self._assigned[name] <= self.tier
        ]
        active.sort(key=self._bench_order)
        return group_lanes(active, self.lanes_doc)

    def _meter_coverage(self):
        """The lanes as this session holds them, for the one-Meter warning.

        Carry and Tier come from the wizard, not from the catalog on disk, so
        the review page warns about the Tiers Orin is about to write rather
        than the ones he started from (ticket 29).
        """
        return {
            name: {
                "enabled": self._enabled[name],
                "tier": self._final_tier(name),
                "meter": lane.get("meter"),
            }
            for name, lane in self.lanes_doc["lanes"].items()
        }

    def _final_tier(self, name):
        """The tier written for a lane. A lane not carried is never asked about,
        so it keeps the tier the catalog already has."""
        if self._enabled[name] and name in self._assigned:
            return self._assigned[name]
        return self._original_lanes["lanes"][name]["tier"]

    def _enter_tier(self, tier):
        self.screen = "tier"
        self.tier = tier
        self.cursor = 0
        self.message = ""
        active = self._tier_names()
        if tier == 1:
            # Whatever is still open must take tier 1, including a lane removed
            # from a higher tier during this run.
            self._marks[1].update(active)

    def _enter_review(self):
        self.screen = "review"
        self.tier = None
        self.cursor = 0
        self.message = ""
        self._arrange_review()

    def _go_confirm(self):
        self.screen = "confirm"
        self.cursor = 0
        self.message = ""

    def _enter_focus(self):
        """Open the named focused screen on current catalog decisions."""
        if self.focus == "carry":
            self._enter_prescreen()
        elif self.focus in ("tier1", "tier2", "tier3", "tier4"):
            self._enter_tier(int(self.focus[-1]))
        elif self.focus == "review":
            self._enter_review()
        elif self.focus == "routing":
            self.screen = "routing"
            self.tier = None
            self.cursor = 0
            self.message = ""

    def _back_from_confirm(self):
        if self.focus == "carry":
            self._enter_prescreen()
        elif self.focus in ("tier1", "tier2", "tier3", "tier4"):
            self._enter_tier(int(self.focus[-1]))
        elif self.focus == "review":
            self._enter_review()
        else:
            self.screen = "routing"
            self.cursor = 0

    def _start_key(self, name):
        """Where a lane first sits in its tier: the order of the lines applied,
        then an `order` the catalog already gives it at this tier, then
        benchmark order. The model grouping of ticket 26 does not apply here:
        the order is Orin's (ticket 28)."""
        line = self._line_order.get(name)
        original = self._original_lanes["lanes"][name]
        kept = original.get("order") if original.get("tier") == self._assigned.get(name) else None
        moved = self.focus and original["tier"] != self._assigned.get(name)
        return (bool(moved), line is None, line or 0, kept is None, kept or 0, *self._bench_order(name))

    def _arrange_review(self):
        """Each tier's order, 4 to 1. A lane already ordered in its tier keeps
        its place, so back and forth through routing loses no J/K move; a lane
        new to the tier joins after them at its starting place."""
        for tier in range(1, 5):
            members = [name for name in self._carried() if self._assigned.get(name) == tier]
            kept = [name for name in self._tier_order[tier] if name in members]
            fresh = sorted((name for name in members if name not in kept), key=self._start_key)
            self._tier_order[tier] = kept + fresh
        self._flatten_review()

    def _flatten_review(self):
        self._review_order = [name for tier in (4, 3, 2, 1) for name in self._tier_order[tier]]

    def _review_cursor_name(self):
        names = self._review_order
        return names[min(self.cursor, len(names) - 1)] if names else None

    def _move_in_tier(self, step):
        """J/K: swap the lane under the cursor with its neighbour inside its
        tier; at the top or bottom of the tier nothing moves. The cursor stays
        on the lane."""
        name = self._review_cursor_name()
        order = self._tier_order[self._assigned[name]]
        here = order.index(name)
        there = here + step
        if 0 <= there < len(order):
            order[here], order[there] = order[there], order[here]
            self._flatten_review()
            self.cursor = self._review_order.index(name)

    def _move_to_tier(self, tier):
        """1-4: the lane under the cursor goes to the end of that tier, its own
        tier included, and the cursor goes with it."""
        name = self._review_cursor_name()
        self._tier_order[self._assigned[name]].remove(name)
        self._assigned[name] = tier
        for marks in self._marks.values():
            marks.discard(name)
        self._marks[tier].add(name)
        self._tier_order[tier].append(name)
        self._flatten_review()
        self.cursor = self._review_order.index(name)

    def _place(self, name):
        """A carried lane's place inside its tier from 1, or None if unplaced."""
        order = self._tier_order.get(self._assigned.get(name), [])
        return order.index(name) + 1 if name in order else None

    def apply_tier_lines(self, text):
        """Apply `<lane> <1-4|off>` lines and say what they did, on one line.

        A tier line carries the lane and gives it that tier; an off line sets it
        not carried; a carried lane with no line goes off (ticket 28). The
        lines' order inside a tier is the review page's starting order. On the
        review page the order is taken again, and the cursor stays on the lane
        it was on when that lane is still listed. Returns the summary line."""
        parsed = parse_tier_lines(text, self.lanes_doc)
        dropped = unnamed_carried(parsed, self._carried())
        for name in dropped:
            self._enabled[name] = False
            self._assigned.pop(name, None)
        for name, value in parsed["decided"].items():
            if value == "off":
                self._enabled[name] = False
                self._assigned.pop(name, None)
            else:
                self._enabled[name] = True
                self._assigned[name] = value
        if parsed["decided"]:
            self._marks = {
                tier: {
                    name for name, assigned in self._assigned.items()
                    if assigned == tier and self._enabled[name]
                }
                for tier in range(1, 5)
            }
            self._line_order = {name: index for index, name in enumerate(parsed["decided"])}
            self._tier_order = {tier: [] for tier in range(1, 5)}
        summary = tier_lines_summary(parsed, dropped)
        if self.screen == "review":
            order = self._review_order
            here = order[min(self.cursor, len(order) - 1)] if order else None
            self._enter_review()
            if here in self._review_order:
                self.cursor = self._review_order.index(here)
        self.message = summary
        return summary

    def _paste_tier_lines(self):
        """`v` on the review page: the clipboard's lines, or a message saying
        why nothing changed."""
        try:
            text = self._clipboard()
        except ClipboardError as e:
            self.message = f"v: {e}; nothing changed"
            return
        if not (text or "").strip():
            self.message = "v: the clipboard holds no lines; nothing changed"
            return
        self.apply_tier_lines(text)

    def _enter_prescreen(self):
        self.screen = "prescreen"
        self.tier = None
        self.cursor = 0
        # The models no lane runs are a note about the data, so they read as a
        # legend line. The message slot is bold and sits below the footer, where
        # `every lane needs a tier` goes: a standing note there reads as an
        # error the human has just caused.
        self.message = "" if self.effort_rows else NO_DATA_MESSAGE

    def _lane_names(self):
        """The carry page's lanes: the catalog's order places each model's
        group, and its efforts run from most to least (ticket 26)."""
        return group_lanes(list(self.lanes_doc["lanes"]), self.lanes_doc)

    def _toggle_enabled(self, name):
        if name:
            self._enabled[name] = not self._enabled[name]
            for marks in self._marks.values():
                marks.discard(name)
            if self._enabled[name]:
                tier = self._assigned.setdefault(
                    name, self._original_lanes["lanes"][name]["tier"]
                )
                self._marks[tier].add(name)

    def _active_name(self):
        active = self._tier_names()
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
        if key == "o" and self.screen in ("start", "tier", "prescreen", "review"):
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
            elif key == "r" and self.rescan_ready():
                self.rescan()
            else:
                self._enter_prescreen()
            return
        if self.screen == "prescreen":
            names = self._lane_names()
            if key == "up" and names:
                self.cursor = (self.cursor - 1) % len(names)
            elif key == "down" and names:
                self.cursor = (self.cursor + 1) % len(names)
            elif key in ("x", "space") and names:
                self._toggle_enabled(names[min(self.cursor, len(names) - 1)])
            elif key == "enter":
                if self.focus:
                    self._go_confirm()
                else:
                    self._enter_tier(4)
            elif key == "b":
                if self.focus:
                    return
                self.screen = "discovery"
                self.cursor = 0
                self.message = ""
            return
        if self.screen == "tier":
            active = self._tier_names()
            if key == "up" and active:
                self.cursor = (self.cursor - 1) % len(active)
            elif key == "down" and active:
                self.cursor = (self.cursor + 1) % len(active)
            elif key in ("space", "x"):
                # The only decision this screen makes. Carrying a lane is the
                # carry screen's decision, and `b` from tier 4 goes back to it;
                # making it here as well asked the human the same question twice
                # and gave the box on this line two meanings.
                name = self._active_name()
                if name:
                    if name in self._marks[self.tier]:
                        if self.focus and self.tier == 1:
                            self.message = "Tier 1 is the lowest Tier; use carry to turn a Lane off."
                            return
                        self._marks[self.tier].remove(name)
                    else:
                        self._marks[self.tier].add(name)
            elif key == "enter":
                if (self.tier == 1 and not self.focus
                        and any(name not in self._marks[1] for name in active)):
                    self.message = "every lane needs a tier"
                    return
                # A marked lane takes this tier. An unmarked lane that used to
                # be here becomes open for the next lower page. Existing lower
                # assignments remain as that lane's editable default.
                for name in active:
                    if self._assigned.get(name) == self.tier:
                        if self.focus:
                            self._assigned[name] = max(1, self.tier - 1)
                        else:
                            del self._assigned[name]
                for name in active:
                    if name in self._marks[self.tier]:
                        self._assigned[name] = self.tier
                if self.focus:
                    self._go_confirm()
                elif self.tier > 1:
                    self._enter_tier(self.tier - 1)
                else:
                    self._enter_review()
            elif key == "b" and self.focus:
                return
            elif key == "b" and self.tier < 4:
                previous = self.tier + 1
                self._enter_tier(previous)
            elif key == "b" and self.tier == 4:
                self._enter_prescreen()
            return
        if self.screen == "review":
            names = self._review_order
            if key == "up" and names:
                self.cursor = (self.cursor - 1) % len(names)
            elif key == "down" and names:
                self.cursor = (self.cursor + 1) % len(names)
            elif key in ("lane-up", "lane-down") and names:
                self._move_in_tier(-1 if key == "lane-up" else 1)
            elif key in ("1", "2", "3", "4") and names:
                self._move_to_tier(int(key))
            elif key == "v":
                self._paste_tier_lines()
            elif key == "enter":
                if self.focus:
                    self._go_confirm()
                else:
                    self.screen = "routing"
                    self.cursor = 0
                    self.message = ""
            elif key == "b":
                if self.focus:
                    return
                self._enter_tier(1)
            return
        if self.screen == "routing":
            count = len(CLASSES) * 2 + 3
            meters_idx = len(CLASSES) * 2 + 2
            if key == "up":
                self.cursor = (self.cursor - 1) % count
            elif key == "down":
                self.cursor = (self.cursor + 1) % count
            elif key in ("plus", "minus", "x", "space"):
                if self.cursor == meters_idx:
                    self._set_meters(not self._meters_on())
                elif key in ("plus", "minus"):
                    delta = 1 if key == "plus" else -1
                    if self.cursor < len(CLASSES) * 2:
                        cls_idx = self.cursor // 2
                        is_ceiling = (self.cursor % 2 == 1)
                        name = CLASSES[cls_idx]
                        cls_info = self.routing_doc["classes"][name]
                        if is_ceiling:
                            cls_info["ceiling"] = min(4, max(cls_info["floor"], cls_info["ceiling"] + delta))
                        else:
                            cls_info["floor"] = min(cls_info["ceiling"], max(1, cls_info["floor"] + delta))
                    else:
                        name = "margin" if self.cursor == len(CLASSES) * 2 else "gate"
                        old = self.routing_doc[name]
                        self.routing_doc[name] = round(min(1.0, max(0.0, old + delta * 0.05)), 2)
            elif key == "enter":
                self.screen = "confirm"
                self.cursor = 0
                self.message = ""
            elif key == "b":
                if self.focus:
                    return
                # back to the review page, with every tier it holds intact
                self._enter_review()
            return
        if self.screen == "confirm":
            # The list of what is about to be written is longer than a short
            # window: at 80x24 eleven of twenty items showed, and the nine out
            # of sight included both file paths and every routing value. A
            # confirm screen you cannot read to the end is not one.
            count = (len(self._focus_rows()) if self.focus else
                     len(self.lanes_doc["lanes"]) + len(CLASSES) * 2 + 5)
            if key == "up":
                self.cursor = (self.cursor - 1) % count
                return
            if key == "down":
                self.cursor = (self.cursor + 1) % count
                return
            if key == "y":
                if self.focus:
                    self._result = (self._focused_lanes(), copy.deepcopy(self.routing_doc))
                    self.screen = "done"
                    return
                result_lanes = copy.deepcopy(self._original_lanes)
                self._arrange_review()
                for name, lane in result_lanes["lanes"].items():
                    lane["tier"] = self._final_tier(name)
                    # each carried lane's place inside its tier (ticket 28); a
                    # lane not carried is in no order, so it keeps none
                    place = self._place(name) if self._enabled[name] else None
                    if place is None:
                        lane.pop("order", None)
                    else:
                        lane["order"] = place
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
                self._back_from_confirm()

    def _focused_lanes(self):
        """Preserve untouched records and materialize only changed decisions."""
        result = copy.deepcopy(self._original_lanes)
        if self.focus == "routing":
            return result
        self._arrange_review()
        for name, lane in result["lanes"].items():
            original = self._original_lanes["lanes"][name]
            lane["tier"] = self._final_tier(name)
            if self._enabled[name] != original.get("enabled", True):
                if self._enabled[name]:
                    lane.pop("enabled", None)
                else:
                    lane["enabled"] = False
                    lane.pop("order", None)
        for tier in range(1, 5):
            original_names = [name for name, lane in self._original_lanes["lanes"].items()
                              if lane["tier"] == tier and lane.get("enabled", True)]
            original_names.sort(key=lambda name: (
                self._original_lanes["lanes"][name].get("order") is None,
                self._original_lanes["lanes"][name].get("order", 0),
                *self._bench_order(name)))
            current = self._tier_order[tier]
            if current != original_names:
                for order, name in enumerate(current, 1):
                    result["lanes"][name]["order"] = order
        return result

    def _focus_rows(self):
        """The actual focused edits, including their Order consequences."""
        rows = []
        def add(name, old, new):
            rows.append({"cells": [name, "", f"{old} → {new}"],
                         "marked": False, "dimmed": False, "tag": ""})
        result = self._focused_lanes()
        for name, lane in result["lanes"].items():
            original = self._original_lanes["lanes"][name]
            for field in ("tier", "order", "enabled"):
                if lane.get(field) != original.get(field):
                    add(f"{name}.{field}", original.get(field, "unset"), lane.get(field, "unset"))
        for name in CLASSES:
            for field in ("floor", "ceiling"):
                old = self._original_routing["classes"][name][field]
                new = self.routing_doc["classes"][name][field]
                if old != new:
                    add(f"classes.{name}.{field}", old, new)
        for field in ("gate", "margin", "meters"):
            old, new = self._original_routing.get(field), self.routing_doc.get(field)
            if old != new:
                add(field, ("on (default)" if old is None else "on" if old else "off")
                    if field == "meters" else old,
                    ("on" if new else "off") if field == "meters" else new)
        for path, changed in ((self.lanes_path, result != self._original_lanes),
                              (self.routing_path, self.routing_doc != self._original_routing)):
            if changed:
                rows.append({"cells": ["file", "", path], "marked": False,
                             "dimmed": False, "tag": ""})
                resolved = os.path.realpath(path)
                if resolved != os.path.abspath(path):
                    rows.append({"cells": ["target", "", resolved], "marked": False,
                                 "dimmed": False, "tag": ""})
        if not rows:
            rows.append({"cells": ["No changes", "", "Nothing will be written"],
                         "marked": False, "dimmed": False, "tag": ""})
        return rows

    def _bench_columns(self):
        """The benchmark columns worth their width: the ones some lane on this
        screen has a figure for.

        Now that a figure reaches only the lane that ran its effort, most
        columns are empty for most lanes, and an all-dash column costs the
        width the columns with data need — at 80 the fit dropped every
        benchmark and left the mean rank alone (ticket 17).
        """
        epoch_names = (self.bench or {}).get("epoch_benchmarks", list(EPOCH_BENCHMARKS))
        aa_names = (list(self.bench["aa_columns"])
                    if self.bench is not None and self.bench.get("aa_skipped") is None
                    else [])
        if self.bench is None:
            return list(epoch_names), aa_names
        lanes = self.bench.get("lanes") or {}
        measured, aa_measured = set(), set()
        for name in self.lanes_doc["lanes"]:
            rec = lanes.get(name) or {}
            measured.update((rec.get("cells") or {}).keys())
            aa = rec.get("aa") or {}
            aa_measured.update(k for k, v in (aa.get("cols") or {}).items() if v is not None)
        kept = [n for n in epoch_names if n in measured]
        kept_aa = [n for n in aa_names if n in aa_measured]
        return (kept or list(epoch_names)), (kept_aa or aa_names)

    def _bench_cells(self, lane_name, epoch_names, aa_names):
        """This lane's figures, and only its own.

        A figure measured at another effort was produced by another lane of
        the same model; printing it here made all six astra lanes read the
        same three scores, so the tier they were being sorted into was a
        judgement on numbers none of them had produced (ticket 17). An empty
        column and `— (n=0)` are the honest reading: nobody measured this
        model at this effort.
        """
        rec = (self.bench or {}).get("lanes", {}).get(lane_name)
        cells = (rec or {}).get("cells") or {}
        values = [
            "—" if name not in cells else f'{cells[name]["performance"] * 100:.1f}'
            for name in epoch_names
        ]
        values.append((rec or {}).get("mean_s") or "—")
        if aa_names:
            aa = (rec or {}).get("aa")
            for name in aa_names:
                value = aa["cols"].get(name) if aa else None
                values.append(fmt_aa_value(value))
            # AA's cost per task at this lane's effort, beside its scores
            values.append(fmt_cost((aa or {}).get("cost_usd")))
            values.append((aa or {}).get("mean_s") or "—")
        return values

    def _frame(self, screen, title, *, tier=None, columns=None, rows=None,
               footer="", body=None, legend=None, elastic="", panel=None,
               defs=None, warnings=None):
        return {
            "screen": screen, "title": title, "tier": tier,
            "columns": columns or [], "rows": rows or [],
            "footer": footer, "message": self.message,
            "body": body or [], "legend": legend or [],
            "steps": self._step_marker(), "elastic": elastic,
            # paragraphs drawn beside the table, wrapped to the room it leaves
            "panel": panel or [],
            # under the table, before the legend: terms defined in two columns
            # (`definition`), and after it: warnings, read before the keys
            "defs": list(defs or []), "warnings": list(warnings or []),
        }

    def _prescreen_legend(self):
        """(definitions, legend lines): the reasons on this screen, and no
        others, plus a count of the benchmarked models that are nobody's lane.

        Each reason in the `why` column is a phrase; the sentence it stands for
        is a definition here. Defining every phrase unconditionally would push
        the lane rows off a short window to explain a case that is not on
        screen, so each entry is earned by a reason that is actually shown.
        The models no lane runs used to be listed by name, which at thirty
        names was noise that ran off the line; the count says what matters,
        that the rows name models the catalog does not.
        """
        kinds = {self._proposals[name]["kind"] for name in self._lane_names()}
        defs = []
        for kind, entry in ((KIND_DOMINATED, DOMINATED_DEF), (KIND_NOT_DOMINATED, NOT_DOMINATED_DEF),
                            (KIND_RECORDED, RECORDED_DEF), (KIND_ULTRA, ULTRA_DEF)):
            if kind in kinds:
                defs.append(entry)
        if kinds & {KIND_NO_ROWS, KIND_UNAVAILABLE}:
            defs.append(ABSENCE_DEF)
        legend = []
        if self.effort_rows and self._unmatched:
            count = len(self._unmatched)
            legend.append(self._fit(f"{plural(count, 'benchmarked model')} "
                                    f"{'has' if count == 1 else 'have'} no lane"))
        return defs, legend

    def _tier_legend(self):
        """Say what this page left out, then the tier definition.

        A lane taken at a higher tier and a lane not carried are both hidden
        (ticket 25), so the count of each is the one trace they leave; the line
        is earned only when something was left out.
        """
        lines = []
        taken = sum(
            1 for name in self._carried()
            if self._assigned.get(name, 0) > self.tier
        )
        off = sum(1 for name in self.lanes_doc["lanes"] if not self._enabled[name])
        hidden = hidden_legend(taken, off)
        if hidden:
            lines.append(hidden)
        # The tier definition is reference, so it goes last: last renders
        # directly above the footer, where it reads as a second footer line, and
        # it is the first line a short window gives up.
        lines.append(TIER_ONELINER)
        return lines

    def _lanes_at(self, tier):
        return sorted(name for name in self._carried() if self._assigned.get(name) == tier)

    def _tier_map_lines(self):
        lines = []
        for tier in range(1, 5):
            names = self._lanes_at(tier)
            if not names:
                lines.append(f"tier {tier} (0): (none)")
            else:
                # five lanes on one tier already ran past column 80 and were cut
                # after a comma, which reads as a list that stops for no reason
                lines.append(self._drift_line(f"tier {tier}", names, always_count=True))
        return lines

    def _fit(self, line):
        """One width rule for every prose line: the renderer clips at width - 1."""
        return fit_line(line, self._width)

    def _drift_line(self, label, items, always_count=False):
        return list_line(label, items, self._width, always_count)

    def _confirm_defs(self):
        """The confirm page's definitions: each routing term, its value as it
        will be written, and what it means in one line, from CONTEXT.md."""
        margin, gate = self.routing_doc["margin"], self.routing_doc["gate"]
        if self._meters_on():
            entries = [
                definition("margin", "the pace lead a later lane needs to take the job from the pick",
                           value=str(margin)),
                definition("gate", "the lowest remaining a meter may have and still take a job: "
                           f"{gate * 100:g}%", value=str(gate)),
                definition("meters", "ranking uses Gate and Margin; off is Tier, Order and name only",
                           value="on"),
            ]
        else:
            entries = [
                definition("margin", "stored; metering is off", value=str(margin)),
                definition("gate", "stored; metering is off", value=str(gate)),
                definition("meters", "ranking is Tier, Order and name; Gate and Margin stay stored",
                           value="off"),
            ]
        return [CLASSES_DEF, *entries, CONFIRM_OFF_DEF]

    def _meters_on(self):
        return meters_enabled(self.routing_doc)

    def _set_meters(self, enabled):
        if enabled:
            if "meters" not in self._original_routing:
                self.routing_doc.pop("meters", None)
            else:
                self.routing_doc["meters"] = True
        else:
            self.routing_doc["meters"] = False

    def _routing_settings(self):
        values = []
        for name in CLASSES:
            cls_info = self.routing_doc["classes"][name]
            values.append((name, "floor", cls_info["floor"]))
            values.append((name, "ceiling", cls_info["ceiling"]))
        values.extend([(None, "margin", self.routing_doc["margin"]),
                       (None, "gate", self.routing_doc["gate"]),
                       (None, "meters", "on" if self._meters_on() else "off")])
        return values

    # The routing page's last group: the three settings that make the pick.
    RANKING_GROUP = ("ranking", "how the pick is made among eligible lanes")

    def _routing_rows(self):
        """The settings grouped: each class is a heading with its description
        from the Class guide, its floor and ceiling indented under it, then
        `ranking` with margin, gate and meters. The cursor is an index into
        `_routing_settings`, so it lands only on a setting, never a heading.

        A description is fitted to the room the panel leaves at this width,
        because the panel explains the setting under the cursor and is the
        one thing this page must not lose at 80 places; at 120 the sentence
        is whole.
        """
        settings = self._routing_settings()
        names = ["  floor", "  ceiling", "  margin", "  gate", "  meters", *CLASSES,
                 self.RANKING_GROUP[0], "setting"]
        room = max(MIN_ELASTIC, self._width - 1 - max(len(n) for n in names) - 2
                   - (PANEL_MIN + PANEL_GAP + 2))

        def heading(name, desc):
            return {"cells": [name, _clip(desc, room)], "marked": False, "dimmed": False,
                    "cursor": False, "tag": "", "styles": {"setting": "section", "value": "desc"}}

        rows = []
        for index, (cls, kind, value) in enumerate(settings):
            if kind == "floor":
                rows.append(heading(cls, self.class_guide.get(cls, "")))
            elif kind == "margin":
                rows.append(heading(*self.RANKING_GROUP))
            cell = ("[x] on" if self._meters_on() else "[ ] off") if kind == "meters" else str(value)
            rows.append({"cells": [f"  {kind}", cell],
                         "marked": kind == "meters" and self._meters_on(),
                         "dimmed": False, "cursor": index == self.cursor, "tag": ""})
        return rows

    def _routing_panel(self):
        """What the setting under the cursor does, drawn beside the table
        (ticket 25): its heading, then a sentence or two, then which of this
        session's lanes it admits. The wording follows CONTEXT.md."""
        settings = self._routing_settings()
        cls, kind, value = settings[min(self.cursor, len(settings) - 1)]
        if cls is not None:
            info = self.routing_doc["classes"][cls]
            floor, ceiling = info["floor"], info["ceiling"]
            if kind == "floor":
                paragraphs = [
                    f"{cls} floor: {value}",
                    f"The lowest tier a {cls} job accepts, and the tier each {cls} job "
                    "is sent at by default.",
                ]
                at = self._lanes_at(floor)
                paragraphs.append(f"Tier {floor} now holds {len(at)} lane{'s' if len(at) != 1 else ''}"
                                  + (f": {', '.join(at)}." if at else "."))
            else:
                paragraphs = [
                    f"{cls} ceiling: {value}",
                    f"The highest tier a {cls} job accepts: extra capability for a job "
                    "that needs it, and the most the class can ever get.",
                ]
                admitted = [name for tier in range(ceiling, floor - 1, -1) for name in self._lanes_at(tier)]
                paragraphs.append(f"Range {floor}-{ceiling} admits {len(admitted)} "
                                  f"lane{'s' if len(admitted) != 1 else ''}"
                                  + (f": {', '.join(admitted)}." if admitted else "."))
            paragraphs.append("A job sent to a lane by name skips the range.")
            return paragraphs
        if kind in ("gate", "margin") and not self._meters_on():
            return [f"{kind}: {value}", "Stored only while metering is off.",
                    "Ranking uses Tier, Order and Lane name. Turn meters on to use Gate and Margin."]
        if kind == "margin":
            return [
                f"margin: {value}",
                "A lane further down the order takes the job from the pick only when its "
                f"pace beats the pick's by more than {value}.",
                "Pace is unspent quota against time left in the week; above 1.0 the "
                "quota will expire unused.",
            ]
        if kind == "meters":
            return [
                f"meters: {value}",
                "When on, ranking uses Gate and Margin, and dispatch probes Remaining "
                "at the start and finish of a job.",
                "When off, ranking is Tier, Order and lane name only. Cached Remaining "
                "may still show. Gate and Margin stay stored.",
            ]
        return [
            f"gate: {value}",
            f"A lane is skipped outright once its meter drops below {value * 100:g}% "
            "remaining, however capable it is.",
            "For shared spend, Remaining is the lower Window fraction. On agy no "
            "vendor joins the two Windows, so the lower one is an assumption.",
        ]

    def _step_marker(self):
        """`start · harnesses · carry · T4 · [T3] · T2 · T1 · routing · confirm`.

        The bracketed step is the current one. Returns "" on the terminal screens,
        which have no step to be at.
        """
        if self.screen in ("done", "quit"):
            return ""
        here = f"tier{self.tier}" if self.screen == "tier" else self.screen
        steps = STEPS
        if self.focus:
            focus_key = "prescreen" if self.focus == "carry" else self.focus
            steps = tuple((key, label) for key, label in STEPS if key in (focus_key, "confirm"))
        parts = [f"[{label}]" if key == here else label for key, label in steps]
        return " · ".join(parts)

    def _discovery_notices(self):
        return discovery_notices(self.discovery, self._width)

    def view(self, width=80):
        """The frame for a terminal `width` places wide. Prose is fitted to
        that width, so a wide terminal shows a whole path or list that 80
        places cut."""
        self._width = max(MIN_WIDTH, width)
        if self.screen == "start":
            body = [
                *start_facts(self.lanes_path, self.routing_path, self.bench_page_path,
                             self.discovery, self._width, refresh=self.refresh,
                             rows_note=self.rows_note),
                "",
                "Nothing is written until the confirm screen; q leaves without writing.",
            ]
            footer = ("any key: continue  o: open benchmark page  q: quit"
                      if self.bench_page_path else "any key: continue  q: quit")
            return self._frame(
                "start", "Delegate setup",
                footer=footer,
                body=body,
            )
        if self.screen == "discovery":
            # What the scrub found, per harness: whether it answered, how many
            # models it listed, and the Lanes the current generation adds and
            # supersedes. It ran at launch, before this page, and `r` runs it
            # again; nothing on this page said so, and Orin asked when it ran.
            live = isinstance(self.discovery, dict)
            # a saved snapshot of harness facts alone lists no model, which is
            # not the same as a harness that listed none
            facts = live and self.discovery.get("model_facts_available") is not False
            harnesses = (self.discovery.get("harnesses") if live else None) or {}
            listed = {}
            for item in (self.discovery.get("models") if live else None) or []:
                if isinstance(item, dict):
                    listed[item.get("harness")] = listed.get(item.get("harness"), 0) + 1
            refresh = self.refresh or {}
            new = {name: (self.lanes_doc["lanes"].get(name) or {}).get("harness")
                   for name in refresh.get("new") or ()}
            removed = [name.rsplit("@", 1)[-1] for name in refresh.get("removed") or ()]
            rows = []
            for name in HARNESSES:
                info = harnesses.get(name) if isinstance(harnesses.get(name), dict) else None
                if info is not None:
                    status = info.get("status") or "missing"
                    if status == "ok":
                        label, found = "found", True
                    elif status == "error":
                        err = info.get("error") or "unknown error"
                        label, found = f"error: {err}", False
                    else:
                        label, found = "missing", False
                    count = info.get("discovered_count")
                    models = ("" if not found else "—" if not facts
                              else str(count if isinstance(count, int) else listed.get(name, 0)))
                else:
                    found = name in self.discovered
                    label = "found" if found else "missing"
                    models = "—"
                counts = ([str(sum(1 for h in new.values() if h == name)), str(removed.count(name))]
                          if self.refresh is not None else ["—", "—"])
                rows.append({"cells": [name, label, models, *counts], "marked": False,
                             "dimmed": not found, "cursor": False, "tag": ""})
            body = [self._fit(f"Scanned {self.scanned}: models per harness, benchmark rows, "
                              "current generation.")]
            if self.rows_note:
                body.append(self._fit(self.rows_note))
            legend = [CLAUDE_COUNT_LEGEND] if live and "claude" in harnesses else []
            return self._frame(
                "discovery", "Delegate setup: discovery",
                columns=["harness", "status", "models", "new lanes", "removed lanes"],
                rows=rows,
                body=body,
                footer=DISCOVERY_RESCAN_FOOTER if self._rescan is not None else DISCOVERY_FOOTER,
                legend=legend,
            )
        if self.screen == "prescreen":
            names = self._lane_names()
            rows = []
            for index, name in enumerate(names):
                lane = self.lanes_doc["lanes"][name]
                on = self._enabled[name]
                # One signal for one fact. This screen used to carry three — the
                # box, a `carry` column reading on/off, and an `off` tag after
                # the reason — and the three together cost the reason its room:
                # at 80 places the reason column did not fit at all and was
                # dropped, so the screen proposed a lane off and said nothing.
                rows.append({
                    "cells": [
                        "[x]" if on else "[ ]", name, lane["model"], lane["effort"],
                        self._reasons[name],
                    ],
                    "marked": on, "dimmed": not on,
                    "cursor": index == self.cursor,
                    "tag": "",
                    # The one reason class drawn in a style of its own: a
                    # verdict the data gave, which nobody recorded and which is
                    # worth a second look. The others say nothing the box and
                    # the row's weight do not already say.
                    "styles": ({"why": "why-data"}
                               if self._proposals[name]["kind"] == KIND_DOMINATED else {}),
                })
            defs, legend = self._prescreen_legend()
            return self._frame(
                "prescreen", "Lanes to carry",
                columns=["carry", "lane", "model", "effort", "why"],
                rows=rows,
                footer=PRESCREEN_FOOTER,
                defs=defs,
                legend=legend,
                elastic="why",
            )
        if self.screen == "tier":
            epoch_names, aa_names = self._bench_columns()
            columns = ["mark", "lane", "model", "effort", *epoch_names, "Epoch mean rank"]
            if aa_names:
                columns.extend([*aa_names, "AA $/task", "AA mean rank"])
            active = self._tier_names()
            rows = []
            for index, name in enumerate(active):
                lane = self.lanes_doc["lanes"][name]
                marked = name in self._marks[self.tier]
                rows.append({
                    "cells": ["[x]" if marked else "[ ]", name, lane["model"], lane["effort"],
                              *self._bench_cells(name, epoch_names, aa_names)],
                    "marked": marked, "dimmed": False,
                    "cursor": index == self.cursor,
                    "tag": "",
                })
            return self._frame(
                "tier", f"Assign tier {self.tier}", tier=self.tier,
                columns=columns, rows=rows,
                footer=TIER_FOOTER,
                # The tier definition belongs where the decision is made, but it
                # and the key hints together overflow an 80-column footer, and a
                # truncated footer loses the keys.
                legend=[*self._tier_legend(), *(
                    ["Unmarking moves a Lane down one Tier; Enter reviews the changes."]
                    if self.focus and self.tier > 1 else [])],
            )
        if self.screen == "review":
            epoch_names, aa_names = self._bench_columns()
            columns = ["#", "lane", "model", "effort", *epoch_names, "Epoch mean rank"]
            if aa_names:
                columns.extend([*aa_names, "AA mean rank"])
            here = self._review_cursor_name()
            rows = []
            # One section per tier, 4 to 1, each numbered in Orin's order
            # (ticket 28). The section line states the tier, so a line needs no
            # tier box; the number is the place ranking tries it in. An empty
            # tier keeps its section, as the place 1-4 can move a lane to.
            for tier in (4, 3, 2, 1):
                order = self._tier_order[tier]
                count = f"{len(order)} lane{'s' if len(order) != 1 else ''}" if order else "no lanes"
                rows.append(section_row(f"Tier {tier} ({count})", len(columns)))
                for place, name in enumerate(order, 1):
                    lane = self.lanes_doc["lanes"][name]
                    rows.append({
                        "cells": [f"{place:>2}", name, lane["model"], lane["effort"],
                                  *self._bench_cells(name, epoch_names, aa_names)],
                        "marked": False, "dimmed": False,
                        "cursor": name == here, "tag": "",
                    })
            off = sum(1 for name in self.lanes_doc["lanes"] if not self._enabled[name])
            # The keys spelled out, then the rule, then any warning: three
            # things read three ways. The lanes not carried used to be listed
            # by name, which at thirty-seven ran off the line; they are on
            # the carry page, so a count is what this page owes.
            legend = [REVIEW_ORDER_LEGEND if self._meters_on()
                      else "Metering is off. Ranking uses Tier, Order and Lane name."]
            if off:
                legend.append(f"{plural(off, 'lane')} not carried "
                              f"{'keeps its' if off == 1 else 'keep their'} catalog tier.")
            return self._frame(
                "review", "Order each tier",
                columns=columns, rows=rows,
                footer=REVIEW_FOOTER,
                defs=REVIEW_MOVE_DEFS,
                legend=legend,
                # Coverage, not a verdict on the Tier: which lanes a Tier
                # carries stays Orin's decision (ticket 29). A warning, so it
                # is drawn as one and never sits in the dim legend.
                warnings=meter_dependency_lines(self._meter_coverage()),
            )
        if self.screen == "routing":
            return self._frame(
                "routing", "Routing",
                columns=["setting", "value"], rows=self._routing_rows(),
                footer=ROUTING_FOOTER,
                # what the setting under the cursor does sits beside the table;
                # the tier map below is reference for every setting at once
                panel=self._routing_panel(),
                legend=self._tier_map_lines(),
                # the descriptions are fitted to the panel's room in
                # `_routing_rows`, so the column may take their width
                elastic="value",
            )
        if self.screen == "confirm":
            rows = []
            # `carry` sits between the item and its value so that `value`, the
            # one column with a path in it, is last: an elastic column pads to
            # the widest row it holds, and a 40-place path column with `tier 4`
            # in it opened a river of blanks across every other line.
            for name in self.lanes_doc["lanes"]:
                off = not self._enabled[name]
                # the column says `off`; a tag saying it again read `off  off`
                rows.append({"cells": [name, "off" if off else "",
                                        f"tier {self._final_tier(name)}"],
                             "marked": False, "dimmed": off, "tag": ""})
            for name in CLASSES:
                cls_info = self.routing_doc["classes"][name]
                rows.append({"cells": [f"classes.{name}.floor", "", str(cls_info["floor"])],
                             "marked": False, "dimmed": False, "tag": ""})
                rows.append({"cells": [f"classes.{name}.ceiling", "", str(cls_info["ceiling"])],
                             "marked": False, "dimmed": False, "tag": ""})
            for name in ("margin", "gate"):
                rows.append({"cells": [name, "", str(self.routing_doc[name])], "marked": False,
                             "dimmed": False, "tag": ""})
            rows.append({"cells": ["meters", "", "on" if self._meters_on() else "off"],
                         "marked": False, "dimmed": False, "tag": ""})
            for path in (self.lanes_path, self.routing_path):
                rows.append({"cells": ["file", "", path], "marked": False,
                             "dimmed": False, "tag": ""})
            if self.focus:
                rows = self._focus_rows()
            for index, row in enumerate(rows):
                row["cursor"] = index == self.cursor
            return self._frame(
                "confirm", "Confirm changes",
                columns=["item", "carry", "value"], rows=rows,
                footer="↑/↓ or j/k: read on  y: write  n/q: quit without writing  b: back",
                # a path is the one value here that will not fit a 24-place cell,
                # and `/Users/dreiss/.config/de…` is not a path anyone can check
                elastic="value",
                legend=["Only the listed changes will be written."] if self.focus else [],
                defs=[] if self.focus else self._confirm_defs(),
            )
        return self._frame(self.screen, "Delegate setup")


MIN_ELASTIC = 12


def section_row(text, width):
    """A heading line inside a table, such as the review page's `Tier 4 (2 lanes)`.
    Its cells are blank so column fitting ignores it; `layout_lines` draws
    `section` across the row. It is never the cursor."""
    return {"cells": [""] * width, "section": text, "marked": False,
            "dimmed": False, "cursor": False, "tag": ""}


def _clip(text, width):
    """Fit a cell, and say so when it did not fit.

    A cell cut with no mark cannot be told from a value that ends there:
    `dominated by the` looks like the whole reason. The ellipsis is one place of
    the width, which is cheaper than the doubt.
    """
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    return text[: width - 1] + "…" if width > 1 else "…"


def _natural_width(view, index):
    cells = [len(row["cells"][index]) for row in view["rows"] if index < len(row["cells"])]
    return max([len(view["columns"][index])] + cells)


def _fit_table(view, width):
    """Return visible column indices and widths, preserving decision columns.

    `width` is the room the table has; the caller deducts the tag first, because
    a tag is drawn after the last column and then clipped with the line, which
    turned `tier 3` into `ti`.

    One column may be named `elastic` in the frame. It is never dropped: it takes
    whatever room the other columns leave and its cells are clipped to that. A
    column that explains a decision is the last thing a narrow window should
    lose — dropping it is how the pre-screen came to propose a lane off at 80
    places and give no reason at all.

    `model` and `effort` are fitted last, after the data. Both are already
    spelled out in the lane name — `astra-xhigh@codex` is the astra model at
    xhigh — so at 80 places they were 27 places of restatement drawn ahead of
    the benchmark scores, and the scores, which are the only reason the tier
    screen exists, were the columns that fell off the end.
    """
    columns = view["columns"]
    if not columns:
        return [], []
    elastic = view.get("elastic")
    elastic_index = columns.index(elastic) if elastic in columns else None
    priority_names = ("mark", "carry", "#", "lane", "Epoch mean rank")
    deferred_names = ("model", "effort")
    priority = [columns.index(name) for name in priority_names if name in columns]
    deferred = [columns.index(name) for name in deferred_names
                if name in columns and columns.index(name) not in priority
                and columns.index(name) != elastic_index]
    rest = [i for i in range(len(columns))
            if i not in priority and i not in deferred and i != elastic_index]
    chosen = []
    widths = {}
    used = 0
    room = max(1, width - 1)
    # 24 places a cell at 80 and 100; a wide terminal lets a cell run longer,
    # so `classes.mechanical.ceiling` is whole at 200 instead of cut as at 80
    cap = max(24, room // 6)
    for i in priority + rest + deferred:
        cell_width = min(_natural_width(view, i), cap)
        if chosen and used + 2 + cell_width > room:
            # A column skipped over while a narrower one behind it is drawn
            # reads as data nobody gathered: at 100 places FrontierCode dropped
            # out and APEX-Agents took its place. What is shown is a prefix of
            # what was asked for, so the rest is missing width, not missing data.
            if i in priority:
                continue
            break
        chosen.append(i)
        widths[i] = cell_width
        used += (2 if len(chosen) > 1 else 0) + cell_width
    if elastic_index is not None:
        spare = room - used - (2 if chosen else 0)
        if spare >= MIN_ELASTIC or not chosen:
            chosen.append(elastic_index)
            widths[elastic_index] = min(_natural_width(view, elastic_index),
                                        max(MIN_ELASTIC, spare))
    chosen.sort()
    return chosen, [widths[i] for i in chosen]


# The table keeps this many rows before the legend starts giving way. Four left
# 4 of 11 lanes on screen once the pre-screen legend grew; the legend is
# reference and the rows are the work.
ROW_FLOOR = 6
MIN_WIDTH, MIN_HEIGHT = 80, 16
# The rows above the body on every page: the trail, a blank row, the title and
# a blank row. The body or the table starts here.
TOP = 4

# One palette for every screen. A style names what a piece of text is, never
# how it looks; the look is decided here, once, as (attributes, colour), and
# `_palette` turns it into curses attributes for the terminal in front of us:
# the colour when the terminal has colours, and bold, dim and reverse alone
# when it has not, so every style is still told apart. Colours are three of
# the basic eight on the terminal's own background, and each means one thing:
# green is settled (a step behind us, a box ticked, a value to be written),
# yellow is attention (a verdict the data gave, a warning), cyan is a key to
# press. Everything else is weight.
STYLES = {
    "steps": ("dim", None),               # the trail: its dots and the steps ahead
    "step-done": ("", "green"),           # a step behind us
    "step-here": ("bold reverse", None),  # the step this page is
    "title": ("bold", None),
    "title-note": ("dim", None),          # `1-44 of 46` beside the title
    "header": ("bold underline", None),   # the underline is the rule under it
    "body": ("", None),
    "row": ("", None),
    "row-dim": ("dim", None),             # a lane not carried, a harness missing
    "row-cursor": ("reverse", None),      # one bar, readable on any background
    "row-cursor-dim": ("reverse", None),
    "mark-on": ("bold", "green"),         # a ticked box
    "why-data": ("", "yellow"),           # a reason the data gave, not the human
    "section": ("bold", None),            # a heading inside a table
    "desc": ("dim", None),                # a description beside a heading
    "panel": ("", None),
    "panel-head": ("bold", None),
    "legend": ("dim", None),              # reference, read after the rows
    "term": ("bold", None),               # the term of a definition
    "value": ("bold", "green"),           # a value about to be written
    "warning": ("bold", "yellow"),        # a warning: read before the keys
    "footer": ("", None),                 # the keys' actions
    "key": ("bold", "cyan"),              # the keys themselves
    "message": ("bold", None),
}
# A panel beside a table: the gap before its rule, the narrowest it may be
# before it is not drawn, and the widest its prose runs, for reading.
PANEL_GAP, PANEL_MIN, PANEL_MAX = 3, 28, 72


def _panel_lines(paragraphs, width):
    """Wrap panel paragraphs to `width`, a blank line between paragraphs; the
    first paragraph is the heading."""
    out = []
    for index, paragraph in enumerate(paragraphs):
        if index:
            out.append(("", "panel"))
        role = "panel-head" if index == 0 else "panel"
        out.extend((line, role) for line in textwrap.wrap(paragraph, width) or [""])
    return out


def _step_spans(steps):
    """Where each step of the trail is drawn: the steps before `[here]` are
    done, `[here]` is the step this page is, and the rest, like the dots
    between them, keep the line's own quiet style."""
    spans, x, done = [], 0, True
    for part in steps.split(" · "):
        if part.startswith("[") and part.endswith("]"):
            spans.append((x, x + len(part), "step-here"))
            done = False
        elif done:
            spans.append((x, x + len(part), "step-done"))
        x += len(part) + 3
    return spans


def _key_spans(footer):
    """The keys of a footer, one `key: action` two spaces from the next: each
    key up to its colon is drawn as a key, and the action keeps the line's
    style."""
    spans, x = [], 0
    for item in footer.split("  "):
        key, colon, _action = item.partition(": ")
        if colon:
            spans.append((x, x + len(key), "key"))
        x += len(item) + 2
    return spans


def _definition_lines(defs):
    """A page's definitions in two aligned columns, each as (text, role,
    spans): the term in its own style, the value in the value style, and the
    meaning in the legend's."""
    if not defs:
        return []
    term_width = max(len(entry["term"]) for entry in defs)
    value_width = max(len(entry.get("value") or "") for entry in defs)
    out = []
    for entry in defs:
        text = entry["term"].ljust(term_width) + "  "
        spans = [(0, len(entry["term"]), entry.get("style") or "term")]
        if value_width:
            value = entry.get("value") or ""
            if value:
                spans.append((len(text), len(text) + len(value), "value"))
            text += value.ljust(value_width) + "  "
        out.append((text + entry["text"], "legend", spans))
    return out


def _legend_zone(view):
    """What sits between the table and the keys, top to bottom: the
    definitions, the legend lines, then the warnings, as (text, role, spans)."""
    return [*_definition_lines(view.get("defs") or []),
            *((line, "legend", []) for line in view.get("legend") or []),
            *((line, "warning", []) for line in view.get("warnings") or [])]


def layout_lines(view, width, height):
    """Place one frame on a character grid: [(row, text, role, spans)].

    Separated from the curses call so a test can read the screen a human sees.
    Every fault this function now guards against — a reason column silently
    dropped, a tag clipped to `ti`, rows scrolled away with nothing to say so —
    was invisible to tests that only ever read the frame dict.

    The trail is row 0 and the title row 2, a blank row under each, and the
    body or the table starts at `TOP`. The keys are the third row from the
    end with a blank row above them; the legend zone — definitions, legend
    lines, warnings (`_legend_zone`) — ends at that blank row and keeps one
    more between it and the last table row, so the rows, the reference and
    the keys never run together. The zone gives way first, last line first,
    once the table would lose its floor.

    `spans` is [(start, end, style)] over `text`: each a piece the renderer
    draws again in a style of its own over the line's role — a ticked box,
    the step this page is, a key, a reason the data gave. Most lines have
    none, and the cursor row never does, so it stays one bar.

    An entry's leading spaces are its column: a panel line beside the table
    shares a row with a table line and starts where the table ends, so it is
    drawn at its indent rather than over the row. `overlay` composes them.
    """
    lines = []
    rows = view["rows"]
    tag_room = max([len(row["tag"]) for row in rows], default=0)
    chosen, widths = _fit_table(view, width - (tag_room + 2 if tag_room else 0))
    body = view.get("body") or []
    footer_y = height - 3
    # the keys never touch what stands above them
    legend_end = footer_y - 1
    table_floor = TOP + (1 if view["columns"] else 0) + min(len(rows), ROW_FLOOR)

    def fit_legend(candidate):
        """The zone entries that leave the table its floor and its blank row."""
        keep = max(0, legend_end - (table_floor + 1))
        if keep < len(candidate):
            candidate = candidate[:keep]
            if keep:
                candidate[-1] = ("… enlarge the window for the rest", "legend", [])
        return candidate

    legend = fit_legend(_legend_zone(view))
    legend_y = legend_end - len(legend)
    # the last table row stops a blank row short of the legend, or of the keys
    table_end = legend_y - 1 if legend else legend_y

    y = TOP
    for line in body:
        if y >= table_end:
            break
        lines.append((y, line, "body", []))
        y += 1
    first, shown = 0, 0
    if chosen and view.get("panel"):
        table_width = sum(widths) + 2 * (len(widths) - 1)
        panel_x = table_width + PANEL_GAP
        panel_width = min(PANEL_MAX, width - 1 - panel_x - 2)
        if panel_width >= PANEL_MIN:
            panel_y = y + (1 if body else 0)
            for offset, (text, role) in enumerate(_panel_lines(view["panel"], panel_width)):
                if panel_y + offset >= table_end:
                    break
                lines.append((panel_y + offset, " " * panel_x + "│ " + text, role, []))
        else:
            # no room beside the table: the panel takes the legend's place,
            # ahead of it, since it explains the row being edited
            legend = fit_legend([(text, "legend", []) for text, _role
                                 in _panel_lines(view["panel"], width - 1)] + legend)
            legend_y = legend_end - len(legend)
            table_end = legend_y - 1 if legend else legend_y
    if chosen and y < table_end:
        if body:
            y += 1
        if y < table_end:
            lines.append((y, "  ".join(_clip(view["columns"][i], w).ljust(w)
                                      for i, w in zip(chosen, widths)), "header", []))
            y += 1
        room = max(1, table_end - y)
        cursor_index = next((i for i, row in enumerate(rows) if row["cursor"]), 0)
        if cursor_index >= room:
            first = cursor_index - room + 1
        for row in rows[first:]:
            if y >= table_end:
                break
            if row.get("section"):
                lines.append((y, fit_line(row["section"], width), "section", []))
                y += 1
                shown += 1
                continue
            cells, spans, x = [], [], 0
            styles = row.get("styles") or {}
            for i, w in zip(chosen, widths):
                cell = row["cells"][i] if i < len(row["cells"]) else ""
                # a ticked box and a cell the frame styles are drawn in their
                # own style; the cursor row is one bar, so it takes none
                if not row["cursor"]:
                    if cell.startswith("[x]"):
                        spans.append((x, x + min(3, w), "mark-on"))
                    style = styles.get(view["columns"][i])
                    if style and cell:
                        spans.append((x, x + min(len(cell), w), style))
                cells.append(_clip(cell, w).ljust(w))
                x += w + 2
            line = "  ".join(cells)
            if row["tag"]:
                line += "  " + row["tag"]
            role = "row-cursor" if row["cursor"] else "row"
            if row["dimmed"]:
                role += "-dim"
            lines.append((y, line, role, spans))
            y += 1
            shown += 1

    title = view["title"]
    title_spans = []
    if shown and shown < len(rows):
        # a window too short for the list said nothing about it, so eight lanes
        # looked like the whole catalog
        note = f"{first + 1}-{first + shown} of {len(rows)}"
        gap = width - 1 - len(title) - len(note)
        title = title + " " * gap + note if gap >= 2 else f"{title}  {note}"
        title_spans = [(len(title) - len(note), len(title), "title-note")]
    steps = view.get("steps") or ""
    if steps:
        lines.append((0, steps, "steps", _step_spans(steps)))
    lines.append((2, title, "title", title_spans))
    for offset, (text, role, spans) in enumerate(legend):
        lines.append((legend_y + offset, text, role, spans))
    lines.append((footer_y, view["footer"], "footer", _key_spans(view["footer"])))
    lines.append((height - 2, view["message"], "message", []))
    return lines


def overlay(entries, width, height):
    """The grid a terminal of this size shows, one string per row, with each
    entry drawn at its leading-space indent over what the row already holds."""
    grid = [""] * height
    for y, text, _role, _spans in entries:
        if not (0 <= y < height) or not text:
            continue
        x = len(text) - len(text.lstrip(" "))
        row = grid[y].ljust(x)
        grid[y] = (row[:x] + text[x:] + row[len(text):])[: width - 1].rstrip()
    return grid


def _palette(curses):
    """`STYLES` as curses attributes for this terminal.

    Colour comes only when the terminal has at least the basic eight and
    takes its own background (`use_default_colors`), so a light theme and a
    dark one both keep their background under the text. Without that, or if
    a pair cannot be made, every style keeps its attributes and drops its
    colour, so a ticked box is still bold and a key is still bold.
    """
    attrs = {"bold": curses.A_BOLD, "dim": curses.A_DIM,
             "reverse": curses.A_REVERSE, "underline": curses.A_UNDERLINE}
    codes = {"green": curses.COLOR_GREEN, "cyan": curses.COLOR_CYAN,
             "yellow": curses.COLOR_YELLOW}
    mono = {}
    for style, (words, _colour) in STYLES.items():
        attr = 0
        for word in words.split():
            attr |= attrs[word]
        mono[style] = attr
    try:
        if not (curses.has_colors() and getattr(curses, "COLORS", 0) >= 8):
            return mono
        curses.use_default_colors()
        pairs = {}
        palette = dict(mono)
        for style, (_words, colour) in STYLES.items():
            if colour:
                if colour not in pairs:
                    pairs[colour] = len(pairs) + 1
                    curses.init_pair(pairs[colour], codes[colour], -1)
                palette[style] |= curses.color_pair(pairs[colour])
        return palette
    except curses.error:
        return mono


def run_curses(wizard):
    """Run the curses renderer until the wizard is done or quit."""
    import curses

    def app(stdscr):
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        stdscr.keypad(True)
        palette = _palette(curses)

        def draw(width, height):
            stdscr.erase()
            view = wizard.view(width)
            for y, text, role, spans in layout_lines(view, width, height):
                if 0 <= y < height and text:
                    # leading spaces are the entry's column, so a panel line
                    # beside the table does not blank the row it shares
                    x = len(text) - len(text.lstrip(" "))
                    if x >= width - 1:
                        continue
                    try:
                        stdscr.addnstr(y, x, text[x:], max(1, width - 1 - x), palette[role])
                        # each span is drawn again over the line, in its own style
                        for start, end, style in spans:
                            if start < width - 1 and end > start:
                                stdscr.addnstr(y, start, text[start:end],
                                               width - 1 - start, palette[style])
                    except curses.error:
                        pass
            stdscr.refresh()

        while wizard.screen not in ("done", "quit"):
            height, width = stdscr.getmaxyx()
            if width < MIN_WIDTH or height < MIN_HEIGHT:
                stdscr.erase()
                try:
                    stdscr.addnstr(0, 0, "Please enlarge the terminal window "
                                   f"(minimum {MIN_WIDTH}x{MIN_HEIGHT}).", max(1, width - 1))
                except curses.error:
                    pass
                stdscr.refresh()
                code = stdscr.getch()
                if code == curses.KEY_RESIZE:
                    continue
                if code in (ord("q"), ord("Q")):
                    wizard.handle("q")
                continue
            draw(width, height)
            code = stdscr.getch()
            mapping = {curses.KEY_UP: "up", curses.KEY_DOWN: "down",
                       ord("k"): "up", ord("j"): "down", ord(" "): "space",
                       10: "enter", 13: "enter", curses.KEY_ENTER: "enter",
                       ord("b"): "b", ord("q"): "q", ord("y"): "y", ord("n"): "n",
                       ord("+"): "plus", ord("="): "plus", ord("-"): "minus",
                       ord("o"): "o", ord("O"): "o", ord("v"): "v", ord("V"): "v",
                       ord("x"): "x", ord("X"): "x",
                       # the review page moves the lane itself (ticket 28)
                       ord("J"): "lane-down", ord("K"): "lane-up",
                       curses.KEY_SF: "lane-down", curses.KEY_SR: "lane-up"}
            if ord("1") <= code <= ord("5"):
                key = chr(code)
            elif code in (ord("r"), ord("R")) and wizard.rescan_ready():
                # the scrub shells out and fetches, so the page says what it
                # is doing before `handle` runs it; a probe may print, so the
                # screen is painted whole afterwards
                key = "r"
                wizard.message = "rescanning…"
                draw(width, height)
                stdscr.clear()
            else:
                key = mapping.get(code, "other")
            if key == "o" and wizard.bench_page_path:
                # the page is written again first, so it opens on this session's
                # carry and Tier decisions and not the ones it started with
                message = wizard.rewrite_bench_page()
                if message:
                    wizard.message = message
                try:
                    import pathlib
                    import webbrowser
                    webbrowser.open(pathlib.Path(wizard.bench_page_path).as_uri())
                except Exception:
                    pass
            wizard.handle(key)
        return wizard.result()

    return curses.wrapper(app)
