#!/usr/bin/env python3
"""PROTOTYPE: print one layout frame with ANSI stripped, for width checks.

Throwaway.  It exists to prove that no painted line is wider than the pane and
that every column of the grid starts at the same cell on every Lane row.

    python3 proto_dump.py --layout panel --width 131 --height 24
    python3 proto_dump.py --layout panel --width 52 --height 24 --check
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata

from dashboard import DEFAULT_LAYOUT, carried_lane_names, discover_layouts
from model import DashboardError, DashboardModel


ANSI = re.compile(r"\033\[[0-9;]*m")
REPO_DEFAULT = "."


class FakeEditor:
    """Stands in for PercentageEditor; the contract asks only for these two."""

    def __init__(self, field, text):
        self.field = field
        self.text = text


def strip(text):
    return ANSI.sub("", text)


def cells(text):
    total = 0
    for char in text:
        if unicodedata.combining(char):
            continue
        total += 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
    return total


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", default=REPO_DEFAULT, help="directory inside the Git project to pin")
    parser.add_argument("--layout", default=DEFAULT_LAYOUT)
    parser.add_argument("--width", type=int, default=131)
    parser.add_argument("--height", type=int, default=24)
    parser.add_argument("--select", help="Lane to select; the first carried Lane by default")
    parser.add_argument("--editor", choices=("gate", "margin"), help="draw with an editor open")
    parser.add_argument("--editor-text", default="25")
    parser.add_argument("--keys", default="", help="keys to feed handle_key before drawing")
    parser.add_argument("--message", default="")
    parser.add_argument("--check", action="store_true", help="report over-wide lines and exit non-zero")
    args = parser.parse_args(argv)

    layouts, failures = discover_layouts()
    if args.layout not in layouts:
        sys.stderr.write(f"proto_dump: no layout '{args.layout}'; have {sorted(layouts)}\n")
        if failures:
            sys.stderr.write(f"proto_dump: skipped {failures}\n")
        return 2
    module = layouts[args.layout]

    try:
        model = DashboardModel(cwd=args.cwd)
    except DashboardError as exc:
        sys.stderr.write(f"proto_dump: {exc}\n")
        return 1

    names = carried_lane_names(model.state)
    selected = args.select or (names[0] if names else None)
    view = {}
    handler = getattr(module, "handle_key", None)
    if args.keys:
        # The host always draws before it reads a key, so a variant may keep the
        # selection in `view`.  Draw one frame first, or a key sees an empty view.
        module.render(
            model.state,
            width=args.width,
            height=args.height,
            selected_lane=selected,
            editor=None,
            message="",
            view=view,
        )
    for key in args.keys:
        if handler is None:
            break
        used = handler(key, model.state, view)
        if isinstance(used, str) and used in names:
            selected = used

    editor = FakeEditor(args.editor, args.editor_text) if args.editor else None
    lines = module.render(
        model.state,
        width=args.width,
        height=args.height,
        selected_lane=selected,
        editor=editor,
        message=args.message,
        view=view,
    )

    over = []
    for number, painted in enumerate(lines, start=1):
        plain = strip(painted)
        if cells(plain) > args.width:
            over.append((number, cells(plain), plain))
        if not args.check:
            print(plain)
    if len(lines) != args.height:
        sys.stderr.write(f"proto_dump: got {len(lines)} lines, wanted {args.height}\n")
        return 1
    if over:
        for number, got, plain in over:
            sys.stderr.write(f"proto_dump: line {number} is {got} cells: {plain!r}\n")
        return 1
    if args.check:
        print(f"{args.layout} {args.width}x{args.height}: {len(lines)} lines, none over {args.width} cells")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
