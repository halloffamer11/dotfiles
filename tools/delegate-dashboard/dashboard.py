#!/usr/bin/env python3
"""Compact terminal dashboard for one pinned delegate project."""

from __future__ import annotations

import argparse
import json
import os
import select
import shutil
import sys
import termios
import tty

from model import DashboardError, DashboardModel


RESET = "\033[0m"
MUTED = "#8d8d89"
FOREGROUND = "#e7e7e7"
ERROR = "#d76563"
SUCCESS = "#78bd74"

KEY_SEQUENCES = (
    "\x1b[1;2A",
    "\x1b[1;2B",
    "\x1b[5~",
    "\x1b[6~",
    "\x1b[A",
    "\x1b[B",
)


def pop_key(pending, *, flush_escape=False):
    """Pop one key without dropping batched text or split terminal sequences."""
    if not pending:
        return None, pending
    if not pending.startswith("\x1b"):
        return pending[0], pending[1:]
    for sequence in KEY_SEQUENCES:
        if pending.startswith(sequence):
            return sequence, pending[len(sequence) :]
    if not flush_escape and any(sequence.startswith(pending) for sequence in KEY_SEQUENCES):
        return None, pending
    return "\x1b", pending[1:]


class PercentageEditor:
    """Small input editor backed by a model policy snapshot."""

    def __init__(self, model, field):
        self.model = model
        self.edit = model.begin_percentage_edit(field)
        self.text = self.edit.text
        self.pristine = True

    @property
    def label(self):
        return self.edit.field.title()

    def feed(self, key):
        """Consume one key; return whether the editor remains open."""
        if key == "\x1b":
            return False
        if key in ("\r", "\n"):
            self.model.save_percentage_edit(self.edit, self.text)
            return False
        if key in ("\x7f", "\b"):
            self.text = "" if self.pristine else self.text[:-1]
            self.pristine = False
        elif key == "\x15":
            self.text = ""
            self.pristine = False
        elif len(key) == 1 and key.isprintable():
            if self.pristine:
                self.text = ""
            self.text += key
            self.pristine = False
        return True


def foreground(hex_color: str) -> str:
    value = hex_color.removeprefix("#")
    return f"\033[38;2;{int(value[0:2], 16)};{int(value[2:4], 16)};{int(value[4:6], 16)}m"


def paint(text: str, color: str = FOREGROUND, *, bold: bool = False, width: int) -> str:
    text = text[: max(0, width)]
    weight = "\033[1m" if bold else ""
    return f"{weight}{foreground(color)}{text}{RESET}"


def percent(value):
    return "—" if value is None else f"{round(value * 100):g}%"


def pace(value):
    return "—" if value is None else f"{value:.2f}×"


def source_label(source, state):
    if not source:
        return "unknown"
    if source == state["project"]["policy"]:
        return "project:.delegate/routing.json"
    return f"global:{os.path.basename(source)}"


def order_label(row, state):
    """Effective Order with its catalog source, not a second sorting rule."""
    if row["order"] is None:
        return "—"
    source = row.get("order_source")
    mark = "?" if not source else "p" if source == state["project"]["policy"] else "g"
    return f"{row['order']}{mark}"


