#!/usr/bin/env python3
"""Selectable terminal setup UI for delegate catalogs."""
import copy

from bench import EPOCH_BENCHMARKS
from catalog import CLASSES, EFFORTS, HARNESSES, resolve_published_model

# These render as single lines in an 80-column terminal, where anything past
# column 79 is clipped. Keep each one under that; a legend cut mid-sentence
# explains nothing.
TIER_ONELINER = "Tier: capability 1-4; a class takes lanes from its floor up to its ceiling."
PACE_LEGEND = "pace = unspent quota vs time left in the week. Above 1.0 it will expire unused."
CLASSES_LEGEND = "classes: each class has a floor and ceiling tier (1-4)."
# One gesture flips the box, and it is the same gesture on the carry screen and
# on the tier screens, so each footer names it the same way. The box means
# something different on each screen — the column header says which — but the
# key that moves it never changes.
FLIP_KEYS = "space/x: flip"
TIER_FOOTER = f"↑/↓/j/k: move  {FLIP_KEYS}  enter: next  b: back  o: bench  q: quit"
# Both of these describe a line the human cannot decide anything about, so each
# one is earned by such a line being on screen; neither is standing furniture.
TIER_ASSIGNED_LEGEND = "dim [n]: already taken at tier n, so that line has no decision left."
TIER_OFF_LEGEND = "off: not carried — you said so on the carry screen. It still takes a tier."
PRESCREEN_FOOTER = f"↑/↓ or j/k: move  {FLIP_KEYS}  enter: continue  b: back  q: quit"
NO_DATA_MESSAGE = "No per-effort data was supplied, so nothing else could be judged."
CONFIRM_OFF_LEGEND = "off: written with enabled: false.  On lanes omit the key."

# A reason has to fit the `why` column, and the column has to fit beside the
# lane, the model and the effort in 80 places. So each reason is a phrase that
# is whole at about twenty characters, and the sentence it used to be is a
# legend line that appears only on the screens where that phrase appears. A
# reason cut mid-word explains no more than a legend cut mid-sentence does.
DOMINATED_LEGEND = "X wins on S: effort X scores ≥ at ≤ cost on most of source S's benchmarks."
ABSENCE_LEGEND = "Absence of data is not evidence against a lane, so those stay on."
RECORDED_LEGEND = '"in the catalog": you recorded that already; the pre-screen leaves it.'
ULTRA_LEGEND = "ultra: no source scores it, and auto-delegation breaks the worker preamble."
NO_ROWS_REASON = "no rows for this lane"
NO_DATA_REASON = "no per-effort data"
NOT_DOMINATED_REASON = "not dominated"
ULTRA_REASON = "ultra, never carried"


def dominated_reason(effort, source):
    """The reason for a lane another effort dominates: `high wins on aa`.

    It names the source because two sources can disagree about one lane, and it
    is not "dominated by high (tbench)" because that is 26 places and the `why`
    column has 21 at 80 columns; `medium wins on tbench`, the longest, is 21.
    """
    return f"{effort} wins on {source}"


def is_dominated_reason(why):
    """Whether a proposal's reason is the data switching the lane off."""
    return isinstance(why, str) and " wins on " in why


def recorded_reason(enabled):
    """The reason shown for a lane whose `enabled` the human already wrote."""
    return f"{'on' if enabled else 'off'} in the catalog"


def resolve_effort_rows(lanes_doc, effort_rows):
    """Returns (rows keyed by catalog model, published names that name no lane).

    A source prints a model however it pleases: `gpt-5.6-luna` from SWE Refactor
    Bench, `GPT-6 Astra` from Terminal-Bench and Artificial Analysis. Every
    comparison below is against `lane["model"]`, so each row is re-keyed to the
    lane model its printed name denotes, and the catalog owns that mapping
    (`catalog.resolve_published_model`). A row naming no lane model is dropped
    rather than reported per lane: the leaderboards carry GLM-5.3, Opus 4.8,
    Sonnet 5 and a dozen others that are nobody's lane, and one line naming them
    all is what a human needs to spot a `published_as` they still owe us.
    """
    resolved, unmatched = [], []
    for row in effort_rows or []:
        if not isinstance(row, dict):
            continue
        model = resolve_published_model(row.get("model"), lanes_doc)
        if model is None:
            name = row.get("model")
            if isinstance(name, str) and name.strip() and name not in unmatched:
                unmatched.append(name)
            continue
        if model == row.get("model"):
            resolved.append(row)
        else:
            copied = dict(row)
            copied["model"] = model
            resolved.append(copied)
    return resolved, unmatched


