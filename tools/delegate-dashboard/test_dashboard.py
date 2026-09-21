#!/usr/bin/env python3
"""Model-boundary tests for the delegate dashboard."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from model import DashboardError, DashboardModel, INTERVENING_EDIT_MARK, METERS_OFF_EFFECT
from dashboard import PercentageEditor, pop_key

import catalog
import rank


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def lane(harness, model, effort, meter, tier, order, *, enabled=True):
    return {
        "harness": harness,
        "model": model,
        "effort": effort,
        "meter": meter,
        "meter_weight": 1,
        "timeout": "10m",
        "price": {"in": 1, "cache_read": 0, "cache_write": 0, "out": 1},
        "tier": tier,
        "order": order,
        "basis": "dashboard fixture",
        "enabled": enabled,
    }


def meter(name, r, pace):
    return {
        "lane": name,
        "r": r,
        "pace": pace,
        "remaining_weekly": r,
        "status": "unknown" if r is None else "ok",
    }


class DashboardModelTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "project"
        (self.root / ".git").mkdir(parents=True)
        self.nested = self.root / "src" / "pkg"
        self.nested.mkdir(parents=True)
        self.config = Path(self.temp.name) / "config"
        self.meters = Path(self.temp.name) / "usage.json"
        lanes = {
            "version": "delegate-lanes.v1",
            "meters": {
                "codex-a": {"harness": "codex", "plan": "A", "price_month": 1, "probe": "fixture"},
                "codex-b": {"harness": "codex", "plan": "B", "price_month": 1, "probe": "fixture"},
                "claude": {"harness": "claude", "plan": "C", "price_month": 1, "probe": "fixture"},
                "grok": {"harness": "grok", "plan": "G", "price_month": 1, "probe": "fixture"},
            },
            "lanes": {
                "luna-low@codex": lane("codex", "gpt-5.6-luna", "low", "codex-a", 1, 1),
                "luna-high@codex": lane("codex", "gpt-5.6-luna", "high", "codex-a", 1, 2, enabled=False),
                "terra-high@codex": lane("codex", "gpt-5.6-terra", "high", "codex-a", 2, 1),
                "sol-high@codex": lane("codex", "gpt-5.6-sol", "high", "codex-b", 2, 2),
                "fable-xhigh@claude": lane("claude", "claude-fable-5-1", "xhigh", "claude", 3, 1),
                "opus-high@claude": lane("claude", "claude-opus-5", "high", "claude", 3, 2),
                "grok46-high@grok": lane("grok", "grok-4-6", "high", "grok", 4, 1),
            },
        }
        routing = {
            "version": "delegate-routing.v1",
            "classes": {
                "scout": {"floor": 1, "ceiling": 2},
                "mechanical": {"floor": 1, "ceiling": 2},
                "impl": {"floor": 2, "ceiling": 3},
                "review": {"floor": 3, "ceiling": 3},
                "hard-impl": {"floor": 3, "ceiling": 3},
            },
            "margin": 0.2,
            "gate": 0.1,
        }
        write_json(self.config / "lanes.json", lanes)
        write_json(self.config / "routing.json", routing)
        self.write_meters(a_r=0.7, a_pace=0.5, b_r=0.7, b_pace=0.6)

    def tearDown(self):
        self.temp.cleanup()

    def write_meters(self, *, a_r, a_pace, b_r, b_pace):
        write_json(
            self.meters,
            {
                "probed_at": 100,
                "lanes": [
                    meter("codex-a", a_r, a_pace),
                    meter("codex-b", b_r, b_pace),
                    meter("claude", 0.8, 0.7),
                    meter("grok", 0.9, 0.8),
                ],
            },
        )

    def make_model(self, meters=None):
        return DashboardModel(
            cwd=self.nested,
            config_dir=self.config,
            meters_path=self.meters if meters is None else meters,
            present={"codex", "claude", "grok"},
        )

    def test_project_is_resolved_once_and_remains_pinned(self):
        dashboard = self.make_model()
        other = Path(self.temp.name) / "other"
        (other / ".git").mkdir(parents=True)
        previous = Path.cwd()
        try:
            os.chdir(other)
            dashboard.refresh()
        finally:
            os.chdir(previous)
        self.assertEqual(dashboard.project_root, self.root.resolve())
        self.assertEqual(dashboard.state["project"]["root"], str(self.root.resolve()))

    def test_four_tiers_show_carried_lanes_in_effective_order(self):
        state = self.make_model().state
        self.assertEqual([tier["tier"] for tier in state["tiers"]], [1, 2, 3, 4])
        shown = [row["lane"] for tier in state["tiers"] for row in tier["rows"]]
        self.assertNotIn("luna-high@codex", shown)
        self.assertEqual(
            [row["lane"] for row in state["tiers"][1]["rows"]],
            ["terra-high@codex", "sol-high@codex"],
        )
        row = state["tiers"][1]["rows"][0]
        self.assertEqual(
            set(row),
            {"lane", "model", "effort", "harness", "meter", "remaining", "pace", "eligible", "reason", "order", "order_source", "tier_source"},
        )
        self.assertEqual(state["usage"]["label"], "Global subscription usage")

    def test_order_sources_distinguish_project_from_global_fallback(self):
        state = self.make_model().state
        global_path = str((self.config / "lanes.json").resolve())
        self.assertTrue(all(row["order_source"] == global_path
                            for tier in state["tiers"] for row in tier["rows"]))

        global_lanes = json.loads((self.config / "lanes.json").read_text())
        del global_lanes["lanes"]["fable-xhigh@claude"]["order"]
        write_json(self.config / "lanes.json", global_lanes)
        project_policy = self.root / ".delegate" / "routing.json"
        write_json(project_policy, {"project_order": ["opus-high@claude"]})
        state = self.make_model().state
        rows = state["tiers"][2]["rows"]
        self.assertEqual([(row["lane"], row["order"], row["order_source"]) for row in rows], [
            ("opus-high@claude", 1, str(project_policy.resolve())),
            ("fable-xhigh@claude", 2, global_path),
        ])
        self.assertEqual(state["tiers"][2]["leader"], "opus-high@claude")

    def test_meter_byte_change_hot_reloads_leader_and_reason(self):
        dashboard = self.make_model()
        before = dashboard.state["revision"]
        self.assertEqual(dashboard.state["tiers"][1]["leader"], "terra-high@codex")
        self.write_meters(a_r=0.7, a_pace=0.5, b_r=0.7, b_pace=0.8)
        self.assertTrue(dashboard.refresh_if_changed())
        self.assertGreater(dashboard.state["revision"], before)
        tier = dashboard.state["tiers"][1]
        self.assertEqual(tier["leader"], "sol-high@codex")
        leader = next(row for row in tier["rows"] if row["lane"] == tier["leader"])
        self.assertEqual(leader["reason"], "stolen by pace: 0.8 >= 0.5 + 0.2")

    def test_project_policy_byte_change_hot_reloads_gate_and_source(self):
        self.write_meters(a_r=0.05, a_pace=0.5, b_r=0.7, b_pace=0.6)
        dashboard = self.make_model()
        tier = dashboard.state["tiers"][1]
        self.assertEqual(tier["leader"], "sol-high@codex")
        terra = next(row for row in tier["rows"] if row["lane"] == "terra-high@codex")
        self.assertIn("vetoed:gate", terra["reason"])

        project_policy = self.root / ".delegate" / "routing.json"
        write_json(project_policy, {"version": "delegate-routing.v1", "gate": 0.0})
        self.assertTrue(dashboard.refresh_if_changed())
        self.assertEqual(dashboard.state["policy"]["gate"]["display"], "0%")
        self.assertEqual(dashboard.state["policy"]["gate"]["source"], str(project_policy.resolve()))
        self.assertEqual(dashboard.state["tiers"][1]["leader"], "terra-high@codex")

    def test_fractional_percentages_round_trip_through_display_and_prefilled_editor(self):
        project_policy = self.root / ".delegate" / "routing.json"
        write_json(
            project_policy,
            {
                "version": "delegate-routing.v1",
                "gate": 0.1234567,
                "margin": 0.0075,
            },
        )
        dashboard = self.make_model()

        self.assertEqual(dashboard.state["policy"]["gate"]["display"], "12.34567%")
        self.assertEqual(dashboard.state["policy"]["margin"]["display"], "0.75%")
        edit = dashboard.begin_percentage_edit("gate")
        self.assertEqual(edit.text, "12.34567")

        self.assertTrue(dashboard.save_percentage_edit(edit, "12.345678"))
        self.assertEqual(json.loads(project_policy.read_text())["gate"], 0.12345678)
        self.assertEqual(dashboard.state["policy"]["gate"]["display"], "12.345678%")

    def test_lowering_gate_changes_leader_and_next_class_rank(self):
        self.write_meters(a_r=0.05, a_pace=0.5, b_r=0.7, b_pace=0.6)
        global_lanes_before = (self.config / "lanes.json").read_bytes()
        global_routing_before = (self.config / "routing.json").read_bytes()
        meters_before = self.meters.read_bytes()
        project_policy = self.root / ".delegate" / "routing.json"
        write_json(
            project_policy,
            {
                "version": "delegate-routing.v1",
                "classes": {"impl": {"ceiling": 2}},
                "note": "preserve",
            },
        )
        dashboard = self.make_model()
        self.assertEqual(dashboard.state["tiers"][1]["leader"], "sol-high@codex")

        edit = dashboard.begin_percentage_edit("gate")
        self.assertTrue(dashboard.save_percentage_edit(edit, "4.5"))
        self.assertEqual(dashboard.state["tiers"][1]["leader"], "terra-high@codex")
        saved = json.loads(project_policy.read_text())
        self.assertEqual(saved["gate"], 0.045)
        self.assertEqual(saved["note"], "preserve")
        self.assertEqual((self.config / "lanes.json").read_bytes(), global_lanes_before)
        self.assertEqual((self.config / "routing.json").read_bytes(), global_routing_before)
        self.assertEqual(self.meters.read_bytes(), meters_before)

        effective = catalog.load_catalog(cwd=self.root, config_dir=self.config)
        rows = rank.rank(
            "impl",
            effective,
            json.loads(self.meters.read_text()),
            {"codex", "claude", "grok"},
        )
        self.assertEqual(effective["routing"]["gate"], 0.045)
        self.assertEqual(rows[0]["lane"], "terra-high@codex")

    def test_margin_edit_starts_and_stops_steal_and_next_class_rank(self):
        project_policy = self.root / ".delegate" / "routing.json"
        write_json(
            project_policy,
            {
                "version": "delegate-routing.v1",
                "classes": {"impl": {"ceiling": 2}},
            },
        )
        dashboard = self.make_model()
        self.assertEqual(dashboard.state["tiers"][1]["leader"], "terra-high@codex")

        self.assertTrue(
            dashboard.save_percentage_edit(
                dashboard.begin_percentage_edit("margin"),
                "10",
            )
        )
        self.assertEqual(dashboard.state["tiers"][1]["leader"], "sol-high@codex")
        effective = catalog.load_catalog(cwd=self.root, config_dir=self.config)
        rows = rank.rank(
            "impl",
            effective,
            json.loads(self.meters.read_text()),
            {"codex", "claude", "grok"},
        )
        self.assertEqual(effective["routing"]["margin"], 0.1)
        self.assertEqual(rows[0]["lane"], "sol-high@codex")

        self.assertTrue(
            dashboard.save_percentage_edit(
                dashboard.begin_percentage_edit("margin"),
                "10.01",
            )
        )
        self.assertEqual(dashboard.state["tiers"][1]["leader"], "terra-high@codex")
        effective = catalog.load_catalog(cwd=self.root, config_dir=self.config)
        rows = rank.rank(
            "impl",
            effective,
            json.loads(self.meters.read_text()),
            {"codex", "claude", "grok"},
        )
        self.assertEqual(effective["routing"]["margin"], 0.1001)
        self.assertEqual(rows[0]["lane"], "terra-high@codex")

    def test_bad_percentage_values_preserve_policy_bytes_and_other_keys(self):
        project_policy = self.root / ".delegate" / "routing.json"
        original = {
            "version": "delegate-routing.v1",
            "gate": 0.15,
            "note": "unchanged",
        }
        write_json(project_policy, original)
        before = project_policy.read_bytes()
        dashboard = self.make_model()

        for value in ("", "not-a-number", "NaN", "Infinity", "-0.01", "100.01"):
            with self.subTest(value=value):
                edit = dashboard.begin_percentage_edit("gate")
                self.assertFalse(dashboard.save_percentage_edit(edit, value))
                self.assertEqual(project_policy.read_bytes(), before)
                self.assertEqual(dashboard.state["save"]["status"], "error")
        self.assertEqual(json.loads(project_policy.read_text()), original)

    def test_policy_reload_during_percentage_entry_conflicts_from_starting_snapshot(self):
        project_policy = self.root / ".delegate" / "routing.json"
        write_json(project_policy, {"version": "delegate-routing.v1", "note": "loaded"})
        dashboard = self.make_model()
        edit = dashboard.begin_percentage_edit("gate")

        write_json(project_policy, {"version": "delegate-routing.v1", "note": "external"})
        external = project_policy.read_bytes()
        self.assertTrue(dashboard.refresh_if_changed())
        self.assertFalse(dashboard.save_percentage_edit(edit, "25"))
        self.assertEqual(project_policy.read_bytes(), external)
        self.assertEqual(dashboard.state["save"]["status"], "conflict")
        edit2 = dashboard.begin_percentage_edit("gate")
        self.assertTrue(dashboard.save_percentage_edit(edit2, "25"))
        self.assertEqual(json.loads(project_policy.read_text())["gate"], 0.25)
        self.assertEqual(json.loads(project_policy.read_text())["note"], "external")
        self.assertEqual(dashboard.state["save"]["status"], "saved")

    def test_global_edit_during_percentage_entry_conflicts_then_saves(self):
        project_policy = self.root / ".delegate" / "routing.json"
        dashboard = self.make_model()
        edit = dashboard.begin_percentage_edit("gate")
        self.assertEqual(edit.text, "10")

        routing_path = self.config / "routing.json"
        routing = json.loads(routing_path.read_text())
        routing["gate"] = 0.5
        write_json(routing_path, routing)
        self.assertTrue(dashboard.refresh_if_changed())
        self.assertFalse(dashboard.save_percentage_edit(edit, edit.text))
        self.assertFalse(project_policy.exists())
        self.assertEqual(dashboard.state["save"]["status"], "conflict")
        self.assertEqual(dashboard.state["policy"]["gate"]["display"], "50%")

        edit2 = dashboard.begin_percentage_edit("gate")
        self.assertTrue(dashboard.save_percentage_edit(edit2, "25"))
        self.assertEqual(json.loads(project_policy.read_text())["gate"], 0.25)

    def test_identical_project_policy_proposal_is_a_noop_save(self):
        project_policy = self.root / ".delegate" / "routing.json"
        document = {"version": "delegate-routing.v1", "gate": 0.15, "note": "keep"}
        write_json(project_policy, document)
        before = project_policy.read_bytes()
        mtime = project_policy.stat().st_mtime_ns
        dashboard = self.make_model()

        self.assertTrue(dashboard.save_project_policy(dict(document)))
        self.assertEqual(dashboard.state["save"]["status"], "saved")
        self.assertEqual(project_policy.read_bytes(), before)
        self.assertEqual(project_policy.stat().st_mtime_ns, mtime)

    def test_percentage_editor_escape_cancels_without_saving(self):
        project_policy = self.root / ".delegate" / "routing.json"
        write_json(project_policy, {"version": "delegate-routing.v1", "gate": 0.15})
        before = project_policy.read_bytes()
        dashboard = self.make_model()
        editor = PercentageEditor(dashboard, "gate")
        self.assertEqual(editor.text, "15")

        self.assertFalse(editor.feed("\x1b"))
        self.assertEqual(project_policy.read_bytes(), before)
        self.assertEqual(dashboard.state["save"]["status"], "idle")

    def test_key_stream_preserves_batched_text_and_escape_sequences(self):
        pending = "g12.5\rj\x1b[B"
        keys = []
        while pending:
            key, pending = pop_key(pending)
            self.assertIsNotNone(key)
            keys.append(key)
        self.assertEqual(keys, ["g", "1", "2", ".", "5", "\r", "j", "\x1b[B"])

        key, pending = pop_key("\x1b[")
        self.assertIsNone(key)
        self.assertEqual(pending, "\x1b[")
        key, pending = pop_key(pending + "A")
        self.assertEqual((key, pending), ("\x1b[A", ""))

        dashboard = self.make_model()
        editor = PercentageEditor(dashboard, "margin")
        pending = "10.01\r"
        active = True
        while pending:
            key, pending = pop_key(pending)
            active = editor.feed(key)
        self.assertFalse(active)
        self.assertEqual(dashboard.state["policy"]["margin"]["display"], "10.01%")

    def _tier_lane_names(self, state):
        return {tier["tier"]: [row["lane"] for row in tier["rows"]] for tier in state["tiers"]}

    def _plan_project_order(self, lane, position, project_doc, project_policy):
        lanes_doc = json.loads((self.config / "lanes.json").read_text())
        routing_doc = json.loads((self.config / "routing.json").read_text())
        files = {
            "lanes": str((self.config / "lanes.json").resolve()),
            "routing": str((self.config / "routing.json").resolve()),
            "project": str(project_policy.resolve()),
        }
        # Ticket 32 gave every planner a project-lanes slot before `values`.
        _dest, _lanes, _routing, planned, _project_lanes, values = catalog._plan_order(
            lane,
            position,
            "project",
            lanes_doc,
            routing_doc,
            project_doc,
            files,
        )
        return planned["project_order"], values

    def test_move_writes_plan_order_and_preserves_other_tiers(self):
        project_policy = self.root / ".delegate" / "routing.json"
        original = {
            "version": "delegate-routing.v1",
            "classes": {"scout": {"floor": 2}},
            "gate": 0.15,
            "note": "keep this",
            "project_order": ["opus-high@claude", "fable-xhigh@claude"],
        }
        write_json(project_policy, original)
        before = project_policy.read_bytes()
        dashboard = self.make_model()
        other_tiers_before = {
            tier: names
            for tier, names in self._tier_lane_names(dashboard.state).items()
            if tier != 2
        }
        planned_order, planned_values = self._plan_project_order(
            "sol-high@codex", 1, original, project_policy
        )

        self.assertFalse(dashboard.move_lane("terra-high@codex", -1))
        self.assertEqual(project_policy.read_bytes(), before)
        self.assertEqual(dashboard.state["save"]["status"], "error")
        self.assertFalse(dashboard.move_lane("sol-high@codex", 1))
        self.assertEqual(project_policy.read_bytes(), before)

        self.assertTrue(dashboard.move_lane("sol-high@codex", -1))
        saved = json.loads(project_policy.read_text())
        for key in ("classes", "gate", "note", "version"):
            self.assertEqual(saved[key], original[key])
            self.assertEqual(json.dumps(saved[key], sort_keys=True), json.dumps(original[key], sort_keys=True))
        self.assertEqual(saved["project_order"], planned_order)
        self.assertEqual(
            planned_values["sequence"]["resulting"],
            ["sol-high@codex", "terra-high@codex"],
        )
        self.assertEqual(
            saved["project_order"],
            ["opus-high@claude", "fable-xhigh@claude", "sol-high@codex", "terra-high@codex"],
        )
        other_tiers_after = {
            tier: names
            for tier, names in self._tier_lane_names(dashboard.state).items()
            if tier != 2
        }
        self.assertEqual(other_tiers_after, other_tiers_before)
        self.assertEqual(dashboard.state["save"]["status"], "saved")
        self.assertEqual(dashboard.state["tiers"][1]["leader"], "sol-high@codex")

        effective = catalog.load_catalog(cwd=self.root, config_dir=self.config)
        rows = rank.rank(
            "impl",
            effective,
            json.loads(self.meters.read_text()),
            {"codex", "claude", "grok"},
        )
        self.assertEqual(rows[0]["lane"], "sol-high@codex")
        self.assertEqual(
            [name for name, lane in sorted(
                ((n, l) for n, l in effective["lanes"].items() if l["tier"] == 2),
                key=lambda item: item[1]["order"],
            )],
            ["sol-high@codex", "terra-high@codex"],
        )

    def test_first_move_creates_project_policy(self):
        dashboard = self.make_model()
        project_policy = self.root / ".delegate" / "routing.json"
        self.assertFalse(project_policy.exists())
        planned_order, planned_values = self._plan_project_order(
            "sol-high@codex", 1, None, project_policy
        )

        self.assertTrue(dashboard.move_lane("sol-high@codex", -1))
        saved = json.loads(project_policy.read_text())
        self.assertEqual(set(saved), {"project_order"})
        self.assertNotIn("version", saved)
        self.assertEqual(saved["project_order"], planned_order)
        self.assertEqual(
            planned_values["sequence"]["resulting"],
            ["sol-high@codex", "terra-high@codex"],
        )
        effective = catalog.load_catalog(cwd=self.root, config_dir=self.config)
        self.assertEqual(
            [name for name, lane in sorted(
                ((n, l) for n, l in effective["lanes"].items() if l["tier"] == 2),
                key=lambda item: item[1]["order"],
            )],
            ["sol-high@codex", "terra-high@codex"],
        )

    def test_save_validates_original_global_documents_and_rejects_invalid_proposal(self):
        project_policy = self.root / ".delegate" / "routing.json"
        write_json(project_policy, {"version": "delegate-routing.v1", "note": "unchanged"})
        before = project_policy.read_bytes()
        dashboard = self.make_model()
        real_validator = catalog.validate_project_routing

        with mock.patch.object(catalog, "validate_project_routing", wraps=real_validator) as validator:
            self.assertFalse(
                dashboard.save_project_policy(
                    {
                        "version": "delegate-routing.v1",
                        "classes": {"scout": {"floor": 3}},
                        "note": "individually valid, invalid after merge",
                    }
                )
            )
        self.assertEqual(project_policy.read_bytes(), before)
        self.assertEqual(dashboard.state["save"]["status"], "error")
        self.assertIn("scout", dashboard.state["save"]["detail"])
        self.assertNotIn("dashboard writes are", dashboard.state["save"]["detail"])
        global_lanes = validator.call_args.args[1]
        global_routing = validator.call_args.args[2]
        self.assertEqual(global_lanes["version"], "delegate-lanes.v1")
        self.assertIn("meters", global_lanes)
        self.assertEqual(global_routing["version"], "delegate-routing.v1")
        self.assertIn("classes", global_routing)

    def test_save_rejects_disabled_global_lane_without_refresh(self):
        project_policy = self.root / ".delegate" / "routing.json"
        original = {
            "version": "delegate-routing.v1",
            "note": "keep",
            "project_order": ["terra-high@codex", "sol-high@codex"],
        }
        write_json(project_policy, original)
        dashboard = self.make_model()
        before = project_policy.read_bytes()

        lanes = json.loads((self.config / "lanes.json").read_text())
        lanes["lanes"]["terra-high@codex"]["enabled"] = False
        write_json(self.config / "lanes.json", lanes)

        self.assertFalse(dashboard.move_lane("sol-high@codex", -1))
        self.assertEqual(project_policy.read_bytes(), before)
        self.assertEqual(dashboard.state["save"]["status"], "error")
        self.assertIsNotNone(dashboard.state["save"]["detail"])

        edit = dashboard.begin_percentage_edit("gate")
        self.assertFalse(dashboard.save_percentage_edit(edit, "25"))
        self.assertEqual(project_policy.read_bytes(), before)
        self.assertEqual(dashboard.state["save"]["status"], "error")
        self.assertEqual(json.loads(project_policy.read_text()), original)

    def test_save_rejects_stale_merged_class_constraint_without_refresh(self):
        project_policy = self.root / ".delegate" / "routing.json"
        original = {
            "version": "delegate-routing.v1",
            "classes": {"impl": {"ceiling": 2}},
            "note": "keep",
        }
        write_json(project_policy, original)
        dashboard = self.make_model()
        before = project_policy.read_bytes()

        routing = json.loads((self.config / "routing.json").read_text())
        routing["classes"]["impl"]["floor"] = 3
        write_json(self.config / "routing.json", routing)

        self.assertFalse(dashboard.move_lane("sol-high@codex", -1))
        self.assertEqual(project_policy.read_bytes(), before)
        self.assertEqual(dashboard.state["save"]["status"], "error")
        self.assertIsNotNone(dashboard.state["save"]["detail"])

        edit = dashboard.begin_percentage_edit("margin")
        self.assertFalse(dashboard.save_percentage_edit(edit, "10"))
        self.assertEqual(project_policy.read_bytes(), before)
        self.assertEqual(dashboard.state["save"]["status"], "error")
        self.assertEqual(json.loads(project_policy.read_text()), original)

    def test_save_rejects_malformed_global_after_failed_refresh(self):
        project_policy = self.root / ".delegate" / "routing.json"
        original = {
            "version": "delegate-routing.v1",
            "note": "keep",
            "gate": 0.15,
        }
        write_json(project_policy, original)
        dashboard = self.make_model()
        before = project_policy.read_bytes()

        (self.config / "lanes.json").write_text("{broken", encoding="utf-8")
        dashboard.refresh()
        self.assertIsNotNone(dashboard.state["error"])
        self.assertIn("Reload failed", dashboard.state["error"])

        self.assertFalse(dashboard.move_lane("sol-high@codex", -1))
        self.assertEqual(project_policy.read_bytes(), before)
        self.assertEqual(dashboard.state["save"]["status"], "error")
        self.assertIsNotNone(dashboard.state["save"]["detail"])

        edit = dashboard.begin_percentage_edit("gate")
        self.assertFalse(dashboard.save_percentage_edit(edit, "20"))
        self.assertEqual(project_policy.read_bytes(), before)
        self.assertEqual(dashboard.state["save"]["status"], "error")
        self.assertEqual(json.loads(project_policy.read_text()), original)

    def test_save_still_succeeds_against_valid_fresh_globals(self):
        project_policy = self.root / ".delegate" / "routing.json"
        write_json(project_policy, {"version": "delegate-routing.v1", "note": "keep"})
        dashboard = self.make_model()

        routing = json.loads((self.config / "routing.json").read_text())
        routing["gate"] = 0.05
        write_json(self.config / "routing.json", routing)
        self.assertTrue(dashboard.move_lane("sol-high@codex", -1))
        self.assertEqual(dashboard.state["policy"]["gate"]["value"], 0.05)
        saved = json.loads(project_policy.read_text())
        self.assertEqual(saved["note"], "keep")
        self.assertEqual(dashboard.state["save"]["status"], "saved")

    def test_external_edit_conflicts_without_overwriting_and_next_action_can_save(self):
        project_policy = self.root / ".delegate" / "routing.json"
        write_json(project_policy, {"version": "delegate-routing.v1", "note": "loaded"})
        dashboard = self.make_model()
        write_json(project_policy, {"version": "delegate-routing.v1", "note": "external"})
        external = project_policy.read_bytes()

        self.assertFalse(dashboard.move_lane("sol-high@codex", -1))
        self.assertEqual(project_policy.read_bytes(), external)
        self.assertEqual(dashboard.state["save"]["status"], "conflict")
        self.assertEqual(dashboard.state["tiers"][1]["leader"], "terra-high@codex")

        self.assertTrue(dashboard.move_lane("sol-high@codex", -1))
        self.assertEqual(json.loads(project_policy.read_text())["note"], "external")
        self.assertEqual(dashboard.state["save"]["status"], "saved")

    def test_policy_change_during_refresh_remains_pending_for_another_reload(self):
        project_policy = self.root / ".delegate" / "routing.json"
        write_json(project_policy, {"version": "delegate-routing.v1", "gate": 0.1})
        dashboard = self.make_model()
        real_leaders = rank.tier_leaders
        changed = False

        def change_after_catalog_load(*args, **kwargs):
            nonlocal changed
            result = real_leaders(*args, **kwargs)
            if not changed:
                changed = True
                write_json(project_policy, {"version": "delegate-routing.v1", "gate": 0.3})
            return result

        with mock.patch.object(rank, "tier_leaders", side_effect=change_after_catalog_load):
            dashboard.refresh()
        self.assertEqual(dashboard.state["policy"]["gate"]["display"], "10%")
        self.assertTrue(dashboard.refresh_if_changed())
        self.assertEqual(dashboard.state["policy"]["gate"]["display"], "30%")

    def test_project_routing_symlink_is_never_replaced_or_followed_for_save(self):
        project_policy = self.root / ".delegate" / "routing.json"
        project_policy.parent.mkdir(parents=True)
        project_policy.symlink_to(self.config / "routing.json")
        global_before = (self.config / "routing.json").read_bytes()
        dashboard = self.make_model()

        self.assertFalse(dashboard.move_lane("sol-high@codex", -1))
        self.assertTrue(project_policy.is_symlink())
        self.assertEqual((self.config / "routing.json").read_bytes(), global_before)
        self.assertEqual(dashboard.state["save"]["status"], "error")

        edit = dashboard.begin_percentage_edit("gate")
        self.assertFalse(dashboard.save_percentage_edit(edit, "25"))
        self.assertTrue(project_policy.is_symlink())
        self.assertEqual((self.config / "routing.json").read_bytes(), global_before)
        self.assertEqual(dashboard.state["save"]["status"], "error")

    def test_symlinked_policy_directory_cannot_write_outside_pinned_project(self):
        outside = Path(self.temp.name) / "other-policy"
        target = outside / "routing.json"
        write_json(target, {"note": "belongs to another project"})
        (self.root / ".delegate").symlink_to(outside, target_is_directory=True)
        before = target.read_bytes()
        dashboard = self.make_model()

        self.assertFalse(dashboard.move_lane("sol-high@codex", -1))
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual(dashboard.state["save"]["status"], "error")

        edit = dashboard.begin_percentage_edit("margin")
        self.assertFalse(dashboard.save_percentage_edit(edit, "10"))
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual(dashboard.state["save"]["status"], "error")

    def test_missing_and_malformed_meter_cache_are_unknown_not_invented(self):
        missing = Path(self.temp.name) / "missing.json"
        state = self.make_model(missing).state
        self.assertEqual(state["usage"]["status"], "missing")
        self.assertTrue(all(row["remaining"] is None and row["pace"] is None
                            for tier in state["tiers"] for row in tier["rows"]))
        self.meters.write_text("{broken", encoding="utf-8")
        state = self.make_model().state
        self.assertEqual(state["usage"]["status"], "malformed")
        self.assertTrue(all(row["remaining"] is None and row["pace"] is None
                            for tier in state["tiers"] for row in tier["rows"]))

    def test_nonfinite_or_unrepresentable_meter_cache_is_malformed_and_json_safe(self):
        self.meters.write_text(
            '{"probed_at":100,"lanes":['
            '{"lane":"codex-a","r":0.7,"pace":1e309,"remaining_weekly":0.7,"status":"ok"},'
            '{"lane":"codex-b","r":0.7,"pace":0.6,"remaining_weekly":0.7,"status":"ok"},'
            '{"lane":"claude","r":0.8,"pace":0.7,"remaining_weekly":0.8,"status":"ok"},'
            '{"lane":"grok","r":0.9,"pace":0.8,"remaining_weekly":0.9,"status":"ok"}'
            "]}",
            encoding="utf-8",
        )
        state = self.make_model().state
        self.assertEqual(state["usage"]["status"], "malformed")
        self.assertTrue(
            all(
                row["remaining"] is None and row["pace"] is None
                for tier in state["tiers"]
                for row in tier["rows"]
            )
        )
        json.dumps(state, allow_nan=False)

        huge = "1" + "0" * 400
        self.meters.write_text(
            '{"probed_at":100,"lanes":['
            f'{{"lane":"codex-a","r":0.7,"pace":{huge},"remaining_weekly":0.7,"status":"ok"}}'
            "]}",
            encoding="utf-8",
        )
        state = self.make_model().state
        self.assertEqual(state["usage"]["status"], "malformed")
        json.dumps(state, allow_nan=False)

    def test_invalid_cache_timestamp_is_unknown_and_json_safe_for_all_callers(self):
        effective = catalog.load_catalog(cwd=self.root, config_dir=self.config)
        for timestamp in ('1e309', '"yesterday"', 'true', '1' + '0' * 400):
            with self.subTest(timestamp=timestamp):
                raw = ('{"probed_at":' + timestamp + ',"lanes":['
                       '{"lane":"codex-a","r":0.01,"pace":0.5}]}')
                self.meters.write_text(raw, encoding="utf-8")
                dashboard = self.make_model()
                self.assertEqual(dashboard.state["usage"]["status"], "malformed")
                self.assertIsNone(dashboard.state["usage"]["probed_at"])
                json.dumps(dashboard.state, allow_nan=False)
                self.assertEqual(
                    rank.rank("impl", effective, json.loads(raw), dashboard.present),
                    rank.rank("impl", effective, {}, dashboard.present),
                )

    def test_cache_validity_matches_canonical_rank_for_wrapped_and_legacy_inputs(self):
        self.write_meters(a_r=0.05, a_pace=0.5, b_r=0.7, b_pace=0.8)
        healthy = json.loads(self.meters.read_text())
        mixed = {"lanes": healthy["lanes"] + [{"lane": "unused", "pace": "bad"}]}
        legacy = {entry["lane"]: entry for entry in healthy["lanes"]}
        legacy["probed_at"] = {"status": "unknown"}
        for document, status in ((mixed, "malformed"), (legacy, "ok")):
            with self.subTest(status=status):
                write_json(self.meters, document)
                dashboard = self.make_model()
                effective = catalog.load_catalog(cwd=self.root, config_dir=self.config)
                previews = rank.tier_leaders(effective, document, dashboard.present)
                self.assertEqual(
                    [tier["leader"] for tier in dashboard.state["tiers"]],
                    [tier["leader"] for tier in previews],
                )
                self.assertEqual(dashboard.state["usage"]["status"], status)
                self.assertIsNone(dashboard.state["usage"]["probed_at"])
                for shown, preview in zip(dashboard.state["tiers"], previews):
                    expected = {row["lane"]: row for row in preview["rows"]}
                    for row in shown["rows"]:
                        self.assertEqual(row["eligible"], expected[row["lane"]]["eligible"])
                        self.assertEqual(row["reason"], expected[row["lane"]]["reason"])
                canonical = rank.rank("impl", effective, document, dashboard.present)
                expected_input = {} if status == "malformed" else healthy
                self.assertEqual(canonical, rank.rank("impl", effective, expected_input, dashboard.present))
                json.dumps(canonical, allow_nan=False)

    def test_meters_absent_is_on_with_empty_effect(self):
        state = self.make_model().state
        meters = state["policy"]["meters"]
        self.assertEqual(
            set(meters),
            {"value", "display", "source", "effect"},
        )
        self.assertEqual(meters["value"], True)
        self.assertEqual(meters["display"], "on")
        self.assertIsNone(meters["source"])
        self.assertEqual(meters["effect"], "")

    def test_meters_off_from_global_or_project_and_gate_does_not_veto(self):
        self.write_meters(a_r=0.05, a_pace=0.5, b_r=0.7, b_pace=0.8)
        cases = (
            ("global", self.config / "routing.json"),
            ("project", self.root / ".delegate" / "routing.json"),
        )
        for source_kind, expected_source in cases:
            with self.subTest(source=source_kind):
                routing = json.loads((self.config / "routing.json").read_text())
                routing.pop("meters", None)
                write_json(self.config / "routing.json", routing)
                project_policy = self.root / ".delegate" / "routing.json"
                if project_policy.exists() or project_policy.is_symlink():
                    project_policy.unlink()
                if source_kind == "global":
                    routing["meters"] = False
                    write_json(self.config / "routing.json", routing)
                else:
                    write_json(project_policy, {"meters": False})
                dashboard = self.make_model()
                meters = dashboard.state["policy"]["meters"]
                self.assertEqual(meters["value"], False)
                self.assertEqual(meters["display"], "off")
                self.assertEqual(meters["source"], str(expected_source.resolve()))
                self.assertEqual(meters["effect"], METERS_OFF_EFFECT)
                self.assertEqual(
                    meters["effect"],
                    "Gate, Margin and Pace inactive; Remaining is cached",
                )
                effective = catalog.load_catalog(cwd=self.root, config_dir=self.config)
                previews = rank.tier_leaders(
                    effective,
                    json.loads(self.meters.read_text()),
                    dashboard.present,
                )
                self.assertEqual(
                    [tier["leader"] for tier in dashboard.state["tiers"]],
                    [preview["leader"] for preview in previews],
                )
                terra = next(
                    row
                    for row in dashboard.state["tiers"][1]["rows"]
                    if row["lane"] == "terra-high@codex"
                )
                self.assertNotIn("vetoed:gate", terra["reason"])
                self.assertEqual(dashboard.state["tiers"][1]["leader"], "terra-high@codex")
                self.assertEqual(dashboard.state["tiers"][1]["leader"], previews[1]["leader"])

    def test_intervening_edit_mark_matches_catalog_message(self):
        source = Path(catalog.__file__).read_text(encoding="utf-8")
        self.assertIn(INTERVENING_EDIT_MARK, source)
        self.assertEqual(
            INTERVENING_EDIT_MARK,
            "intervening edit: source documents or resolved paths changed; preview again",
        )

    def test_intervening_global_edit_between_preview_and_apply_is_conflict(self):
        project_policy = self.root / ".delegate" / "routing.json"
        original = {"version": "delegate-routing.v1", "gate": 0.15, "note": "keep"}
        write_json(project_policy, original)
        real_edit = catalog.edit_catalog

        def wrap_with_global_change(which):
            def wrapper(*args, **kwargs):
                if kwargs.get("apply"):
                    if which == "lanes":
                        path = self.config / "lanes.json"
                    else:
                        path = self.config / "routing.json"
                    doc = json.loads(path.read_text())
                    doc["note"] = "intervening global"
                    write_json(path, doc)
                return real_edit(*args, **kwargs)
            return wrapper

        for action, which in (("move", "lanes"), ("gate", "routing")):
            with self.subTest(action=action, source=which):
                write_json(project_policy, original)
                dashboard = self.make_model()
                before = project_policy.read_bytes()
                with mock.patch.object(catalog, "edit_catalog", side_effect=wrap_with_global_change(which)):
                    if action == "move":
                        saved = dashboard.move_lane("sol-high@codex", -1)
                    else:
                        saved = dashboard.save_percentage_edit(
                            dashboard.begin_percentage_edit("gate"),
                            "20",
                        )
                self.assertFalse(saved)
                self.assertEqual(dashboard.state["save"]["status"], "conflict")
                self.assertEqual(project_policy.read_bytes(), before)
                self.assertEqual(json.loads(project_policy.read_text()), original)

    def test_noop_gate_save_leaves_bytes_and_mtime_and_reports_saved(self):
        project_policy = self.root / ".delegate" / "routing.json"
        write_json(project_policy, {"version": "delegate-routing.v1", "gate": 0.15, "note": "same"})
        dashboard = self.make_model()
        before = project_policy.read_bytes()
        mtime = project_policy.stat().st_mtime_ns
        edit = dashboard.begin_percentage_edit("gate")
        self.assertTrue(dashboard.save_percentage_edit(edit, "15"))
        self.assertEqual(project_policy.read_bytes(), before)
        self.assertEqual(project_policy.stat().st_mtime_ns, mtime)
        self.assertEqual(dashboard.state["save"]["status"], "saved")

    def test_move_at_tier_boundary_is_refused_without_writing(self):
        project_policy = self.root / ".delegate" / "routing.json"
        original = {
            "version": "delegate-routing.v1",
            "project_order": ["terra-high@codex", "sol-high@codex"],
        }
        write_json(project_policy, original)
        dashboard = self.make_model()
        before = project_policy.read_bytes()
        mtime = project_policy.stat().st_mtime_ns
        self.assertFalse(dashboard.move_lane("terra-high@codex", -1))
        self.assertEqual(project_policy.read_bytes(), before)
        self.assertEqual(project_policy.stat().st_mtime_ns, mtime)
        self.assertEqual(dashboard.state["save"]["status"], "error")
        self.assertFalse(dashboard.move_lane("sol-high@codex", 1))
        self.assertEqual(project_policy.read_bytes(), before)
        self.assertEqual(project_policy.stat().st_mtime_ns, mtime)

    def test_move_lane_refuses_stale_global_order_or_tier_without_writing(self):
        dashboard = self.make_model()
        project_policy = self.root / ".delegate" / "routing.json"
        self.assertFalse(project_policy.exists())
        self.assertEqual(
            [row["lane"] for row in dashboard.state["tiers"][1]["rows"]],
            ["terra-high@codex", "sol-high@codex"],
        )

        lanes = json.loads((self.config / "lanes.json").read_text())
        lanes["lanes"]["terra-high@codex"]["order"] = 2
        lanes["lanes"]["sol-high@codex"]["order"] = 1
        write_json(self.config / "lanes.json", lanes)
        self.assertFalse(dashboard.move_lane("sol-high@codex", -1))
        self.assertFalse(project_policy.exists())
        self.assertEqual(dashboard.state["save"]["status"], "conflict")
        self.assertEqual(
            [row["lane"] for row in dashboard.state["tiers"][1]["rows"]],
            ["sol-high@codex", "terra-high@codex"],
        )
        self.assertTrue(dashboard.move_lane("terra-high@codex", -1))
        self.assertEqual(
            json.loads(project_policy.read_text())["project_order"],
            ["terra-high@codex", "sol-high@codex"],
        )

        dashboard = self.make_model()
        before = project_policy.read_bytes()
        lanes = json.loads((self.config / "lanes.json").read_text())
        lanes["lanes"]["sol-high@codex"]["tier"] = 3
        lanes["lanes"]["sol-high@codex"]["order"] = 3
        write_json(self.config / "lanes.json", lanes)
        self.assertFalse(dashboard.move_lane("sol-high@codex", -1))
        self.assertEqual(project_policy.read_bytes(), before)
        self.assertEqual(dashboard.state["save"]["status"], "conflict")

    def test_project_path_resolving_to_a_global_file_is_refused(self):
        """A project document that is a global document opens no pane at all.

        Before ticket 32 the project had one document and the pane opened, then
        refused each save. It has two now, and pinning the config at the
        project's own `.delegate` makes both of them global files, so the pane
        cannot even read a catalog. Refusing at construction is the same rule
        held one step earlier, and it covers `lanes.json` as well.
        """
        config = self.root / ".delegate"
        config.mkdir(parents=True)
        write_json(config / "lanes.json", json.loads((self.config / "lanes.json").read_text()))
        write_json(config / "routing.json", json.loads((self.config / "routing.json").read_text()))
        before = {
            name: (config / name).read_bytes() for name in ("lanes.json", "routing.json")
        }
        with self.assertRaises(DashboardError) as caught:
            DashboardModel(
                cwd=self.nested,
                config_dir=config,
                meters_path=self.meters,
                present={"codex", "claude", "grok"},
            )
        self.assertIn("resolves to", str(caught.exception))
        for name, raw in before.items():
            self.assertEqual((config / name).read_bytes(), raw)

    def test_project_lanes_resolving_to_the_global_catalog_is_refused(self):
        """The same refusal reached through a link on `.delegate/lanes.json`."""
        project_delegate = self.root / ".delegate"
        project_delegate.mkdir(parents=True)
        (project_delegate / "lanes.json").symlink_to(self.config / "lanes.json")
        before = (self.config / "lanes.json").read_bytes()
        with self.assertRaises(DashboardError) as caught:
            self.make_model()
        self.assertIn("project Lanes", str(caught.exception))
        self.assertIn("global lane catalog", str(caught.exception))
        self.assertEqual((self.config / "lanes.json").read_bytes(), before)

    def test_a_project_tier_is_carried_into_the_state(self):
        """Ticket 32: a project Tier moves the Lane and the row says whose it is."""
        dashboard = self.make_model()
        self.assertEqual(dashboard._tier_of("sol-high@codex"), 2)
        self.assertEqual(dashboard.state["project_tiers"], {})

        write_json(
            self.root / ".delegate" / "lanes.json",
            {"lanes": {"sol-high@codex": {"tier": 1}}},
        )
        self.assertTrue(dashboard.refresh_if_changed())
        self.assertEqual(dashboard._tier_of("sol-high@codex"), 1)
        self.assertEqual(
            dashboard.state["project_tiers"]["sol-high@codex"], {"from": 2, "to": 1}
        )
        moved = [
            row
            for tier in dashboard.state["tiers"]
            for row in tier["rows"]
            if row["lane"] == "sol-high@codex"
        ]
        self.assertEqual(len(moved), 1)
        self.assertEqual(moved[0]["tier_source"], "project")
        others = [
            row["tier_source"]
            for tier in dashboard.state["tiers"]
            for row in tier["rows"]
            if row["lane"] != "sol-high@codex"
        ]
        self.assertEqual(set(others), {"global"})

    def test_unsafe_target_after_preview_is_refused_on_both_save_paths(self):
        project_policy = self.root / ".delegate" / "routing.json"
        write_json(project_policy, {"version": "delegate-routing.v1", "gate": 0.15, "note": "keep"})
        global_before = (self.config / "routing.json").read_bytes()
        real_edit = catalog.edit_catalog

        def replace_with_symlink_after_preview(*args, **kwargs):
            result = real_edit(*args, **kwargs)
            if not kwargs.get("apply"):
                if project_policy.exists() and not project_policy.is_symlink():
                    project_policy.unlink()
                if not project_policy.is_symlink():
                    project_policy.symlink_to(self.config / "routing.json")
            return result

        for action in ("move", "gate"):
            with self.subTest(action=action):
                if project_policy.is_symlink() or project_policy.exists():
                    project_policy.unlink()
                write_json(project_policy, {"version": "delegate-routing.v1", "gate": 0.15, "note": "keep"})
                dashboard = self.make_model()
                with mock.patch.object(catalog, "edit_catalog", side_effect=replace_with_symlink_after_preview):
                    if action == "move":
                        saved = dashboard.move_lane("sol-high@codex", -1)
                    else:
                        saved = dashboard.save_percentage_edit(
                            dashboard.begin_percentage_edit("gate"),
                            "20",
                        )
                self.assertFalse(saved)
                self.assertEqual(dashboard.state["save"]["status"], "error")
                self.assertTrue(project_policy.is_symlink())
                self.assertEqual((self.config / "routing.json").read_bytes(), global_before)

    def test_preview_target_mismatch_is_refused_without_writing(self):
        project_policy = self.root / ".delegate" / "routing.json"
        write_json(project_policy, {"version": "delegate-routing.v1", "note": "keep"})
        before = project_policy.read_bytes()
        dashboard = self.make_model()
        real_edit = catalog.edit_catalog

        def retarget(*args, **kwargs):
            result = dict(real_edit(*args, **kwargs))
            target = dict(result.get("target") or {})
            target["file"] = str((self.config / "routing.json").resolve())
            result["target"] = target
            return result

        with mock.patch.object(catalog, "edit_catalog", side_effect=retarget):
            self.assertFalse(dashboard.move_lane("sol-high@codex", -1))
            self.assertFalse(
                dashboard.save_percentage_edit(dashboard.begin_percentage_edit("margin"), "10")
            )
        self.assertEqual(project_policy.read_bytes(), before)
        self.assertEqual(dashboard.state["save"]["status"], "error")

    def test_catalog_oserror_and_valueerror_are_save_errors(self):
        project_policy = self.root / ".delegate" / "routing.json"
        write_json(project_policy, {"version": "delegate-routing.v1", "gate": 0.15})
        before = project_policy.read_bytes()
        dashboard = self.make_model()
        for exc in (OSError("disk full"), ValueError("bad catalog value")):
            with self.subTest(exc=type(exc).__name__):
                with mock.patch.object(catalog, "edit_catalog", side_effect=exc):
                    self.assertFalse(dashboard.move_lane("sol-high@codex", -1))
                self.assertEqual(dashboard.state["save"]["status"], "error")
                self.assertEqual(project_policy.read_bytes(), before)
                with mock.patch.object(catalog, "edit_catalog", side_effect=exc):
                    self.assertFalse(
                        dashboard.save_percentage_edit(
                            dashboard.begin_percentage_edit("gate"),
                            "20",
                        )
                    )
                self.assertEqual(dashboard.state["save"]["status"], "error")
                self.assertEqual(project_policy.read_bytes(), before)

        real_edit = catalog.edit_catalog

        def raise_on_apply(*args, **kwargs):
            if kwargs.get("apply"):
                raise OSError("apply failed")
            return real_edit(*args, **kwargs)

        with mock.patch.object(catalog, "edit_catalog", side_effect=raise_on_apply):
            self.assertFalse(dashboard.move_lane("sol-high@codex", -1))
        self.assertEqual(dashboard.state["save"]["status"], "error")
        self.assertEqual(project_policy.read_bytes(), before)

    def test_keyboardinterrupt_is_not_swallowed(self):
        dashboard = self.make_model()
        with mock.patch.object(catalog, "edit_catalog", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                dashboard.move_lane("sol-high@codex", -1)
            with self.assertRaises(KeyboardInterrupt):
                dashboard.save_percentage_edit(
                    dashboard.begin_percentage_edit("gate"),
                    "20",
                )

    def test_json_command_is_noninteractive(self):
        result = subprocess.run(
            [
                sys.executable,
                str(HERE / "dashboard.py"),
                "--cwd",
                str(self.nested),
                "--config-dir",
                str(self.config),
                "--meters",
                str(self.meters),
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["project"]["root"], str(self.root.resolve()))
        self.assertEqual(len(data["tiers"]), 4)
        self.assertEqual(
            set(data["policy"]["meters"]),
            {"value", "display", "source", "effect"},
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
