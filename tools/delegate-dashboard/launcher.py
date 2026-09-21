#!/usr/bin/env python3
"""Resolve Herdr's launch project and replace this process with the dashboard."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Optional


PLUGIN_ROOT = Path(__file__).resolve().parent
DASHBOARD_PATH = (PLUGIN_ROOT / "dashboard.py").resolve()


class LauncherError(RuntimeError):
    """An actionable error while resolving or starting the dashboard."""


def _absolute_path(value: str) -> Path:
    path = Path(os.path.expanduser(value))
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def _directory(value: str, label: str) -> Path:
    path = _absolute_path(value)
    if not path.is_dir():
        raise LauncherError(f"{label} is not an existing directory: {path}")
    return path


def load_context(raw: Optional[str] = None) -> Mapping[str, Any]:
    """Decode Herdr's invocation context without inventing a project path."""

    if raw is None:
        raw = os.environ.get("HERDR_PLUGIN_CONTEXT_JSON")
    if not raw or not raw.strip():
        return {}
    try:
        context = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LauncherError(f"HERDR_PLUGIN_CONTEXT_JSON is not valid JSON: {exc}") from exc
    if not isinstance(context, dict):
        raise LauncherError("HERDR_PLUGIN_CONTEXT_JSON must contain a JSON object")
    return context


def _context_candidates(context: Mapping[str, Any]) -> list[tuple[str, Any]]:
    worktree = context.get("worktree")
    checkout_path = worktree.get("checkout_path") if isinstance(worktree, dict) else None
    return [
        ("worktree.checkout_path", checkout_path),
        ("focused_pane_cwd", context.get("focused_pane_cwd")),
        ("workspace_cwd", context.get("workspace_cwd")),
    ]


def resolve_project_cwd(
    explicit_cwd: Optional[str] = None,
    context: Optional[Mapping[str, Any]] = None,
    plugin_root: Optional[Path] = None,
) -> Path:
    """Resolve one project directory with explicit and Herdr context precedence.

    An explicit ``--cwd`` is intentional and wins. Otherwise the invocation's
    worktree checkout wins over the focused pane and workspace working directory.
    The plugin root is never used as an implicit project fallback.
    """

    if explicit_cwd is not None:
        return _directory(explicit_cwd, "--cwd")

    if context is None:
        context = load_context()
    root = (plugin_root or PLUGIN_ROOT).resolve()
    rejected: list[str] = []
    for label, value in _context_candidates(context):
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            candidate = _directory(value, label)
        except LauncherError as exc:
            rejected.append(str(exc))
            continue
        if candidate == root:
            rejected.append(f"{label} resolved to the plugin root: {root}")
            continue
        return candidate

    details = f" Rejected candidates: {'; '.join(rejected)}" if rejected else ""
    raise LauncherError(
        "could not resolve a project from Herdr's launch context. "
        "Pass --cwd DIRECTORY when invoking the launcher directly." + details
    )


def dashboard_command(
    project_cwd: Path,
    config_dir: Optional[str] = None,
    meters: Optional[str] = None,
) -> list[str]:
    """Build the dashboard argv using an absolute path owned by this plugin."""

    command = [sys.executable, str(DASHBOARD_PATH), "--cwd", str(project_cwd)]
    if config_dir is not None:
        command.extend(["--config-dir", str(_absolute_path(config_dir))])
    if meters is not None:
        command.extend(["--meters", str(_absolute_path(meters))])
    return command


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve the Herdr launch project and start the delegate dashboard."
    )
    parser.add_argument(
        "--cwd",
        metavar="DIRECTORY",
        help="explicit project directory; overrides all Herdr context fields",
    )
    parser.add_argument(
        "--config-dir",
        metavar="DIRECTORY",
        help="optional delegate config directory passed to dashboard.py",
    )
    parser.add_argument(
        "--meters",
        metavar="FILE",
        help="optional meter JSON file passed to dashboard.py",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        project_cwd = resolve_project_cwd(
            explicit_cwd=args.cwd or os.environ.get("DELEGATE_DASHBOARD_CWD")
        )
        if not DASHBOARD_PATH.is_file():
            raise LauncherError(
                f"dashboard.py is not present at {DASHBOARD_PATH}; "
                "integrated dashboard work is still required"
            )
        os.execv(sys.executable, dashboard_command(
            project_cwd,
            args.config_dir or os.environ.get("DELEGATE_DASHBOARD_CONFIG_DIR"),
            args.meters or os.environ.get("DELEGATE_DASHBOARD_METERS"),
        ))
    except LauncherError as exc:
        print(f"delegate-dashboard launcher: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"delegate-dashboard launcher: could not exec dashboard.py: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