def unmatched_message(unmatched, width=79):
    """One line naming the published models no lane runs, or "" for none."""
    if not unmatched:
        return ""
    head = "no lane runs these, ignored: "
    shown = []
    for name in unmatched:
        candidate = shown + [name]
        more = len(unmatched) - len(candidate)
        tail = f" +{more} more" if more else ""
        if len(head + ", ".join(candidate) + tail) > width:
            break
        shown.append(name)
    if not shown:
        count = len(unmatched)
        phrase = "name matches" if count == 1 else "names match"
        return f"{count} published {phrase} no lane; each is too long to print here"
    more = len(unmatched) - len(shown)
    return head + ", ".join(shown) + (f" +{more} more" if more else "")


def certain_effort_rows(effort_rows):
    """Rows that may dominate. Uncertain rows inform nothing: they must not
    dominate another lane, and they are not evidence against the lane they name.

    A row at an effort no lane can select is dropped for the same reason. The
    benchmark harnesses drive the API enum, which runs `none` to `max`, so every
    published sweep carries a `none` row — and no lane can be configured at
    `none`. Letting one dominate would switch off a real lane on the strength of
    a setting that cannot be chosen, which is exactly what it did to
    luna-low@codex: equal score to `none` at a tenth of a cent more.

    A `composite` row is a reader's figure, not evidence: Artificial Analysis
    does not publish the weighting of its Intelligence Index, so it is shown and
    never counted.
    """
    certain = []
    for row in effort_rows or []:
        if not isinstance(row, dict) or row.get("uncertain") or row.get("composite"):
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


def _beats(other, row):
    """At least the score for no more money, and strictly better in one of the two."""
    return (other["score"] >= row["score"] and other["cost_usd"] <= row["cost_usd"]
            and (other["score"] > row["score"] or other["cost_usd"] < row["cost_usd"]))


def dominating_effort(model, effort, source, certain):
    """The effort of `model` that dominates `effort` inside one source, or None.

    Dominated means another effort of the same model beats it on more than half
    of the benchmarks that source scored both on. A source with one benchmark —
    Terminal-Bench, SWE Refactor Bench — comes down to that one comparison.
    Artificial Analysis scores eight components off the same runs, and losing
    one noisy component in eight is not reason enough to switch a lane off: on
    the live page of 2026-09-11 that reading proposed twelve lanes off, nine of
    them on a single component.
    """
    mine, theirs = {}, {}
    for row in certain:
        if row.get("model") != model or row.get("source") != source:
            continue
        if row.get("effort") == effort:
            mine.setdefault(row.get("benchmark"), row)
        else:
            theirs.setdefault(row["effort"], {}).setdefault(row.get("benchmark"), row)
    for other_effort, board in theirs.items():
        shared = [benchmark for benchmark in mine if benchmark in board]
        wins = sum(1 for benchmark in shared if _beats(board[benchmark], mine[benchmark]))
        if shared and 2 * wins > len(shared):
            return other_effort
    return None


def dominating_row(row, certain):
    """The dominating effort's point on this row's own board, or None.

    The judgement belongs to the effort over its whole source
    (`dominating_effort`), so every point of a dominated effort is marked on
    every board of that source, including a board where it happens to score
    higher: the lane is off over the source, not over one chart.

    Public because the benchmark page draws this rule: a point it shows hollow
    has to be a point the pre-screen switched a lane off over, and two
    implementations of one rule would eventually disagree in front of a human
    trying to check the wizard's arithmetic.
    """
    other = dominating_effort(row.get("model"), row.get("effort"), row.get("source"), certain)
    if other is None:
        return None
    board = (row.get("source"), row.get("benchmark"))
    return next((r for r in certain
                 if r.get("model") == row.get("model") and r.get("effort") == other
                 and (r.get("source"), r.get("benchmark")) == board), None)


def _first_domination(lane, certain):
    """(effort, source) of the first source in which another effort dominates
    this lane, else None."""
    sources = []
    for row in certain:
        if row.get("model") == lane["model"] and row.get("effort") == lane["effort"]:
            if row.get("source") not in sources:
                sources.append(row.get("source"))
    for source in sources:
        other = dominating_effort(lane["model"], lane["effort"], source, certain)
        if other is not None:
            return other, source
    return None


