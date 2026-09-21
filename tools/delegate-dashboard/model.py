#!/usr/bin/env python3
"""State model for the delegate dashboard.

The model resolves one Git project during construction, reads only cached Meter
observations, and never runs a vendor probe or acquires Meter data.  Eligibility
and leader decisions go to ``rank.tier_leaders``.  Gate, Margin, and Project-order
saves go through ``catalog.edit_catalog`` with ``scope='project'``, cached meters,
and the construction-time harness set.  ``move_lane_tier`` is the same path for a
Lane's Tier, written against ticket 32's project Lanes document; until that backend
is installed its preview raises and nothing is written.  The dashboard makes no
write at ``scope='global'``.  Direct catalog writes are not a dashboard save path.

Ticket 13 put a staging step in front of all four writes.  ``stage_move_lane``,
``stage_move_lane_tier`` and ``stage_percentage_edit`` hold one change each in
:attr:`DashboardModel.staged` and write nothing; the state they build is ranked
from the staged documents, so a Tier leader or a Pick moves on the screen before
any file does.  ``save_staged`` is the only writer, and it makes exactly the
catalog calls the immediate methods above make, in the order they were staged,
so a staged sequence and the same sequence of immediate saves leave the same
bytes.  Those immediate methods remain the reference for that and are no longer
bound to a key.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
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

_CURRENT_POLICY = object()

# catalog.edit_catalog raises CatalogError with this exact text on a stale expect.
INTERVENING_EDIT_MARK = (
    "intervening edit: source documents or resolved paths changed; preview again"
)
METERS_OFF_EFFECT = "Gate, Margin and Pace inactive; Remaining is cached"
ARROW = "→"


class DashboardError(Exception):
    """A plain-language failure to build dashboard state."""


@dataclass(frozen=True)
class PercentageEdit:
    """One percentage editor's value and policy snapshot at open time."""

    field: str
    text: str
    project_doc: dict[str, Any]
    policy_bytes: bytes | None
    global_signatures: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class StagedChange:
    """One unsaved change: the catalog call it will make, and its one line.

    ``kind`` is what the pane marks -- ``order``, ``tier``, ``gate`` or
    ``margin``.  ``op`` and ``kwargs`` are the ``catalog.edit_catalog``
    arguments, which are also what replays the change onto a document, so the
    staged view and the save cannot drift apart.
    """

    kind: str
    op: str
    label: str
    kwargs: dict[str, Any]
    lane: str | None = None
    field: str | None = None
    # What the change moves away from, which the write reports but never reads.
    origin: Any = None

    @property
    def writes_project_lanes(self) -> bool:
        """True when this change is written to the project's Lanes document."""
        return self.kind == "tier"


# The four files staging pins, in the words the pane uses for each one.
STAGE_BASE_NAMES = (
    ("project", "routing.json"),
    ("project_lanes", "lanes.json"),
    ("lanes", "the global lane catalog"),
    ("routing", "the global routing policy"),
)


# catalog.edit_catalog raises this while a project may not carry Lane Tiers.
PROJECT_TIER_UNSUPPORTED = "is global-only"
PROJECT_TIER_MISSING = "Tier move needs the project Lanes backend (ticket 32)"


def _percentage_text(value: int | float) -> str:
    """Render a stored fraction as a lossless, human-editable percentage."""
    percentage = Decimal(str(value)) * Decimal(100)
    if percentage == 0:
        return "0"
    return format(percentage.normalize(), "f")