def body_lines(state, width, selected_lane=None):
    """Return semantic terminal lines; spacing is deliberately not a test seam."""
    lines = []
    for tier in state["tiers"]:
        color = tier["color"]
        leader = tier["leader"] or "none eligible"
        lines.append((f"┃ Tier {tier['tier']}   ◆ {leader}", color, True))
        if width >= 132:
            lines.append(
                (
                    "┃    Ord  Lane                     Model                Effort  "
                    "Harness  Meter             Rem   Pace   OK  Reason",
                    MUTED,
                    False,
                )
            )
        else:
            lines.append(("┃    Ord Lane · Model / Effort @ Harness · Meter", MUTED, False))
        if not tier["rows"]:
            lines.append(("┃    No carried lanes", MUTED, False))
        for row in tier["rows"]:
            leader_mark = "◆" if row["lane"] == tier["leader"] else "·"
            cursor_mark = ">" if row["lane"] == selected_lane else " "
            order = order_label(row, state)
            eligible = "yes" if row["eligible"] else "no"
            row_color = color if leader_mark == "◆" else FOREGROUND
            is_leader = leader_mark == "◆"
            if width >= 132:
                text = (
                    f"┃ {cursor_mark}{leader_mark} {order:>3}  {row['lane']:<24} "
                    f"{row['model']:<20} {row['effort']:<7} {row['harness']:<8} "
                    f"{row['meter']:<17} {percent(row['remaining']):>4}  "
                    f"{pace(row['pace']):>6}  {eligible:<3} {row['reason']}"
                )
                lines.append((text, row_color, is_leader))
            else:
                lines.append(
                    (
                        f"┃ {cursor_mark}{leader_mark} {order:>3} {row['lane']} · {row['model']} / "
                        f"{row['effort']} @ {row['harness']} · Meter {row['meter']}",
                        row_color,
                        is_leader,
                    )
                )
                lines.append(
                    (
                        f"┃       Remaining {percent(row['remaining'])} · Pace {pace(row['pace'])} · "
                        f"eligible {eligible} · {row['reason']}",
                        row_color,
                        is_leader,
                    )
                )
        lines.append(("", FOREGROUND, False))
    return lines


def compose(
    state,
    offset,
    width,
    height,
    selected_lane=None,
    *,
    follow_selection=True,
    editor=None,
):
    """Compose a clipped viewport with persistent project identity and key help."""
    gate = state["policy"]["gate"]
    margin = state["policy"]["margin"]
    project = state["project"]
    usage = state["usage"]
    header = [
        (f"Pinned project  {project['name']}  {project['root']}", FOREGROUND, True),
        ("Delegate project routing  /  prototype", FOREGROUND, True),
        ("Ord: p=project · g=global/fallback (derived from global Order/name)", MUTED, False),
        (
            f"Gate {gate['display']} [{source_label(gate['source'], state)}]   "
            f"Margin {margin['display']} [{source_label(margin['source'], state)}]",
            MUTED,
            False,
        ),
        (
            f"{usage['label']} · cached, display-only · {usage['status']} · {usage['path']}",
            MUTED if usage["status"] == "ok" else ERROR,
            False,
        ),
    ]
    if usage.get("detail"):
        header.append((usage["detail"], ERROR, False))
    if state.get("error"):
        header.append((state["error"], ERROR, True))
    if editor is not None:
        header.append(
            (
                f"Edit {editor.label} percentage (0–100): {editor.text}_  "
                "Enter save · Esc cancel",
                FOREGROUND,
                True,
            )
        )
    save = state.get("save", {})
    if save.get("status") != "idle" and save.get("detail"):
        color = SUCCESS if save["status"] == "saved" else ERROR
        header.append((save["detail"], color, save["status"] != "saved"))

    footer_height = 1
    if height <= footer_height:
        return [("j/k select · J/K move · r reload · q close", MUTED, False)], 0
    if height == 2:
        return [header[0], ("j/k select · J/K move · r reload · q close", MUTED, False)], 0

    max_header = max(1, height - footer_height - 1)
    header = header[:max_header]
    available = max(1, height - len(header) - footer_height)
    body = body_lines(state, width, selected_lane)
    max_offset = max(0, len(body) - available)
    offset = min(max(0, offset), max_offset)
    selected_line = next(
        (index for index, (text, _color, _bold) in enumerate(body) if text.startswith("┃ >")),
        None,
    )
    if follow_selection and selected_line is not None:
        if selected_line < offset:
            offset = selected_line
        elif selected_line >= offset + available:
            offset = selected_line - available + 1
    visible = body[offset : offset + available]
    extent = "all" if not body else f"{offset + 1}–{min(len(body), offset + available)}/{len(body)}"
    footer_text = (
        f"editing {editor.label} · type value · Enter save · Esc cancel [{extent}]"
        if editor is not None
        else f"jk/↑↓ select · JK/⇧↑↓ move · g Gate · m Margin · r reload · q close [{extent}]"
    )
    footer = [(footer_text, MUTED, False)]
    return header + visible + footer, offset


