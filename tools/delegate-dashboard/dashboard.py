#!/usr/bin/env python3
"""Compact read-only terminal dashboard for one pinned delegate project."""

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


def body_lines(state, width):
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
            order = "—" if row["order"] is None else str(row["order"])
            eligible = "yes" if row["eligible"] else "no"
            row_color = color if leader_mark == "◆" else FOREGROUND
            is_leader = leader_mark == "◆"
            if width >= 132:
                text = (
                    f"┃ {leader_mark}  {order:>3}  {row['lane']:<24} "
                    f"{row['model']:<20} {row['effort']:<7} {row['harness']:<8} "
                    f"{row['meter']:<17} {percent(row['remaining']):>4}  "
                    f"{pace(row['pace']):>6}  {eligible:<3} {row['reason']}"
                )
                lines.append((text, row_color, is_leader))
            else:
                lines.append(
                    (
                        f"┃ {leader_mark} {order:>3} {row['lane']} · {row['model']} / "
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


def compose(state, offset, width, height):
    """Compose a clipped viewport with persistent project identity and key help."""
    gate = state["policy"]["gate"]
    margin = state["policy"]["margin"]
    project = state["project"]
    usage = state["usage"]
    header = [
        (f"Pinned project  {project['name']}  {project['root']}", FOREGROUND, True),
        ("Delegate project routing  /  prototype · read-only", FOREGROUND, True),
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

    footer_height = 1
    if height <= footer_height:
        return [("j/k scroll · r reload · q close", MUTED, False)], 0
    if height == 2:
        return [header[0], ("j/k scroll · r reload · q close", MUTED, False)], 0

    max_header = max(1, height - footer_height - 1)
    header = header[:max_header]
    available = max(1, height - len(header) - footer_height)
    body = body_lines(state, width)
    max_offset = max(0, len(body) - available)
    offset = min(max(0, offset), max_offset)
    visible = body[offset : offset + available]
    extent = "all" if not body else f"{offset + 1}–{min(len(body), offset + available)}/{len(body)}"
    footer = [(f"j/k or ↑/↓ scroll · PgUp/PgDn · r reload · q close   [{extent}]", MUTED, False)]
    return header + visible + footer, offset


def draw(state, offset):
    size = shutil.get_terminal_size((100, 30))
    lines, offset = compose(state, offset, size.columns, size.lines)
    rendered = [paint(text, color, bold=bold, width=size.columns) for text, color, bold in lines]
    rendered.extend([""] * max(0, size.lines - len(rendered)))
    sys.stdout.write("\033[H" + "\033[K\n".join(rendered[: size.lines]) + "\033[K")
    sys.stdout.flush()
    return offset, len(body_lines(state, size.columns))


def run_terminal(model: DashboardModel) -> int:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        sys.stderr.write("dashboard: interactive view needs a terminal; use --json for diagnostics\n")
        return 2

    fd = sys.stdin.fileno()
    previous = termios.tcgetattr(fd)
    offset = 0
    try:
        tty.setcbreak(fd)
        sys.stdout.write("\033[?1049h\033[?25l\033[2J")
        dirty = True
        while True:
            changed = model.refresh_if_changed()
            if changed:
                dirty = True
            if dirty:
                offset, total = draw(model.state, offset)
                dirty = False

            ready, _, _ = select.select([fd], [], [], 0.5)
            if not ready:
                continue
            key = os.read(fd, 16).decode("utf-8", errors="ignore")
            if key in ("q", "Q", "\x03"):
                return 0
            if key in ("j", "\x1b[B"):
                offset += 1
            elif key in ("k", "\x1b[A"):
                offset = max(0, offset - 1)
            elif key in ("\x1b[6~", " "):
                offset += 8
            elif key in ("\x1b[5~",):
                offset = max(0, offset - 8)
            elif key == "g":
                offset = 0
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
        description="Open the read-only delegate dashboard pinned to one Git project."
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
