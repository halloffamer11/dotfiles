#!/usr/bin/env python3
"""Open the local dashboard pane, using the socket only for popup placement."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

import tomllib


PLUGIN_ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = PLUGIN_ROOT / "herdr-plugin.toml"
PLACEMENTS = ("split", "tab", "zoomed", "overlay", "popup")
CLI_PLACEMENTS = set(PLACEMENTS) - {"popup"}


class OpenError(RuntimeError):
    """An actionable error while opening the Herdr pane."""


def manifest_entrypoint() -> tuple[str, str]:
    try:
        with MANIFEST_PATH.open("rb") as manifest_file:
            manifest = tomllib.load(manifest_file)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise OpenError(f"could not read {MANIFEST_PATH}: {exc}") from exc

    plugin_id = manifest.get("id")
    panes = manifest.get("panes")
    if not isinstance(plugin_id, str) or not plugin_id:
        raise OpenError(f"manifest has no plugin id: {MANIFEST_PATH}")
    if not isinstance(panes, list) or len(panes) != 1:
        raise OpenError("delegate dashboard manifest must declare exactly one pane")
    entrypoint = panes[0].get("id") if isinstance(panes[0], dict) else None
    if not isinstance(entrypoint, str) or not entrypoint:
        raise OpenError("delegate dashboard manifest pane has no entrypoint id")
    return plugin_id, entrypoint


def _herdr_binary() -> str:
    configured = os.environ.get("HERDR_BIN_PATH")
    if configured:
        return configured
    return shutil.which("herdr") or "herdr"


def _add_optional(params: dict[str, Any], key: str, value: Optional[str]) -> None:
    if value:
        params[key] = value


def _absolute_cwd(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    path = Path(os.path.expanduser(value))
    if not path.is_absolute():
        path = Path.cwd() / path
    return str(path.resolve())


def _request_params(args: argparse.Namespace, plugin_id: str, entrypoint: str) -> dict[str, Any]:
    params: dict[str, Any] = {
        "plugin_id": plugin_id,
        "entrypoint": entrypoint,
        "placement": args.placement,
        "focus": False,
        "env": _launch_env(args),
    }
    if args.placement in ("split", "zoomed"):
        _add_optional(params, "target_pane_id", args.target_pane)
    if args.placement == "tab":
        _add_optional(params, "workspace_id", args.workspace)
    if args.placement == "split":
        params["direction"] = args.direction
    if args.placement == "popup":
        _add_optional(params, "width", args.width)
        _add_optional(params, "height", args.height)
    return params


def _launch_env(args: argparse.Namespace) -> dict[str, str]:
    # Plugin processes inherit the server environment, not this invoking shell.
    env = {"PATH": os.environ.get("PATH", os.defpath)}
    project_cwd = args.cwd
    if not project_cwd and args.target_pane:
        try:
            result = subprocess.run(
                [_herdr_binary(), "pane", "get", args.target_pane],
                capture_output=True, text=True, check=True,
            )
            pane = json.loads(result.stdout)["result"]["pane"]
            # make -C changes its own cwd while the invoking pane stays in the
            # user's project. Use that pane context, not the helper process.
            project_cwd = pane["cwd"]
        except (OSError, subprocess.CalledProcessError, ValueError, KeyError) as exc:
            raise OpenError(f"could not resolve invoking pane {args.target_pane}: {exc}") from exc
    if not project_cwd:
        raise OpenError("pass --target-pane or --cwd to identify the launch project")
    for option, variable in (
        ("cwd", "DELEGATE_DASHBOARD_CWD"),
        ("config_dir", "DELEGATE_DASHBOARD_CONFIG_DIR"),
        ("meters", "DELEGATE_DASHBOARD_METERS"),
    ):
        value = _absolute_cwd(project_cwd if option == "cwd" else getattr(args, option))
        if value:
            env[variable] = value
    return env


def _open_with_cli(args: argparse.Namespace, plugin_id: str, entrypoint: str) -> int:
    command = [
        _herdr_binary(),
        "plugin",
        "pane",
        "open",
        "--plugin",
        plugin_id,
        "--entrypoint",
        entrypoint,
        "--placement",
        args.placement,
    ]
    if args.placement in ("split", "zoomed") and args.target_pane:
        command.extend(["--target-pane", args.target_pane])
    if args.placement == "tab" and args.workspace:
        command.extend(["--workspace", args.workspace])
    for key, value in _launch_env(args).items():
        command.extend(["--env", f"{key}={value}"])
    if args.placement == "split":
        command.extend(["--direction", args.direction])
    command.append("--no-focus")
    try:
        completed = subprocess.run(command, check=False)
    except OSError as exc:
        raise OpenError(f"could not run Herdr CLI: {exc}") from exc
    return completed.returncode


def _read_socket_response(connection: socket.socket, request_id: str) -> dict[str, Any]:
    with connection.makefile("rb") as response_stream:
        line = response_stream.readline()
    if not line:
        raise OpenError("Herdr socket closed without a response")
    try:
        response = json.loads(line)
    except json.JSONDecodeError as exc:
        raise OpenError(f"Herdr socket returned invalid JSON: {exc}") from exc
    if not isinstance(response, dict) or response.get("id") != request_id:
        raise OpenError("Herdr socket returned an unexpected response id")
    return response


def _open_popup(args: argparse.Namespace, plugin_id: str, entrypoint: str) -> int:
    if os.name == "nt":
        raise OpenError("popup placement requires the Unix socket helper on this prototype")
    socket_path = os.environ.get("HERDR_SOCKET_PATH")
    if not socket_path:
        raise OpenError("HERDR_SOCKET_PATH is required for popup placement")

    request_id = f"delegate-dashboard-{os.getpid()}"
    request = {
        "id": request_id,
        "method": "plugin.pane.open",
        "params": _request_params(args, plugin_id, entrypoint),
    }
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(30)
            connection.connect(socket_path)
            payload = (json.dumps(request, separators=(",", ":")) + "\n").encode("utf-8")
            connection.sendall(payload)
            response = _read_socket_response(connection, request_id)
    except OSError as exc:
        raise OpenError(f"could not use Herdr socket {socket_path}: {exc}") from exc

    error = response.get("error")
    if error:
        if isinstance(error, dict):
            message = error.get("message") or error.get("code") or str(error)
        else:
            message = str(error)
        print(f"Herdr popup open failed: {message}", file=sys.stderr)
        return 1
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Open the delegate dashboard Herdr pane")
    parser.add_argument("--placement", choices=PLACEMENTS, default="split")
    parser.add_argument(
        "--target-pane",
        default=os.environ.get("HERDR_PANE_ID"),
        help="pane beside which a split or zoomed pane opens (default: HERDR_PANE_ID)",
    )
    parser.add_argument(
        "--workspace",
        default=os.environ.get("HERDR_WORKSPACE_ID"),
        help="workspace for a tab placement (default: HERDR_WORKSPACE_ID)",
    )
    parser.add_argument("--direction", choices=("right", "down"), default="right")
    parser.add_argument("--cwd", metavar="PATH", help="project directory to pin; overrides invocation context")
    parser.add_argument("--config-dir", metavar="PATH", help="optional delegate catalog directory")
    parser.add_argument("--meters", metavar="FILE", help="optional cached Meter fixture")
    parser.add_argument("--width", help="popup width in cells or percent")
    parser.add_argument("--height", help="popup height in cells or percent")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    if os.environ.get("HERDR_ENV") != "1":
        print("delegate-dashboard opener: run inside a Herdr-managed pane", file=sys.stderr)
        return 2
    if args.placement != "popup" and (args.width or args.height):
        print("delegate-dashboard opener: --width/--height require --placement popup", file=sys.stderr)
        return 2

    try:
        plugin_id, entrypoint = manifest_entrypoint()
        if args.placement in CLI_PLACEMENTS:
            return _open_with_cli(args, plugin_id, entrypoint)
        return _open_popup(args, plugin_id, entrypoint)
    except OpenError as exc:
        print(f"delegate-dashboard opener: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
