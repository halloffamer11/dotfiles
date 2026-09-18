#!/usr/bin/env python3
"""Throwaway ANSI-stripped dump of proto_layout_strip. PROTOTYPE."""

from __future__ import annotations

import argparse
import re
import sys
from types import SimpleNamespace

from model import DashboardError, DashboardModel
from proto_layout_strip import cells, render


ANSI = re.compile(r"\033\[[0-9;]*m")
DEFAULT_CWD = (
    "/Users/dreiss/.herdr/worktrees/dotfiles/worktree-delegate-monitor-herdr-strip"
)


def strip_ansi(text: str) -> str:
    return ANSI.sub("", text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dump one rank-strip frame.")
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--select")
    parser.add_argument("--editor", choices=("gate", "margin"))
    parser.add_argument("--cwd", default=DEFAULT_CWD)
    args = parser.parse_args(argv)
    try:
        model = DashboardModel(cwd=args.cwd)
    except DashboardError as exc:
        sys.stderr.write(f"proto_strip_dump: {exc}\n")
        return 1
    selected = args.select
    if selected is None:
        for tier in model.state.get("tiers") or []:
            for row in tier.get("rows") or []:
                selected = row["lane"]
                break
            if selected:
                break
    editor = None
    if args.editor:
        policy = (model.state.get("policy") or {}).get(args.editor) or {}
        editor = SimpleNamespace(
            field=args.editor,
            text=str(policy.get("display") or "").removesuffix("%") or "0",
        )
    view: dict = {}
    frame = render(
        model.state,
        width=args.width,
        height=args.height,
        selected_lane=selected,
        editor=editor,
        message="",
        view=view,
    )
    if len(frame) != args.height:
        sys.stderr.write(f"proto_strip_dump: height {len(frame)} != {args.height}\n")
    for line in frame:
        plain = strip_ansi(line)
        wide = cells(plain)
        if wide > args.width:
            sys.stderr.write(f"proto_strip_dump: line {wide}c > {args.width}\n")
        sys.stdout.write(plain + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