def _parse_percentage(text: str) -> float:
    """Parse a finite percentage from 0 through 100 into its stored fraction."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("enter a percentage from 0 to 100")
    try:
        percentage = Decimal(text.strip())
    except InvalidOperation as exc:
        raise ValueError("enter a number from 0 to 100") from exc
    if not percentage.is_finite():
        raise ValueError("percentage must be finite and from 0 to 100")
    if percentage < 0 or percentage > 100:
        raise ValueError("percentage must be from 0 to 100")
    if percentage == 0:
        return 0.0
    return float(percentage / Decimal(100))


def _strict_json(raw: bytes) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"{value} is not valid JSON")

    return json.loads(raw.decode("utf-8"), parse_constant=reject_constant)


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
        # Ticket 32's project Lanes document; `move_lane_tier` is its only writer.
        self.project_lanes_path = self.project_root / ".delegate" / "lanes.json"
        clash = self._clashing_project_target()
        if clash is not None:
            raise DashboardError(clash)
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
        self._staged: list[StagedChange] = []
        self._stage_base: dict[str, tuple[str, str]] | None = None
        self.refresh()

    @property
    def staged(self) -> tuple[StagedChange, ...]:
        """The unsaved changes, oldest first."""
        return tuple(self._staged)

    def _global_target_of(self, path: Path) -> str | None:
        """Name the global document `path` resolves to, if it resolves to one."""
        return {
            self.global_lanes_path.resolve(strict=False): "the global lane catalog",
            self.global_routing_path.resolve(strict=False): "the global routing policy",
        }.get(path.resolve(strict=False))

    def _clashing_project_target(self) -> str | None:
        """Refuse a project whose Lanes document is a global document.

        Ticket 32 gave the project a second document, ``.delegate/lanes.json``,
        and ``load_catalog`` reads it as a lane customization.  A link, or a
        ``--config-dir`` pinned at the project's own ``.delegate``, makes that
        file the global catalog, which the catalog then rejects for carrying a
        version.  There is no view to open and no save to refuse, so this one is
        answered at construction, in the dashboard's own words.  A project
        routing path that resolves to a global file still opens and is refused
        at each save, which is where that rule has always lived.
        """
        hit = self._global_target_of(self.project_lanes_path)
        if hit is not None:
            return f"{self.project_lanes_path}: the project Lanes path resolves to {hit}"
        return None

    def _signatures(self) -> tuple[tuple[str, str], ...]:
        return (
            _file_signature(self.project_policy_path),
            _file_signature(self.project_lanes_path),
            _file_signature(self.meters_path),
            _file_signature(self.global_lanes_path),
            _file_signature(self.global_routing_path),
        )

    def _global_signatures(self) -> tuple[tuple[str, str], ...]:
        return (
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

    def _load_optional_snapshot(self, path: Path) -> tuple[dict[str, Any], bytes | None]:
        """Read one project document that may not exist yet."""
        try:
            raw = self._read_optional_bytes(path)
        except OSError as exc:
            raise DashboardError(f"{path}: cannot read: {exc}") from exc
        if raw is None:
            return {}, None
        try:
            doc = _strict_json(raw)
        except (UnicodeError, ValueError) as exc:
            raise DashboardError(f"{path}: malformed JSON: {exc}") from exc
        if not isinstance(doc, dict):
            raise DashboardError(f"{path}: document must be a JSON object")
        return doc, raw

    def _load_project_snapshot(self) -> tuple[dict[str, Any], bytes | None]:
        return self._load_optional_snapshot(self.project_policy_path)

    def _load_project_lanes_snapshot(self) -> tuple[dict[str, Any], bytes | None]:
        return self._load_optional_snapshot(self.project_lanes_path)

    def _source_files(self) -> dict[str, str]:
        """The four source paths, named as ``catalog`` names them in a snapshot."""
        return {
            "lanes": str(self.global_lanes_path),
            "routing": str(self.global_routing_path),
            "project": str(self.project_policy_path),
            "project_lanes": str(self.project_lanes_path),
        }

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
        if rank.meter_observations(doc) is None:
            return (
                {},
                "malformed",
                "Meter cache has invalid observations; values are unknown.",
                signature,
            )
        return doc, "ok", None, signature

    def _replay(
        self,
        changes: Iterable[StagedChange],
        lanes_doc: dict[str, Any],
        routing_doc: dict[str, Any],
        project_doc: dict[str, Any] | None,
        project_lanes_doc: dict[str, Any] | None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """Apply the staged changes to the two project documents, in order.

        The catalog's own planners do the work, so a staged document is the
        document ``edit_catalog`` would write for the same call, and the second
        change is planned against the result of the first exactly as a second
        immediate save would be.  Nothing here touches the filesystem.
        """
        files = self._source_files()
        for change in changes:
            if change.op == "order":
                planned = catalog._plan_order(
                    change.kwargs["lane"],
                    change.kwargs["position"],
                    "project",
                    lanes_doc,
                    routing_doc,
                    project_doc,
                    files,
                    project_lanes_doc,
                )
            else:
                planned = catalog._plan_set(
                    change.kwargs["field"],
                    change.kwargs["value"],
                    "project",
                    lanes_doc,
                    routing_doc,
                    project_doc,
                    project_lanes_doc,
                )
            project_doc, project_lanes_doc = planned[3], planned[4]
        return project_doc, project_lanes_doc

    def _staged_effective(
        self,
        changes: Iterable[StagedChange],
        lanes_doc: dict[str, Any],
        routing_doc: dict[str, Any],
        project_doc: dict[str, Any] | None,
        project_lanes_doc: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """The effective catalog the staged documents produce.

        ``catalog._catalog_from_docs`` is the catalog's own reader for documents
        it already holds, and the one ``edit_catalog`` previews through; going
        through it keeps the staged view on the single ranking rule and
        validates both documents on the way.
        """
        project, project_lanes = self._replay(
            changes, lanes_doc, routing_doc, project_doc, project_lanes_doc
        )
        return catalog._catalog_from_docs(
            lanes_doc, routing_doc, project, self._source_files(), project_lanes
        )

    def _staged_effective_from_disk(
        self, changes: Iterable[StagedChange]
    ) -> dict[str, Any]:
        """The same, against the documents on disk right now."""
        lanes_doc, _ = self._load_json_snapshot(self.global_lanes_path)
        routing_doc, _ = self._load_json_snapshot(self.global_routing_path)
        project_doc, project_raw = self._load_project_snapshot()
        project_lanes_doc, project_lanes_raw = self._load_project_lanes_snapshot()
        return self._staged_effective(
            changes,
            lanes_doc,
            routing_doc,
            project_doc if project_raw is not None else None,
            project_lanes_doc if project_lanes_raw is not None else None,
        )

    def _record_stage_base(self) -> None:
        """Pin the bytes a staged save is allowed to write onto."""
        self._stage_base = {
            "project": _file_signature(self.project_policy_path),
            "project_lanes": _file_signature(self.project_lanes_path),
            "lanes": _file_signature(self.global_lanes_path),
            "routing": _file_signature(self.global_routing_path),
        }

    def _staged_conflict(self) -> str | None:
        """Name the pinned files another writer changed since staging began."""
        if self._stage_base is None or not self._staged:
            return None
        now = {
            "project": _file_signature(self.project_policy_path),
            "project_lanes": _file_signature(self.project_lanes_path),
            "lanes": _file_signature(self.global_lanes_path),
            "routing": _file_signature(self.global_routing_path),
        }
        changed = [name for key, name in STAGE_BASE_NAMES if now[key] != self._stage_base[key]]
        if not changed:
            return None
        return f"{' and '.join(changed)} changed on disk since the first staged change"

    def _staged_summary(self) -> dict[str, Any]:
        """The public, JSON-safe account of what is unsaved."""
        changes = []
        lanes: list[str] = []
        fields: list[str] = []
        for change in self._staged:
            changes.append(
                {
                    "kind": change.kind,
                    "lane": change.lane,
                    "field": change.field,
                    "label": change.label,
                }
            )
            if change.lane and change.lane not in lanes:
                lanes.append(change.lane)
            if change.field and change.field not in fields:
                fields.append(change.field)
        return {
            "count": len(self._staged),
            "changes": changes,
            "lanes": lanes,
            "fields": fields,
            "conflict": self._staged_conflict(),
        }

    @staticmethod
    def _display_order(row: dict[str, Any]) -> tuple[int, int, str]:
        order = row.get("order")
        return (1 if order is None else 0, order if isinstance(order, int) else 0, row["lane"])

    def _build_state(self) -> tuple[dict[str, Any], dict[str, Any]]:
        global_lanes, global_lanes_raw = self._load_json_snapshot(self.global_lanes_path)
        global_routing, global_routing_raw = self._load_json_snapshot(self.global_routing_path)
        project_doc, project_raw = self._load_project_snapshot()
        project_lanes_doc, project_lanes_raw = self._load_project_lanes_snapshot()
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
            if self._staged:
                effective = self._staged_effective(
                    self._staged,
                    global_lanes,
                    global_routing,
                    project_doc if project_raw is not None else None,
                    project_lanes_doc if project_lanes_raw is not None else None,
                )
            else:
                effective = catalog.load_catalog(
                    cwd=str(self.project_root),
                    config_dir=str(self.config_dir) if self.config_dir is not None else None,
                )
        except catalog.CatalogError as exc:
            raise DashboardError(str(exc)) from exc

        meters, meter_status, meter_detail, meter_signature = self._load_meters()
        previews = rank.tier_leaders(effective, meters, self.present)
        sources = effective["sources"]
        # Ticket 32: the Lanes whose Tier this project moved, and where from.
        project_tiers = dict(effective.get("project_tiers") or {})
        staged = self._staged_summary()
        staged_lanes = set(staged["lanes"])
        staged_fields = set(staged["fields"])
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
                    "order_source": sources.get(f"lanes.{row['lane']}.order"),
                    "tier_source": "project" if row["lane"] in project_tiers else "global",
                    "staged": row["lane"] in staged_lanes,
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
        meters_on = catalog.meters_enabled(routing)
        self._revision += 1
        state = {
            "project": {
                "name": self.project_root.name,
                "root": str(self.project_root),
                "policy": str(self.project_policy_path),
                "lanes": str(self.project_lanes_path),
            },
            "policy": {
                "gate": {
                    "value": routing["gate"],
                    "display": f"{_percentage_text(routing['gate'])}%",
                    "source": sources.get("gate"),
                    "staged": "gate" in staged_fields,
                },
                "margin": {
                    "value": routing["margin"],
                    "display": f"{_percentage_text(routing['margin'])}%",
                    "source": sources.get("margin"),
                    "staged": "margin" in staged_fields,
                },
                "meters": {
                    "value": meters_on,
                    "display": "on" if meters_on else "off",
                    "source": sources.get("meters"),
                    "effect": "" if meters_on else METERS_OFF_EFFECT,
                },
            },
            "usage": {
                "label": "Global subscription usage",
                "path": str(self.meters_path),
                "status": meter_status,
                "detail": meter_detail,
                "probed_at": meters.get("probed_at") if "lanes" in meters else None,
            },
            "tiers": tiers,
            "project_tiers": project_tiers,
            "staged": staged,
            "revision": self._revision,
            "error": None,
            "save": {"status": "idle", "detail": None},
        }
        snapshot = {
            "project_doc": project_doc,
            "project_raw": project_raw,
            "global_lanes": global_lanes,
            "global_routing": global_routing,
            # The same five files, in the same order, as `_signatures()`: a
            # shorter tuple never compares equal, so the watch would reload on
            # every pass.
            "signatures": (
                _bytes_signature(project_raw),
                _bytes_signature(project_lanes_raw),
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
            # The rows are the last valid ones, but the staged count is now.
            new_state["staged"] = self._staged_summary()
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

    def _cached_meters_doc(self) -> dict[str, Any]:
        """Return the pinned Meter cache without probing vendors."""
        meters, _status, _detail, _signature = self._load_meters()
        return meters

    def _catalog_edit_kwargs(self) -> dict[str, Any]:
        return {
            "scope": "project",
            "cwd": str(self.project_root),
            "config_dir": str(self.config_dir) if self.config_dir is not None else None,
            "present": self.present,
            "meters": self._cached_meters_doc(),
        }

    def _validate_project_proposal(self, proposal: dict[str, Any]) -> str | None:
        """Validate a complete project document against freshly read globals."""
        try:
            global_lanes, _ = self._load_json_snapshot(self.global_lanes_path)
            global_routing, _ = self._load_json_snapshot(self.global_routing_path)
            catalog.validate_project_routing(
                proposal,
                global_lanes,
                global_routing,
                source=str(self.project_policy_path),
                lanes_source=str(self.global_lanes_path),
                global_source=str(self.global_routing_path),
            )
        except (DashboardError, catalog.CatalogError) as exc:
            return str(exc)
        return None

    def _supported_project_operation(
        self,
        current: dict[str, Any],
        proposal: dict[str, Any],
    ) -> tuple[str, dict[str, Any]] | tuple[None, None]:
        """Map a complete proposal to one catalog set of Gate or Margin.

        Project order, Class ranges, and other keys are not written through
        this method. ``move_lane`` is the Order path.
        """
        if not isinstance(proposal, dict):
            return None, None
        baseline = current or {}
        changed = [
            key
            for key in (set(baseline) | set(proposal)) - {"version"}
            if baseline.get(key) != proposal.get(key)
        ]
        if changed == ["gate"] and "gate" in proposal:
            return "set", {"field": "routing.gate", "value": proposal["gate"]}
        if changed == ["margin"] and "margin" in proposal:
            return "set", {"field": "routing.margin", "value": proposal["margin"]}
        return None, None

    def _target_is_project_policy(self, target: Any) -> bool:
        """True when a catalog target file resolves to the pinned project policy."""
        if not isinstance(target, dict):
            return False
        file_name = target.get("file")
        if not isinstance(file_name, str) or not file_name:
            return False
        return (
            Path(file_name).expanduser().resolve(strict=False)
            == self.project_policy_path.resolve(strict=False)
        )

    def _fail_catalog_call(self, exc: BaseException) -> bool:
        """Map a catalog preview/apply failure to save state. Never catches interrupts."""
        if isinstance(exc, catalog.CatalogError) and INTERVENING_EDIT_MARK in str(exc):
            self.refresh()
            self._set_save_state(
                "conflict",
                "Conflict: catalog sources changed during save; reloaded. Repeat the action to save.",
            )
            return False
        if isinstance(exc, (catalog.CatalogError, OSError, ValueError)):
            self._set_save_state("error", f"Not saved: {exc}")
            return False
        raise exc

    def _refuse_if_unsafe_or_stale(
        self,
        expected: bytes | None,
    ) -> bool:
        """Return True when save must stop: unsafe path or stale project bytes."""
        unsafe = self._unsafe_policy_target()
        if unsafe is not None:
            self._set_save_state("error", f"Not saved: {unsafe}")
            return True
        try:
            current_raw = self._read_optional_bytes(self.project_policy_path)
        except OSError as exc:
            self._set_save_state("error", f"Not saved: cannot recheck project policy: {exc}")
            return True
        if current_raw != expected:
            self.refresh()
            self._set_save_state(
                "conflict",
                "Conflict: project routing changed externally; reloaded it. Repeat the action to save.",
            )
            return True
        return False

    def _apply_catalog_edit(
        self,
        op: str,
        *,
        expected_policy_bytes: bytes | None | object = _CURRENT_POLICY,
        **edit_kwargs: Any,
    ) -> bool:
        """Preview and apply one project catalog edit; refuse symlink targets."""
        expected = (
            self._loaded_policy_bytes
            if expected_policy_bytes is _CURRENT_POLICY
            else expected_policy_bytes
        )
        if self._refuse_if_unsafe_or_stale(expected):
            return False

        kwargs = {**self._catalog_edit_kwargs(), **edit_kwargs}
        try:
            preview = catalog.edit_catalog(op, apply=False, **kwargs)
        except (catalog.CatalogError, OSError, ValueError) as exc:
            return self._fail_catalog_call(exc)

        if not self._target_is_project_policy(preview.get("target")):
            self._set_save_state(
                "error",
                "Not saved: catalog preview targeted a file other than the pinned project policy.",
            )
            return False

        if self._refuse_if_unsafe_or_stale(expected):
            return False

        if preview.get("noop"):
            self._set_save_state("saved", "Saved project policy.")
            return True

        try:
            result = catalog.edit_catalog(
                op,
                apply=True,
                expect=preview["revision"],
                **kwargs,
            )
        except (catalog.CatalogError, OSError, ValueError) as exc:
            return self._fail_catalog_call(exc)

        if not self._target_is_project_policy(result.get("target")):
            self.refresh()
            self._set_save_state(
                "error",
                "Saved, but the catalog reported a file other than the pinned project policy.",
            )
            return False

        self.refresh()
        if self.state.get("error"):
            self._set_save_state("error", "Saved, but the resulting policy could not be reloaded.")
            return False
        self._set_save_state("saved", "Saved project policy.")
        return True

    def save_project_policy(
        self,
        proposed: dict[str, Any],
        *,
        expected_policy_bytes: bytes | None | object = _CURRENT_POLICY,
    ) -> bool:
        """Validate a complete proposal and apply one supported project set.

        Supported writes are Gate and Margin. Project order uses ``move_lane``.
        Class ranges and other keys are rejected after validation, so this is
        not a general document writer. Globals are re-read immediately before
        validation. The project-byte check is not a filesystem lock.
        """
        proposal = copy.deepcopy(proposed)
        error = self._validate_project_proposal(proposal)
        if error is not None:
            self._set_save_state("error", f"Not saved: {error}")
            return False

        if {k: v for k, v in proposal.items() if k != "version"} == {
            k: v for k, v in (self._project_doc or {}).items() if k != "version"
        }:
            self._set_save_state("saved", "Saved project policy.")
            return True

        op, edit_kwargs = self._supported_project_operation(self._project_doc, proposal)
        if op is None or edit_kwargs is None:
            self._set_save_state(
                "error",
                "Not saved: dashboard writes are Gate, Margin, or one Project order move.",
            )
            return False
        return self._apply_catalog_edit(
            op,
            expected_policy_bytes=expected_policy_bytes,
            **edit_kwargs,
        )

    def begin_percentage_edit(self, field: str) -> PercentageEdit:
        """Capture a Gate or Margin edit, including its conflict baseline."""
        if field not in ("gate", "margin"):
            raise ValueError("percentage field must be 'gate' or 'margin'")
        return PercentageEdit(
            field=field,
            text=_percentage_text(self.state["policy"][field]["value"]),
            project_doc=copy.deepcopy(self._project_doc),
            policy_bytes=self._loaded_policy_bytes,
            global_signatures=self._global_signatures(),
        )

    def save_percentage_edit(self, edit: PercentageEdit, text: str) -> bool:
        """Validate and save a percentage edit through catalog.edit_catalog."""
        if not isinstance(edit, PercentageEdit) or edit.field not in ("gate", "margin"):
            self._set_save_state("error", "Not saved: invalid percentage edit.")
            return False
        try:
            fraction = _parse_percentage(text)
        except ValueError as exc:
            self._set_save_state("error", f"Not saved: {edit.field.title()} {exc}.")
            return False

        # The prefilled value came from the globals the editor opened on; a global
        # edit since then makes it stale, the same as a project edit does.
        if edit.global_signatures and edit.global_signatures != self._global_signatures():
            self.refresh()
            self._set_save_state(
                "conflict",
                "Conflict: global policy changed during entry; reloaded it. Repeat the action to save.",
            )
            return False

        proposal = copy.deepcopy(edit.project_doc)
        proposal[edit.field] = fraction
        error = self._validate_project_proposal(proposal)
        if error is not None:
            self._set_save_state("error", f"Not saved: {error}")
            return False
        return self._apply_catalog_edit(
            "set",
            expected_policy_bytes=edit.policy_bytes,
            field=f"routing.{edit.field}",
            value=fraction,
        )

    def _order_move_target(
        self, lane_name: str, direction: int
    ) -> tuple[tuple[dict[str, Any], int] | None, str | None]:
        """The Tier and the one-based destination of one Order move.

        Returns ``(None, reason)`` when the move is off the board.  The shown
        Tier is the staged one, so a staged move is measured against the
        positions the pane is painting, not against the file.
        """
        if type(direction) is not int or direction not in (-1, 1):
            return None, "movement must be one position up or down"
        for tier in self.state.get("tiers", []):
            names = [row["lane"] for row in tier["rows"]]
            if lane_name not in names:
                continue
            destination = names.index(lane_name) + direction
            if destination < 0 or destination >= len(names):
                return None, f"'{lane_name}' is already at the Tier {tier['tier']} boundary"
            return (tier, destination + 1), None
        return None, f"lane '{lane_name}' is not carried"

    def _tier_move_target(
        self, lane_name: str, direction: int
    ) -> tuple[tuple[int, int] | None, str | None]:
        """The current and destination Tier of one project Tier move."""
        if type(direction) is not int or direction not in (-1, 1):
            return None, "a Tier move is one Tier left or right"
        current = self._tier_of(lane_name)
        if current is None:
            return None, f"lane '{lane_name}' is not carried"
        destination = current + direction
        if destination not in TIER_COLORS:
            edge = "first" if direction < 0 else "last"
            return None, (
                f"Tier {current} is the {edge} Tier, so '{lane_name}' "
                f"cannot move {'left' if direction < 0 else 'right'}"
            )
        return (current, destination), None

    def move_lane(self, lane_name: str, direction: int) -> bool:
        """Move one carried lane by one position inside its existing Tier."""
        target, reason = self._order_move_target(lane_name, direction)
        if target is None:
            self._set_save_state("error", f"Not saved: {reason}.")
            return False
        selected_tier, position = target
        destination = position - 1

        displayed_names = [row["lane"] for row in selected_tier["rows"]]
        try:
            fresh_names = self._fresh_carried_lane_names(selected_tier["tier"])
        except (catalog.CatalogError, OSError, ValueError) as exc:
            self._set_save_state("error", f"Not saved: {exc}")
            return False
        if fresh_names != displayed_names:
            self.refresh()
            self._set_save_state(
                "conflict",
                "Conflict: catalog Order or Tier changed; reloaded. Repeat the action to save.",
            )
            return False

        return self._apply_catalog_edit(
            "order",
            lane=lane_name,
            position=destination + 1,
        )

    def _unsafe_lanes_target(self) -> str | None:
        """The Tier write's own version of ``_unsafe_policy_target``.

        The project Lanes document is a second file in the same directory, so it
        gets the same three refusals: the file is a link, the directory is a
        link, or the path resolves onto a global document.
        """
        if self.project_lanes_path.is_symlink():
            return "project lanes path is a symlink; refusing to replace it"
        if self.project_lanes_path.parent.resolve() != self.project_lanes_path.parent:
            return "project policy directory is a symlink; refusing to write outside the pinned path"
        hit = self._global_target_of(self.project_lanes_path)
        if hit is not None:
            return f"project lanes path resolves to {hit}"
        return None

    def _tier_of(self, lane_name: str) -> int | None:
        """The Tier a carried Lane currently sits in, project override included."""
        for tier in self.state.get("tiers", []):
            if any(row["lane"] == lane_name for row in tier["rows"]):
                return tier["tier"]
        return None

    def _target_is_project_lanes(self, target: Any) -> bool:
        """True when a catalog target resolves to the project's Lanes document."""
        if not isinstance(target, dict):
            return False
        file_name = target.get("file")
        if not isinstance(file_name, str) or not file_name:
            return False
        return (
            Path(file_name).expanduser().resolve(strict=False)
            == self.project_lanes_path.resolve(strict=False)
        )

    def move_lane_tier(self, lane_name: str, direction: int) -> bool:
        """Move one carried Lane one Tier down or up, for this project only.

        Ticket 32: a project sets a Lane's Tier in
        ``<git-root>/.delegate/lanes.json`` and ``catalog.edit_catalog`` takes it
        as ``set lanes.<lane>.tier`` at ``scope='project'``, on the same
        preview/``expect``/apply contract ``move_lane`` uses for Order.  Setting
        a Lane back to its global Tier removes the entry; the catalog does that,
        not this method.  An installation without that backend raises at the
        preview and the caller shows :data:`PROJECT_TIER_MISSING`.
        """
        target, reason = self._tier_move_target(lane_name, direction)
        if target is None:
            self._set_save_state("error", f"Not saved: {reason}.")
            return False
        current, destination = target
        return self._apply_project_lane_tier(lane_name, current, destination)

    def _apply_project_lane_tier(
        self, lane_name: str, current: int, destination: int
    ) -> bool:
        """Write one Lane's project Tier: the write half of ``move_lane_tier``."""
        unsafe = self._unsafe_lanes_target()
        if unsafe is not None:
            self._set_save_state("error", f"Not saved: {unsafe}")
            return False

        kwargs = self._catalog_edit_kwargs()
        field = f"lanes.{lane_name}.tier"
        try:
            preview = catalog.edit_catalog(
                "set", apply=False, field=field, value=destination, **kwargs
            )
        except catalog.CatalogError as exc:
            if PROJECT_TIER_UNSUPPORTED in str(exc):
                self._set_save_state("error", PROJECT_TIER_MISSING)
                return False
            return self._fail_catalog_call(exc)
        except (OSError, ValueError) as exc:
            return self._fail_catalog_call(exc)

        if not self._target_is_project_lanes(preview.get("target")):
            self._set_save_state(
                "error",
                "Not saved: catalog preview targeted a file other than the project Lanes.",
            )
            return False
        if preview.get("noop"):
            self._set_save_state("saved", f"{lane_name} is already in Tier {destination}.")
            return True

        try:
            result = catalog.edit_catalog(
                "set",
                apply=True,
                expect=preview["revision"],
                field=field,
                value=destination,
                **kwargs,
            )
        except (catalog.CatalogError, OSError, ValueError) as exc:
            return self._fail_catalog_call(exc)

        if not self._target_is_project_lanes(result.get("target")):
            self.refresh()
            self._set_save_state(
                "error",
                "Saved, but the catalog reported a file other than the project Lanes.",
            )
            return False

        self.refresh()
        if self.state.get("error"):
            self._set_save_state("error", "Saved, but the resulting catalog could not be reloaded.")
            return False
        self._set_save_state(
            "saved",
            f"{lane_name}  Tier {current} {ARROW} Tier {destination}, for this project.",
        )
        return True

    # --- staged edits (ticket 13) -------------------------------------------

    def _stage(self, change: StagedChange) -> bool:
        """Add one change after replaying it, or refuse it and change nothing.

        A change that the catalog would not plan, or that leaves a catalog the
        ranker cannot read, is refused here rather than at the save, so the
        staged list is always a list a save can make.
        """
        try:
            self._staged_effective_from_disk(list(self._staged) + [change])
        except (DashboardError, catalog.CatalogError, OSError, ValueError) as exc:
            self._set_save_state("error", f"Not staged: {exc}")
            return False

        first = self._stage_base is None
        if first:
            self._record_stage_base()
        self._staged.append(change)
        self.refresh()
        if self.state.get("error"):
            self._staged.pop()
            if first:
                self._stage_base = None
            self.refresh()
            self._set_save_state("error", "Not staged: the staged view could not be built.")
            return False
        self._set_save_state("staged", f"{change.label}  ·  {len(self._staged)} unsaved")
        return True

    def stage_move_lane(self, lane_name: str, direction: int) -> bool:
        """Stage one Order move inside the Lane's shown Tier."""
        target, reason = self._order_move_target(lane_name, direction)
        if target is None:
            self._set_save_state("error", f"Not staged: {reason}.")
            return False
        tier, position = target
        return self._stage(
            StagedChange(
                kind="order",
                op="order",
                lane=lane_name,
                label=(
                    f"{lane_name}  Order {position - direction} {ARROW} {position} "
                    f"in Tier {tier['tier']}"
                ),
                kwargs={"lane": lane_name, "position": position},
            )
        )

    def stage_move_lane_tier(self, lane_name: str, direction: int) -> bool:
        """Stage one Lane's Tier move, for this project only."""
        target, reason = self._tier_move_target(lane_name, direction)
        if target is None:
            self._set_save_state("error", f"Not staged: {reason}.")
            return False
        current, destination = target
        return self._stage(
            StagedChange(
                kind="tier",
                op="set",
                lane=lane_name,
                origin=current,
                label=(
                    f"{lane_name}  Tier {current} {ARROW} Tier {destination}, "
                    "for this project"
                ),
                kwargs={"field": f"lanes.{lane_name}.tier", "value": destination},
            )
        )

    def stage_percentage_edit(self, edit: PercentageEdit, text: str) -> bool:
        """Stage one Gate or Margin value from a percentage editor."""
        if not isinstance(edit, PercentageEdit) or edit.field not in ("gate", "margin"):
            self._set_save_state("error", "Not staged: invalid percentage edit.")
            return False
        try:
            fraction = _parse_percentage(text)
        except ValueError as exc:
            self._set_save_state("error", f"Not staged: {edit.field.title()} {exc}.")
            return False
        shown = (self.state.get("policy") or {}).get(edit.field) or {}
        return self._stage(
            StagedChange(
                kind=edit.field,
                op="set",
                field=edit.field,
                label=(
                    f"{edit.field.title()} {shown.get('display') or ''} {ARROW} "
                    f"{_percentage_text(fraction)}%"
                ),
                kwargs={"field": f"routing.{edit.field}", "value": fraction},
            )
        )

    def undo_staged(self) -> bool:
        """Drop the last staged change."""
        if not self._staged:
            self._set_save_state("staged", "Nothing staged to undo.")
            return False
        dropped = self._staged.pop()
        if not self._staged:
            self._stage_base = None
        self.refresh()
        self._set_save_state(
            "staged", f"Dropped {dropped.label}  ·  {len(self._staged)} unsaved"
        )
        return True

    def discard_staged(self) -> bool:
        """Drop every staged change."""
        count = len(self._staged)
        if not count:
            self._set_save_state("staged", "Nothing staged to drop.")
            return False
        self._staged.clear()
        self._stage_base = None
        self.refresh()
        self._set_save_state(
            "staged", f"Dropped all {count} staged change{'' if count == 1 else 's'}."
        )
        return True

    def save_staged(self) -> bool:
        """Write every staged change, or none of them that this can detect.

        The conflict, the two symlink refusals and one replay of the whole list
        are answered before the first write; then each change makes the catalog
        call its immediate method makes, in the order it was staged.  A change
        leaves the staged list only once it is on disk, so a write that fails
        part way keeps itself and everything after it staged.
        """
        if not self._staged:
            self._set_save_state("saved", "Nothing staged to save.")
            return True

        conflict = self._staged_conflict()
        if conflict is not None:
            self.refresh()
            self._record_stage_base()
            self._set_save_state(
                "conflict",
                f"Not saved: {conflict}; reloaded it. Press w again to save onto it.",
            )
            return False

        if any(not change.writes_project_lanes for change in self._staged):
            unsafe = self._unsafe_policy_target()
            if unsafe is not None:
                self._set_save_state("error", f"Not saved: {unsafe}")
                return False
        if any(change.writes_project_lanes for change in self._staged):
            unsafe = self._unsafe_lanes_target()
            if unsafe is not None:
                self._set_save_state("error", f"Not saved: {unsafe}")
                return False

        try:
            self._staged_effective_from_disk(self._staged)
        except (DashboardError, catalog.CatalogError, OSError, ValueError) as exc:
            self._set_save_state("error", f"Not saved: {exc}")
            return False

        total = len(self._staged)
        while self._staged:
            change = self._staged.pop(0)
            if change.writes_project_lanes:
                written = self._apply_project_lane_tier(
                    change.lane, change.origin, change.kwargs["value"]
                )
            else:
                written = self._apply_catalog_edit(change.op, **change.kwargs)
            if not written:
                detail = (self.state.get("save") or {}).get("detail") or "the catalog refused it"
                self._staged.insert(0, change)
                self._record_stage_base()
                self.refresh()
                self._set_save_state(
                    "error",
                    f"Saved {total - len(self._staged)} of {total}; "
                    f"stopped at {change.label}: {detail}",
                )
                return False
            if self._staged:
                self._record_stage_base()

        self._stage_base = None
        self.refresh()
        self._set_save_state(
            "saved", f"Saved {total} staged change{'' if total == 1 else 's'} to the project."
        )
        return True

    def _fresh_carried_lane_names(self, tier_number: int) -> list[str]:
        """Carried lane names for one Tier from a freshly loaded effective catalog."""
        effective = catalog.load_catalog(
            cwd=str(self.project_root),
            config_dir=str(self.config_dir) if self.config_dir is not None else None,
        )
        previews = rank.tier_leaders(effective, self._cached_meters_doc(), self.present)
        for preview in previews:
            if preview["tier"] != tier_number:
                continue
            carried = [
                row
                for row in preview["rows"]
                if not row["reason"].startswith("vetoed:disabled")
            ]
            carried.sort(key=self._display_order)
            return [row["lane"] for row in carried]
        return []
