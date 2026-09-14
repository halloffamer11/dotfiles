#!/usr/bin/env python3
"""Read-only state model for the delegate dashboard prototype.

The model resolves one Git project during construction, reads only cached Meter
observations, and delegates every eligibility and leader decision to
``rank.tier_leaders``.  It never imports or executes ``usage.py``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
DELEGATE_SCRIPTS = REPO_ROOT / "agents" / "skills" / "delegate" / "scripts"
if str(DELEGATE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(DELEGATE_SCRIPTS))

import catalog
import rank


TIER_COLORS = {
    1: "#78bd74",
    2: "#1fb5bc",
    3: "#c68f32",
    4: "#be80ca",
}


class DashboardError(Exception):
    """A plain-language failure to build dashboard state."""


def _strict_json(raw: bytes) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"{value} is not valid JSON")

    return json.loads(raw.decode("utf-8"), parse_constant=reject_constant)


def _number_or_none(value: Any, *, fraction: bool = False) -> bool:
    if value is None:
        return True
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return 0 <= value <= 1 if fraction else value >= 0


def _valid_meter_document(doc: Any) -> bool:
    """Accept the cache shape ranking understands, without repairing values."""
    if not isinstance(doc, dict) or not isinstance(doc.get("lanes"), list):
        return False
    for observation in doc["lanes"]:
        if not isinstance(observation, dict):
            return False
        if not isinstance(observation.get("lane"), str) or not observation["lane"]:
            return False
        if not _number_or_none(observation.get("r"), fraction=True):
            return False
        if not _number_or_none(observation.get("pace")):
            return False
        if not _number_or_none(observation.get("remaining_weekly"), fraction=True):
            return False
        if "status" in observation and not isinstance(observation["status"], str):
            return False
    return True


def _file_signature(path: Path) -> tuple[str, str]:
    """Return a byte-sensitive signature that also distinguishes missing files."""
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return ("missing", "")
    except OSError as exc:
        return ("unreadable", f"{type(exc).__name__}:{exc}")
    return ("bytes", hashlib.sha256(raw).hexdigest())


class DashboardModel:
    """Public, JSON-safe dashboard state pinned to one resolved Git project.

    ``state`` is replaced after every successful refresh. ``refresh_if_changed``
    watches the pinned project's routing document and the Meter cache by bytes.
    A bad policy reload leaves the last valid rows visible with ``state['error']``;
    a missing or malformed Meter cache is rebuilt as explicit unknown data.
    """

    def __init__(
        self,
        *,
        cwd: str | Path,
        config_dir: str | Path | None = None,
        meters_path: str | Path | None = None,
        present: Iterable[str] | None = None,
    ) -> None:
        requested = Path(cwd).expanduser().resolve()
        root = catalog.find_git_root(str(requested))
        if root is None:
            raise DashboardError(f"{requested}: no Git project found")

        self.project_root = Path(root).resolve()
        self.config_dir = (
            Path(config_dir).expanduser().resolve() if config_dir is not None else None
        )
        if meters_path is None:
            import os

            cache = (
                os.environ.get("DELEGATE_CACHE")
                or os.environ.get("CONSULT_CACHE")
                or "~/.cache/delegate/usage.json"
            )
            self.meters_path = Path(cache).expanduser().resolve()
        else:
            self.meters_path = Path(meters_path).expanduser().resolve()
        self.project_policy_path = self.project_root / ".delegate" / "routing.json"
        self.present = (
            frozenset(present)
            if present is not None
            else frozenset(harness for harness in catalog.HARNESSES if shutil.which(harness))
        )
        self.state: dict[str, Any] = {}
        self._revision = 0
        self._watch_signatures: tuple[tuple[str, str], tuple[str, str]] | None = None
        self.refresh()

    def _signatures(self) -> tuple[tuple[str, str], tuple[str, str]]:
        return (
            _file_signature(self.project_policy_path),
            _file_signature(self.meters_path),
        )

    def _load_meters(self) -> tuple[dict[str, Any], str, str | None]:
        try:
            raw = self.meters_path.read_bytes()
        except FileNotFoundError:
            return {}, "missing", "Meter cache is missing; observations are unknown."
        except OSError as exc:
            return {}, "unreadable", f"Meter cache cannot be read; observations are unknown: {exc}"
        try:
            doc = _strict_json(raw)
        except (UnicodeError, ValueError):
            return {}, "malformed", "Meter cache is malformed; observations are unknown."
        if not _valid_meter_document(doc):
            return {}, "malformed", "Meter cache has invalid observations; values are unknown."
        return doc, "ok", None

    @staticmethod
    def _display_order(row: dict[str, Any]) -> tuple[int, int, str]:
        order = row.get("order")
        return (1 if order is None else 0, order if isinstance(order, int) else 0, row["lane"])

    def _build_state(self) -> dict[str, Any]:
        try:
            effective = catalog.load_catalog(
                cwd=str(self.project_root),
                config_dir=str(self.config_dir) if self.config_dir is not None else None,
            )
        except catalog.CatalogError as exc:
            raise DashboardError(str(exc)) from exc

        meters, meter_status, meter_detail = self._load_meters()
        previews = rank.tier_leaders(effective, meters, self.present)
        tiers = []
        for preview in previews:
            carried = [
                row
                for row in preview["rows"]
                if not row["reason"].startswith("vetoed:disabled")
            ]
            carried.sort(key=self._display_order)
            rows = [
                {
                    "lane": row["lane"],
                    "model": row["model"],
                    "effort": row["effort"],
                    "harness": row["harness"],
                    "meter": row["meter"],
                    "remaining": row["r"],
                    "pace": row["pace"],
                    "eligible": row["eligible"],
                    "reason": row["reason"],
                    "order": row["order"],
                }
                for row in carried
            ]
            tiers.append(
                {
                    "tier": preview["tier"],
                    "color": TIER_COLORS[preview["tier"]],
                    "leader": preview["leader"],
                    "rows": rows,
                }
            )

        routing = effective["routing"]
        sources = effective["sources"]
        self._revision += 1
        return {
            "prototype": True,
            "project": {
                "name": self.project_root.name,
                "root": str(self.project_root),
                "policy": str(self.project_policy_path),
            },
            "policy": {
                "gate": {
                    "value": routing["gate"],
                    "display": f"{round(routing['gate'] * 100):g}%",
                    "source": sources.get("gate"),
                },
                "margin": {
                    "value": routing["margin"],
                    "display": f"{round(routing['margin'] * 100):g}%",
                    "source": sources.get("margin"),
                },
            },
            "usage": {
                "label": "Global subscription usage",
                "path": str(self.meters_path),
                "status": meter_status,
                "detail": meter_detail,
                "probed_at": meters.get("probed_at") if meters else None,
            },
            "tiers": tiers,
            "revision": self._revision,
            "error": None,
        }

    def refresh(self) -> dict[str, Any]:
        """Reload public state while retaining the pinned project identity."""
        try:
            new_state = self._build_state()
        except DashboardError as exc:
            if not self.state:
                self._watch_signatures = self._signatures()
                raise
            self._revision += 1
            new_state = dict(self.state)
            new_state["revision"] = self._revision
            new_state["error"] = f"Reload failed; showing last valid state: {exc}"
        self.state = new_state
        self._watch_signatures = self._signatures()
        return self.state

    def refresh_if_changed(self) -> bool:
        """Refresh after a watched file's bytes change; return whether it changed."""
        signatures = self._signatures()
        if signatures == self._watch_signatures:
            return False
        self.refresh()
        return True