def propose_enabled(lanes_doc, effort_rows):
    """Ticket-15 pre-screen rule. Returns {name: (enabled, reason)}."""
    rows, _unmatched = resolve_effort_rows(lanes_doc, effort_rows)
    certain = certain_effort_rows(rows)
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
            enabled = bool(lane["enabled"])
            out[name] = (enabled, recorded_reason(enabled))
            continue
        found = _first_domination(lane, certain)
        if found is not None:
            other, source = found
            out[name] = (False, dominated_reason(other, source))
            continue
        if not supplied:
            out[name] = (True, NO_DATA_REASON)
        elif not any(
            not row.get("uncertain")
            and row.get("model") == lane["model"]
            and row.get("effort") == lane["effort"]
            for row in rows
        ):
            out[name] = (True, NO_ROWS_REASON)
        else:
            out[name] = (True, NOT_DOMINATED_REASON)
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
        _rows, self._unmatched = resolve_effort_rows(self.lanes_doc, effort_rows)
        proposals = propose_enabled(self.lanes_doc, effort_rows)
        self._enabled = {name: enabled for name, (enabled, _) in proposals.items()}
        self._reasons = {name: reason for name, (_, reason) in proposals.items()}

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
        # The models no lane runs are a note about the data, so they read as a
        # legend line. The message slot is bold and sits below the footer, where
        # `every lane needs a tier` goes: a standing note there reads as an
        # error the human has just caused.
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
            elif key in ("x", "space") and names:
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
            elif key in ("space", "x"):
                # The only decision this screen makes. Carrying a lane is the
                # carry screen's decision, and `b` from tier 4 goes back to it;
                # making it here as well asked the human the same question twice
                # and gave the box on this line two meanings.
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
            elif key == "b" and self.tier == 4:
                self._enter_prescreen()
            return
        if self.screen == "routing":
            count = len(CLASSES) * 2 + 2
            if key == "up":
                self.cursor = (self.cursor - 1) % count
            elif key == "down":
                self.cursor = (self.cursor + 1) % count
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
                for name in list(self._assigned):
                    if self._assigned[name] == 1:
                        del self._assigned[name]
                self._enter_tier(1)
            return
        if self.screen == "confirm":
            # The list of what is about to be written is longer than a short
            # window: at 80x24 eleven of twenty items showed, and the nine out
            # of sight included both file paths and every routing value. A
            # confirm screen you cannot read to the end is not one.
            count = len(self.lanes_doc["lanes"]) + len(CLASSES) * 2 + 4
            if key == "up":
                self.cursor = (self.cursor - 1) % count
                return
            if key == "down":
                self.cursor = (self.cursor + 1) % count
                return
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
                values.append("—" if value is None else (str(int(value)) if value == int(value) else f"{value:.1f}"))
            values.append((aa or {}).get("mean_s") or "—")
        return values

    def _frame(self, screen, title, *, tier=None, columns=None, rows=None,
               footer="", body=None, legend=None, elastic=""):
        return {
            "screen": screen, "title": title, "tier": tier,
            "columns": columns or [], "rows": rows or [],
            "footer": footer, "message": self.message,
            "body": body or [], "legend": legend or [],
            "steps": self._step_marker(), "elastic": elastic,
        }

    def _prescreen_legend(self):
        """Explain the reasons that are on this screen, and no others.

        Each reason in the `why` column is a phrase; the sentence it stands for
        is here. Listing the sentences unconditionally would push the lane rows
        off a short window to explain a case that is not on screen, so each line
        is earned by a reason that is actually shown.
        """
        reasons = [self._reasons[name] for name in self._lane_names()]
        lines = [DOMINATED_LEGEND]
        if any(r in (NO_ROWS_REASON, NO_DATA_REASON) for r in reasons):
            lines.append(ABSENCE_LEGEND)
        # a `published_as` still owed to us shows up here and nowhere else
        ignored = unmatched_message(self._unmatched) if self.effort_rows else ""
        if ignored:
            lines.append(ignored)
        if any(r == ULTRA_REASON for r in reasons):
            lines.append(ULTRA_LEGEND)
        if any(r.endswith("in the catalog") for r in reasons):
            lines.append(RECORDED_LEGEND)
        return lines

    def _tier_legend(self):
        """Explain the lines on this screen that carry state instead of a choice.

        `[n]` and `off` are both facts arriving from an earlier screen, not
        controls, and a reader has to be able to tell them from the `[x]` this
        screen does answer. Each line is earned by such a row being on screen,
        the way the pre-screen legend is: standing furniture explaining a case
        that is not there costs the rows their room on a short window.
        """
        lines = []
        if self._assigned:
            lines.append(TIER_ASSIGNED_LEGEND)
        if any(not self._enabled[name] for name in self.lanes_doc["lanes"]):
            lines.append(TIER_OFF_LEGEND)
        # The tier definition is reference, so it goes last: last renders
        # directly above the footer, where it reads as a second footer line, and
        # it is the first line a short window gives up.
        lines.append(TIER_ONELINER)
        return lines

    def _tier_map_lines(self):
        by_tier = {tier: [] for tier in range(1, 5)}
        for name, tier in self._assigned.items():
            by_tier[tier].append(name)
        lines = []
        for tier in range(1, 5):
            names = sorted(by_tier[tier])
            if not names:
                lines.append(f"tier {tier} (0): (none)")
            else:
                # five lanes on one tier already ran past column 80 and were cut
                # after a comma, which reads as a list that stops for no reason
                lines.append(self._drift_line(f"tier {tier}", names, always_count=True))
        return lines

    @staticmethod
    def _fit(line):
        """One width rule for every start-screen line: the renderer clips at 79."""
        return line if len(line) <= 79 else line[:76] + "..."

    def _drift_line(self, label, items, always_count=False):
        """`label (n): a, b (+k more)`, filled to the width and no further.

        `always_count` keeps the count on a list of one, for a block of lines
        read together — the tier map — where a line without it reads as a
        different kind of line.
        """
        total = len(items)
        if total == 1 and not always_count:
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
                "Tier is capability, 1 to 4. Each class takes lanes from its floor tier",
                "up to its ceiling tier, as set in routing.json. It is not computed; it",
                "is your judgement. Lanes alike on tier are equivalent; pace separates them.",
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
                })
            return self._frame(
                "prescreen", "Lanes to carry",
                columns=["carry", "lane", "model", "effort", "why"],
                rows=rows,
                footer=PRESCREEN_FOOTER,
                legend=self._prescreen_legend(),
                elastic="why",
            )
        if self.screen == "tier":
            epoch_names, aa_names = self._bench_columns()
            columns = ["mark", "lane", "model", "effort", *epoch_names, "Epoch mean rank"]
            if aa_names:
                columns.extend([*aa_names, "AA mean rank"])
            active, dimmed = self._tier_names()
            rows = []
            for index, name in enumerate(active + dimmed):
                lane = self.lanes_doc["lanes"][name]
                is_assigned = name in self._assigned
                is_off = not self._enabled[name]
                marked = name in self._marks[self.tier] if not is_assigned else False
                # The tier a lane already went to belongs in the box, not in a
                # tag after the table: a tag is rendered past the last column and
                # then clipped, so `tier 3` reached the eye as `ti`. `[3]` is the
                # same fact in the width the box already has, and it leaves `off`
                # as the only tag, which fits. A digit is not a third state of
                # the tick: dimmed, and with the legend line it earns, it says
                # the line is spoken for and this screen asks nothing of it.
                if is_assigned:
                    box = f"[{self._assigned[name]}]"
                else:
                    box = "[x]" if marked else "[ ]"
                # `off` is state carried in from the carry screen, not a control
                # on this one: dimmed, tagged, and answered nowhere but there.
                tag = "off" if is_off else ""
                rows.append({
                    "cells": [box, name, lane["model"], lane["effort"],
                              *self._bench_cells(name, epoch_names, aa_names)],
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
                # truncated footer loses the keys.
                legend=self._tier_legend(),
            )
        if self.screen == "routing":
            values = []
            for name in CLASSES:
                cls_info = self.routing_doc["classes"][name]
                values.append((f"classes.{name}.floor", cls_info["floor"]))
                values.append((f"classes.{name}.ceiling", cls_info["ceiling"]))
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
            # `carry` sits between the item and its value so that `value`, the
            # one column with a path in it, is last: an elastic column pads to
            # the widest row it holds, and a 40-place path column with `tier 4`
            # in it opened a river of blanks across every other line.
            for name in self.lanes_doc["lanes"]:
                off = not self._enabled[name]
                # the column says `off`; a tag saying it again read `off  off`
                rows.append({"cells": [name, "off" if off else "",
                                        f"tier {self._assigned[name]}"],
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
            for path in (self.lanes_path, self.routing_path):
                rows.append({"cells": ["file", "", path], "marked": False,
                             "dimmed": False, "tag": ""})
            for index, row in enumerate(rows):
                row["cursor"] = index == self.cursor
            return self._frame(
                "confirm", "Confirm changes",
                columns=["item", "carry", "value"], rows=rows,
                footer="↑/↓ or j/k: read on  y: write  n/q: quit without writing  b: back",
                # a path is the one value here that will not fit a 24-place cell,
                # and `/Users/dreiss/.config/de…` is not a path anyone can check
                elastic="value",
                legend=[CLASSES_LEGEND, *self._margin_legend(),
                        *self._gate_legend(), CONFIRM_OFF_LEGEND],
            )
        return self._frame(self.screen, "Delegate setup")


MIN_ELASTIC = 12


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
    priority_names = ("mark", "carry", "lane", "Epoch mean rank")
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
    for i in priority + rest + deferred:
        cell_width = min(_natural_width(view, i), 24)
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


def layout_lines(view, width, height):
    """Place one frame on a character grid: [(row, text, role)].

    Separated from the curses call so a test can read the screen a human sees.
    Every fault this function now guards against — a reason column silently
    dropped, a tag clipped to `ti`, rows scrolled away with nothing to say so —
    was invisible to tests that only ever read the frame dict.
    """
    lines = []
    rows = view["rows"]
    tag_room = max([len(row["tag"]) for row in rows], default=0)
    chosen, widths = _fit_table(view, width - (tag_room + 2 if tag_room else 0))
    body = view.get("body") or []
    legend = list(view.get("legend") or [])
    footer_y = height - 3
    steps = view.get("steps") or ""
    steps_y = footer_y - 1 if steps else footer_y
    table_floor = 2 + (1 if view["columns"] else 0) + min(len(rows), ROW_FLOOR)
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
        lines.append((y, line, "body"))
        y += 1
    first, shown = 0, 0
    if chosen and y < legend_y:
        if body:
            y += 1
        if y < legend_y:
            lines.append((y, "  ".join(_clip(view["columns"][i], w).ljust(w)
                                      for i, w in zip(chosen, widths)), "header"))
            y += 1
        room = max(1, legend_y - y)
        cursor_index = next((i for i, row in enumerate(rows) if row["cursor"]), 0)
        if cursor_index >= room:
            first = cursor_index - room + 1
        for row in rows[first:]:
            if y >= legend_y:
                break
            cells = []
            for i, w in zip(chosen, widths):
                cell = row["cells"][i] if i < len(row["cells"]) else ""
                cells.append(_clip(cell, w).ljust(w))
            line = "  ".join(cells)
            if row["tag"]:
                line += "  " + row["tag"]
            role = "row-cursor" if row["cursor"] else "row"
            if row["dimmed"]:
                role += "-dim"
            lines.append((y, line, role))
            y += 1
            shown += 1

    title = view["title"]
    if shown and shown < len(rows):
        # a window too short for the list said nothing about it, so eight lanes
        # looked like the whole catalog
        note = f"{first + 1}-{first + shown} of {len(rows)}"
        gap = width - 1 - len(title) - len(note)
        title = title + " " * gap + note if gap >= 2 else f"{title}  {note}"
    lines.append((0, title, "title"))
    for offset, line in enumerate(legend):
        lines.append((legend_y + offset, line, "legend"))
    if steps:
        lines.append((steps_y, steps, "steps"))
    lines.append((footer_y, view["footer"], "footer"))
    lines.append((height - 2, view["message"], "message"))
    return lines


def run_curses(wizard):
    """Run the curses renderer until the wizard is done or quit."""
    import curses

    def app(stdscr):
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        stdscr.keypad(True)
        roles = {
            "title": curses.A_BOLD, "header": curses.A_BOLD,
            "steps": curses.A_BOLD, "message": curses.A_BOLD,
            "body": 0, "legend": 0, "footer": 0, "row": 0,
            "row-dim": curses.A_DIM,
            "row-cursor": curses.A_REVERSE | curses.A_BOLD,
            "row-cursor-dim": curses.A_DIM | curses.A_REVERSE | curses.A_BOLD,
        }
        while wizard.screen not in ("done", "quit"):
            stdscr.erase()
            height, width = stdscr.getmaxyx()
            if width < MIN_WIDTH or height < MIN_HEIGHT:
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
            view = wizard.view()
            for y, text, role in layout_lines(view, width, height):
                if 0 <= y < height and text:
                    try:
                        stdscr.addnstr(y, 0, text, max(1, width - 1), roles[role])
                    except curses.error:
                        pass
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
