#!/usr/bin/env python3
"""State model for the delegate dashboard prototype.

The model resolves one Git project during construction, reads only cached Meter
observations, and delegates every eligibility and leader decision to
``rank.tier_leaders``.  It never imports or executes ``usage.py``.
"""

from __future__ import annotations

import copy
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


def _bytes_signature(raw: bytes | None) -> tuple[str, str]:
    if raw is None:
        return ("missing", "")
    return ("bytes", hashlib.sha256(raw).hexdigest())


class DashboardModel:
    """Public, JSON-safe dashboard state pinned to one resolved Git project.

    ``state`` is replaced after every successful refresh. ``refresh_if_changed``
    watches the pinned project's routing document, both global policy documents,
    and the Meter cache by bytes.
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
        global_dir = (
            self.config_dir
            if self.config_dir is not None
            else Path(catalog.CONFIG_DIR).expanduser().resolve()
        )
        self.global_lanes_path = global_dir / "lanes.json"
        self.global_routing_path = global_dir / "routing.json"
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
        self._watch_signatures: tuple[tuple[str, str], ...] | None = None
        self._loaded_policy_bytes: bytes | None = None
        self._project_doc: dict[str, Any] = {}
        self._global_lanes_doc: dict[str, Any] = {}
        self._global_routing_doc: dict[str, Any] = {}
        self.refresh()

    def _signatures(self) -> tuple[tuple[str, str], ...]:
        return (
            _file_signature(self.project_policy_path),
            _file_signature(self.meters_path),
            _file_signature(self.global_lanes_path),
            _file_signature(self.global_routing_path),
        )

    @staticmethod
    def _read_optional_bytes(path: Path) -> bytes | None:
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None

    @staticmethod
    def _load_json_snapshot(path: Path) -> tuple[dict[str, Any], bytes]:
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise DashboardError(f"{path}: cannot read: {exc}") from exc
        try:
            doc = _strict_json(raw)
        except (UnicodeError, ValueError) as exc:
            raise DashboardError(f"{path}: malformed JSON: {exc}") from exc
        if not isinstance(doc, dict):
            raise DashboardError(f"{path}: document must be a JSON object")
        return doc, raw

    def _load_project_snapshot(self) -> tuple[dict[str, Any], bytes | None]:
        try:
            raw = self._read_optional_bytes(self.project_policy_path)
        except OSError as exc:
            raise DashboardError(f"{self.project_policy_path}: cannot read: {exc}") from exc
        if raw is None:
            return {}, None
        try:
            doc = _strict_json(raw)
        except (UnicodeError, ValueError) as exc:
            raise DashboardError(f"{self.project_policy_path}: malformed JSON: {exc}") from exc
        if not isinstance(doc, dict):
            raise DashboardError(f"{self.project_policy_path}: document must be a JSON object")
        return doc, raw

    def _load_meters(
        self,
    ) -> tuple[dict[str, Any], str, str | None, tuple[str, str]]:
        try:
            raw = self.meters_path.read_bytes()
        except FileNotFoundError:
            return (
                {},
                "missing",
                "Meter cache is missing; observations are unknown.",
                _bytes_signature(None),
            )
        except OSError as exc:
            return (
                {},
                "unreadable",
                f"Meter cache cannot be read; observations are unknown: {exc}",
                _file_signature(self.meters_path),
            )
        signature = _bytes_signature(raw)
        try:
            doc = _strict_json(raw)
        except (UnicodeError, ValueError):
            return (
                {},
                "malformed",
                "Meter cache is malformed; observations are unknown.",
                signature,
            )
        if not _valid_meter_document(doc):
            return (
                {},
                "malformed",
                "Meter cache has invalid observations; values are unknown.",
                signature,
            )
        return doc, "ok", None, signature

    @staticmethod
    def _display_order(row: dict[str, Any]) -> tuple[int, int, str]:
        order = row.get("order")
        return (1 if order is None else 0, order if isinstance(order, int) else 0, row["lane"])

    def _build_state(self) -> tuple[dict[str, Any], dict[str, Any]]:
        global_lanes, global_lanes_raw = self._load_json_snapshot(self.global_lanes_path)
        global_routing, global_routing_raw = self._load_json_snapshot(self.global_routing_path)
        project_doc, project_raw = self._load_project_snapshot()
        try:
            if project_raw is not None:
                catalog.validate_project_routing(
                    project_doc,
                    global_lanes,
                    global_routing,
                    source=str(self.project_policy_path),
                    lanes_source=str(self.global_lanes_path),
                    global_source=str(self.global_routing_path),
                )
            effective = catalog.load_catalog(
                cwd=str(self.project_root),
                config_dir=str(self.config_dir) if self.config_dir is not None else None,
            )
        except catalog.CatalogError as exc:
            raise DashboardError(str(exc)) from exc

        meters, meter_status, meter_detail, meter_signature = self._load_meters()
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
        state = {
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
            "save": {"status": "idle", "detail": None},
        }
        snapshot = {
            "project_doc": project_doc,
            "project_raw": project_raw,
            "global_lanes": global_lanes,
            "global_routing": global_routing,
            "signatures": (
                _bytes_signature(project_raw),
                meter_signature,
                _bytes_signature(global_lanes_raw),
                _bytes_signature(global_routing_raw),
            ),
        }
        return state, snapshot

    def refresh(self) -> dict[str, Any]:
        """Reload public state while retaining the pinned project identity."""
        try:
            new_state, snapshot = self._build_state()
        except DashboardError as exc:
            if not self.state:
                self._watch_signatures = self._signatures()
                raise
            self._revision += 1
            new_state = dict(self.state)
            new_state["revision"] = self._revision
            new_state["error"] = f"Reload failed; showing last valid state: {exc}"
            self._watch_signatures = self._signatures()
        else:
            self._project_doc = copy.deepcopy(snapshot["project_doc"])
            self._loaded_policy_bytes = snapshot["project_raw"]
            self._global_lanes_doc = snapshot["global_lanes"]
            self._global_routing_doc = snapshot["global_routing"]
            # These are the bytes used to build the state, not a later sample.
            # If a file changed during the refresh, the next watch pass sees it.
            self._watch_signatures = snapshot["signatures"]
        self.state = new_state
        return self.state

    def refresh_if_changed(self) -> bool:
        """Refresh after a watched file's bytes change; return whether it changed."""
        signatures = self._signatures()
        if signatures == self._watch_signatures:
            return False
        self.refresh()
        return True

    def _set_save_state(self, status: str, detail: str) -> None:
        save = {"status": status, "detail": detail}
        self.state = dict(self.state)
        self.state["save"] = save

    def _unsafe_policy_target(self) -> str | None:
        """Explain a policy path that must not be replaced, or return None."""
        if self.project_policy_path.is_symlink():
            return "project routing path is a symlink; refusing to replace it"
        if self.project_policy_path.parent.resolve() != self.project_policy_path.parent:
            return "project policy directory is a symlink; refusing to write outside the pinned path"
        resolved = self.project_policy_path.resolve(strict=False)
        global_targets = {
            self.global_lanes_path.resolve(strict=False),
            self.global_routing_path.resolve(strict=False),
        }
        if resolved in global_targets:
            return "project routing path resolves to a global delegate policy file"
        return None

    def save_project_policy(self, proposed: dict[str, Any]) -> bool:
        """Validate and atomically save a complete proposed project document.

        The final byte check prevents the ordinary stale-editor overwrite. There
        is intentionally no broad filesystem lock in this prototype, so another
        writer can still race between that last check and the atomic rename.
        """
        proposal = copy.deepcopy(proposed)
        try:
            catalog.validate_project_routing(
                proposal,
                self._global_lanes_doc,
                self._global_routing_doc,
                source=str(self.project_policy_path),
                lanes_source=str(self.global_lanes_path),
                global_source=str(self.global_routing_path),
            )
        except catalog.CatalogError as exc:
            self._set_save_state("error", f"Not saved: {exc}")
            return False

        unsafe = self._unsafe_policy_target()
        if unsafe is not None:
            self._set_save_state("error", f"Not saved: {unsafe}")
            return False

        try:
            current_raw = self._read_optional_bytes(self.project_policy_path)
        except OSError as exc:
            self._set_save_state("error", f"Not saved: cannot recheck project policy: {exc}")
            return False
        if current_raw != self._loaded_policy_bytes:
            self.refresh()
            self._set_save_state(
                "conflict",
                "Conflict: project routing changed externally; reloaded it. Repeat the action to save.",
            )
            return False

        try:
            catalog.write_json(str(self.project_policy_path), proposal)
        except OSError as exc:
            self._set_save_state("error", f"Not saved: {exc}")
            return False

        self.refresh()
        if self.state.get("error"):
            self._set_save_state("error", "Saved, but the resulting policy could not be reloaded.")
            return False
        self._set_save_state("saved", "Saved project policy.")
        return True

    def move_lane(self, lane_name: str, direction: int) -> bool:
        """Move one carried lane by one position inside its existing Tier."""
        if type(direction) is not int or direction not in (-1, 1):
            self._set_save_state("error", "Not saved: movement must be one position up or down.")
            return False

        selected_tier = None
        selected_index = None
        for tier in self.state.get("tiers", []):
            names = [row["lane"] for row in tier["rows"]]
            if lane_name in names:
                selected_tier = tier
                selected_index = names.index(lane_name)
                break
        if selected_tier is None or selected_index is None:
            self._set_save_state("error", f"Not saved: lane '{lane_name}' is not carried.")
            return False

        destination = selected_index + direction
        if destination < 0 or destination >= len(selected_tier["rows"]):
            self._set_save_state(
                "error",
                f"Not saved: '{lane_name}' is already at the Tier {selected_tier['tier']} boundary.",
            )
            return False

        complete_order = []
        for tier in self.state["tiers"]:
            names = [row["lane"] for row in tier["rows"]]
            if tier is selected_tier:
                names[selected_index], names[destination] = names[destination], names[selected_index]
            complete_order.extend(names)

        proposal = copy.deepcopy(self._project_doc)
        if not proposal:
            proposal["version"] = catalog.ROUTING_VERSION
        proposal["project_order"] = complete_order
        return self.save_project_policy(proposal)
