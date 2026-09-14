#!/usr/bin/env python3
"""Model-boundary tests for the throwaway delegate dashboard."""

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

from model import DashboardModel

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
            {"lane", "model", "effort", "harness", "meter", "remaining", "pace", "eligible", "reason", "order"},
        )
        self.assertEqual(state["usage"]["label"], "Global subscription usage")

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

    def test_move_stays_in_tier_and_saves_complete_order(self):
        project_policy = self.root / ".delegate" / "routing.json"
        original = {
            "version": "delegate-routing.v1",
            "classes": {"scout": {"floor": 2}},
            "gate": 0.15,
            "note": "keep this",
            "project_order": ["opus-high@claude", "fable-xhigh@claude"],
        }
        write_json(project_policy, original)
        dashboard = self.make_model()

        self.assertFalse(dashboard.move_lane("terra-high@codex", -1))
        self.assertEqual(json.loads(project_policy.read_text()), original)
        self.assertEqual(dashboard.state["save"]["status"], "error")
        self.assertFalse(dashboard.move_lane("sol-high@codex", 1))
        self.assertEqual(json.loads(project_policy.read_text()), original)

        self.assertTrue(dashboard.move_lane("sol-high@codex", -1))
        saved = json.loads(project_policy.read_text())
        self.assertEqual(saved["classes"], original["classes"])
        self.assertEqual(saved["gate"], original["gate"])
        self.assertEqual(saved["note"], original["note"])
        self.assertEqual(
            saved["project_order"],
            [
                "luna-low@codex",
                "sol-high@codex",
                "terra-high@codex",
                "opus-high@claude",
                "fable-xhigh@claude",
                "grok46-high@grok",
            ],
        )
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

    def test_first_move_creates_project_policy(self):
        dashboard = self.make_model()
        project_policy = self.root / ".delegate" / "routing.json"
        self.assertFalse(project_policy.exists())

        self.assertTrue(dashboard.move_lane("sol-high@codex", -1))
        saved = json.loads(project_policy.read_text())
        self.assertEqual(saved["version"], "delegate-routing.v1")
        self.assertEqual(saved["project_order"][1:3], ["sol-high@codex", "terra-high@codex"])

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
        global_lanes = validator.call_args.args[1]
        global_routing = validator.call_args.args[2]
        self.assertEqual(global_lanes["version"], "delegate-lanes.v1")
        self.assertIn("meters", global_lanes)
        self.assertEqual(global_routing["version"], "delegate-routing.v1")
        self.assertIn("classes", global_routing)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
