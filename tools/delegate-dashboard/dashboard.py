#!/usr/bin/env python3
"""Compact terminal dashboard for one pinned delegate project.

The host and the view are split.  This host owns the model, the selected Lane,
the percentage editors and the keys ``j``/``k`` and arrows, ``J``/``K``, ``g``,
``m``, ``r`` and ``q``.  Every other key goes to the view's ``handle_key``; a
view that returns a carried Lane name from it also moves the selection to that
Lane.  The view's ``selectable(state, view)`` names the Lanes ``j``/``k`` may
stop on, so rows it hides are never walked.  A ``handle_key`` that accepts a
``model`` keyword is handed this host's :class:`DashboardModel`, which is how
the view reaches a save path of its own.

``deck`` is the view.  It is imported directly, so the host has no layout
argument and no layout key.
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import select
import shutil
import sys
import termios
import tty

import deck
from model import DashboardError, DashboardModel


# Left, right and Shift+Tab join the list so the parser reads them as one key.
# Until they did, each one reached the view as the three keys ESC, '[' and a
# letter, so an arrow acted as the letter it ends with.
KEY_SEQUENCES = (
    "\x1b[1;2A",
    "\x1b[1;2B",
    "\x1b[5~",
    "\x1b[6~",
    "\x1b[A",
    "\x1b[B",
    "\x1b[C",
    "\x1b[D",
    "\x1b[Z",
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
    def field(self):
        """The policy field this editor writes: 'gate' or 'margin'."""
        return self.edit.field

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


def draw(module, state, width, height, *, selected_lane, editor, message, view):
    """Ask the view for a frame and write exactly `height` lines."""
    try:
        lines = list(
            module.render(
                state,
                width=width,
                height=height,
                selected_lane=selected_lane,
                editor=editor,
                message=message,
                view=view,
            )
        )
    except Exception as exc:  # a failed frame must not take the host down
        lines = [f"view {module.NAME} failed to render: {type(exc).__name__}: {exc}"]
    lines.extend([""] * max(0, height - len(lines)))
    sys.stdout.write("\033[H" + "\033[K\n".join(lines[:height]) + "\033[K")
    sys.stdout.flush()


def carried_lane_names(state):
    return [row["lane"] for tier in state["tiers"] for row in tier["rows"]]


def walkable_lane_names(module, state, view):
    """The carried Lane names ``j``/``k`` may stop on in the current body.

    A view that hides rows -- a folded Tier, say -- exposes
    ``selectable(state, view)`` and names the stops it paints, so one press
    leaves a fold and no press ever walks a hidden row.  Without the hook every
    carried Lane is a stop.
    """
    carried = carried_lane_names(state)
    chooser = getattr(module, "selectable", None)
    if chooser is None:
        return carried
    try:
        names = [name for name in chooser(state, view) if name in carried]
    except Exception:  # the same rule as a failed render: never stop the host
        return carried
    return names or carried


def call_handle_key(handler, key, state, view, model):
    """Call the view's ``handle_key``, handing it the model if it asks for one.

    A key that writes -- the Tier move on ``H``/``L`` -- needs the model's save
    path.  A handler that takes only ``(key, state, view)`` is called with
    exactly those three.
    """
    try:
        params = inspect.signature(handler).parameters
        wants_model = "model" in params or any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in params.values()
        )
    except (TypeError, ValueError):
        wants_model = False
    if wants_model:
        return handler(key, state, view, model=model)
    return handler(key, state, view)


def run_terminal(model: DashboardModel) -> int:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        sys.stderr.write("dashboard: interactive view needs a terminal; use --json for diagnostics\n")
        return 2

    message = ""
    view = {}

    fd = sys.stdin.fileno()
    previous = termios.tcgetattr(fd)
    names = carried_lane_names(model.state)
    selected = names[0] if names else None
    editor = None
    pending = ""
    try:
        tty.setcbreak(fd)
        sys.stdout.write("\033[?1049h\033[?25l\033[2J")
        dirty = True
        while True:
            if model.refresh_if_changed():
                names = carried_lane_names(model.state)
                if selected not in names:
                    selected = names[0] if names else None
                dirty = True
            if dirty:
                size = shutil.get_terminal_size((100, 30))
                draw(
                    deck,
                    model.state,
                    size.columns,
                    size.lines,
                    selected_lane=selected,
                    editor=editor,
                    message=message,
                    view=view,
                )
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
                message = ""
                names = walkable_lane_names(deck, model.state, view)
                selected_index = names.index(selected) if selected in names else 0
                if key in ("j", "\x1b[B") and names:
                    selected = names[min(len(names) - 1, selected_index + 1)]
                elif key in ("k", "\x1b[A") and names:
                    selected = names[max(0, selected_index - 1)]
                elif key in ("K", "\x1b[1;2A") and selected is not None:
                    model.move_lane(selected, -1)
                elif key in ("J", "\x1b[1;2B") and selected is not None:
                    model.move_lane(selected, 1)
                elif key == "g":
                    editor = PercentageEditor(model, "gate")
                elif key == "m":
                    editor = PercentageEditor(model, "margin")
                elif key in ("r", "R"):
                    model.refresh()
                else:
                    handler = getattr(deck, "handle_key", None)
                    if handler is not None:
                        try:
                            used = call_handle_key(
                                handler, key, model.state, view, model
                            )
                        except Exception as exc:
                            used = None
                            message = (
                                f"view {deck.NAME} key {key!r} failed: "
                                f"{type(exc).__name__}: {exc}"
                            )
                        # A Lane name is truthy, so a boolean return still works.
                        if isinstance(used, str) and used in names:
                            selected = used
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
        json.dump(model.state, sys.stdout, indent=2, ensure_ascii=False, allow_nan=False)
        sys.stdout.write("\n")
        return 0
    return run_terminal(model)


if __name__ == "__main__":
    raise SystemExit(main())