def draw(state, offset, selected_lane=None, *, follow_selection=True, editor=None):
    size = shutil.get_terminal_size((100, 30))
    lines, offset = compose(
        state,
        offset,
        size.columns,
        size.lines,
        selected_lane,
        follow_selection=follow_selection,
        editor=editor,
    )
    rendered = [paint(text, color, bold=bold, width=size.columns) for text, color, bold in lines]
    rendered.extend([""] * max(0, size.lines - len(rendered)))
    sys.stdout.write("\033[H" + "\033[K\n".join(rendered[: size.lines]) + "\033[K")
    sys.stdout.flush()
    return offset, len(body_lines(state, size.columns, selected_lane))


def carried_lane_names(state):
    return [row["lane"] for tier in state["tiers"] for row in tier["rows"]]


def run_terminal(model: DashboardModel) -> int:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        sys.stderr.write("dashboard: interactive view needs a terminal; use --json for diagnostics\n")
        return 2

    fd = sys.stdin.fileno()
    previous = termios.tcgetattr(fd)
    offset = 0
    names = carried_lane_names(model.state)
    selected = names[0] if names else None
    follow_selection = True
    editor = None
    pending = ""
    try:
        tty.setcbreak(fd)
        sys.stdout.write("\033[?1049h\033[?25l\033[2J")
        dirty = True
        while True:
            changed = model.refresh_if_changed()
            if changed:
                names = carried_lane_names(model.state)
                if selected not in names:
                    selected = names[0] if names else None
                follow_selection = True
                dirty = True
            if dirty:
                offset, total = draw(
                    model.state,
                    offset,
                    selected,
                    follow_selection=follow_selection,
                    editor=editor,
                )
                follow_selection = False
                dirty = False

            ready, _, _ = select.select([fd], [], [], 0.5)
            if not ready and not pending:
                continue
            if ready:
                pending += os.read(fd, 4096).decode("utf-8", errors="ignore")
            flush_escape = not ready
            while pending:
                key, pending = pop_key(pending, flush_escape=flush_escape)
                if key is None:
                    break
                if editor is not None:
                    if key == "\x03":
                        return 0
                    if not editor.feed(key):
                        editor = None
                    dirty = True
                    continue
                if key in ("q", "Q", "\x03"):
                    return 0
                names = carried_lane_names(model.state)
                selected_index = names.index(selected) if selected in names else 0
                if key in ("j", "\x1b[B") and names:
                    selected = names[min(len(names) - 1, selected_index + 1)]
                    follow_selection = True
                elif key in ("k", "\x1b[A") and names:
                    selected = names[max(0, selected_index - 1)]
                    follow_selection = True
                elif key in ("K", "\x1b[1;2A") and selected is not None:
                    model.move_lane(selected, -1)
                    follow_selection = True
                elif key in ("J", "\x1b[1;2B") and selected is not None:
                    model.move_lane(selected, 1)
                    follow_selection = True
                elif key in ("\x1b[6~", " "):
                    offset += 8
                elif key in ("\x1b[5~",):
                    offset = max(0, offset - 8)
                elif key == "g":
                    editor = PercentageEditor(model, "gate")
                elif key == "m":
                    editor = PercentageEditor(model, "margin")
                elif key == "G":
                    offset = max(0, total - 1)
                elif key in ("r", "R"):
                    model.refresh()
                dirty = True
    except KeyboardInterrupt:
        return 0
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, previous)
        sys.stdout.write("\033[0m\033[?25h\033[?1049l")
        sys.stdout.flush()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Open the delegate dashboard pinned to one Git project."
    )
    parser.add_argument("--cwd", required=True, help="directory inside the Git project to pin")
    parser.add_argument("--config-dir", help="directory containing delegate lanes.json and routing.json")
    parser.add_argument("--meters", help="cached Meter JSON file; never refreshed with vendor probes")
    parser.add_argument("--json", action="store_true", help="print one diagnostic model state and exit")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        model = DashboardModel(cwd=args.cwd, config_dir=args.config_dir, meters_path=args.meters)
    except DashboardError as exc:
        sys.stderr.write(f"dashboard: {exc}\n")
        return 1
    if args.json:
        json.dump(model.state, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0
    return run_terminal(model)


if __name__ == "__main__":
    raise SystemExit(main())
