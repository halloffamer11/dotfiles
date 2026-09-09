#!/usr/bin/env python3
"""test_events.py — test events.py JSONL event encoding and CLI."""
import json, os, subprocess, sys, tempfile
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
EVENTS_PY = os.path.join(HERE, "..", "events.py")
sys.path.insert(0, os.path.join(HERE, ".."))
import events


def fail(msg):
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def assert_true(cond, msg):
    if not cond:
        fail(msg)


def parse_iso(ts_str):
    try:
        dt = datetime.fromisoformat(ts_str)
        assert_true(dt.tzinfo is not None, f"ts {ts_str} missing timezone offset")
        return dt
    except Exception as e:
        fail(f"invalid ISO ts {ts_str}: {e}")


def main():
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, "sub", "ledger.jsonl")
        env = dict(os.environ, DELEGATE_LEDGER=ledger_path)

        # 1. Test meter event
        usage_fixture = {
            "probed_at": 1788403774.3,
            "probed_at_iso": "2026-09-02T23:00:00+00:00",
            "gate": 0.1,
            "rollover_min": 30,
            "lanes": [
                {
                    "lane": "agy-gemini",
                    "harness": "agy",
                    "meter": "gemini",
                    "remaining_5h": 0.87,
                    "remaining_weekly": 0.90,
                    "r": 0.87,
                    "binding": "5h",
                    "reset_5h": 1788406804,
                    "reset_weekly": 1788616225,
                    "pace": 2.58,
                    "status": "ok",
                    "note": None,
                },
                {
                    "lane": "codex",
                    "harness": "codex",
                    "meter": None,
                    "remaining_5h": 0.5,
                    "remaining_weekly": 0.7,
                    "r": 0.5,
                    "binding": "5h",
                    "reset_5h": 1788406804,
                    "reset_weekly": 1788616225,
                    "pace": 1.1,
                    "status": "ok",
                    "note": None,
                },
            ],
        }
        usage_json_path = os.path.join(tmpdir, "usage.json")
        with open(usage_json_path, "w") as f:
            json.dump(usage_fixture, f)

        # CLI invocation: meter
        res = subprocess.run([sys.executable, EVENTS_PY, "meter", usage_json_path], env=env)
        assert_true(res.returncode == 0, f"events.py meter exited {res.returncode}")

        with open(ledger_path) as f:
            lines = [l.strip() for l in f if l.strip()]
        assert_true(len(lines) == 1, f"expected 1 line in ledger, got {len(lines)}")

        m = json.loads(lines[0])
        assert_true(m.get("v") == 1, "meter event v != 1")
        assert_true(m.get("kind") == "meter", "meter event kind != 'meter'")
        assert_true(m.get("source") == "probe", "meter event source != 'probe'")
        assert_true(m.get("cache_age_s") == 0, "meter event cache_age_s != 0")
        assert_true(m.get("probed_at") == 1788403774.3, "meter event probed_at mismatch")
        assert_true(m.get("lanes") == usage_fixture["lanes"], "meter event lanes mismatch")
        parse_iso(m.get("ts"))

        # 2. Test start & finish sharing thread_id and omitted class is null
        thread_id = "550e8400-e29b-41d4-a716-446655440000"
        res = subprocess.run(
            [
                sys.executable,
                EVENTS_PY,
                "start",
                thread_id,
                "flash-high@agy",
                "-",
                "medium",
                "600",
                "/abs/dir",
                "/abs/brief.md",
                "/abs/out.json",
                "-",
            ],
            env=env,
        )
        assert_true(res.returncode == 0, f"events.py start exited {res.returncode}")

        with open(ledger_path) as f:
            lines = [l.strip() for l in f if l.strip()]
        assert_true(len(lines) == 2, f"expected 2 lines in ledger, got {len(lines)}")

        s = json.loads(lines[1])
        assert_true(s.get("v") == 1, "start event v != 1")
        assert_true(s.get("kind") == "dispatch.start", "start event kind != 'dispatch.start'")
        assert_true(s.get("thread_id") == thread_id, "start thread_id mismatch")
        assert_true(s.get("lane") == "flash-high@agy", "start lane mismatch")
        assert_true(s.get("class") is None, "start omitted class is not null")
        assert_true(s.get("effort") == "medium", "start effort mismatch")
        assert_true(s.get("timeout_s") == 600, "start timeout_s != 600")
        assert_true(s.get("cwd") == "/abs/dir", "start cwd mismatch")
        assert_true(s.get("brief") == "/abs/brief.md", "start brief mismatch")
        assert_true(s.get("out") == "/abs/out.json", "start out mismatch")
        assert_true(s.get("write") is None, "start omitted write is not null")
        parse_iso(s.get("ts"))

        res = subprocess.run(
            [
                sys.executable,
                EVENTS_PY,
                "finish",
                thread_id,
                "flash-high@agy",
                "-",
                "104",
                "0",
                "done",
                "-",
                "/abs/out.json",
            ],
            env=env,
        )
        assert_true(res.returncode == 0, f"events.py finish exited {res.returncode}")

        with open(ledger_path) as f:
            lines = [l.strip() for l in f if l.strip()]
        assert_true(len(lines) == 3, f"expected 3 lines in ledger, got {len(lines)}")

        fn = json.loads(lines[2])
        assert_true(fn.get("v") == 1, "finish event v != 1")
        assert_true(fn.get("kind") == "dispatch.finish", "finish event kind != 'dispatch.finish'")
        assert_true(fn.get("thread_id") == thread_id, "finish thread_id does not match start")
        assert_true(fn.get("lane") == "flash-high@agy", "finish lane mismatch")
        assert_true(fn.get("class") is None, "finish omitted class is not null")
        assert_true(fn.get("secs") == 104, "finish secs != 104")
        assert_true(fn.get("rc") == 0, "finish rc != 0")
        assert_true(fn.get("status") == "done", "finish status != 'done'")
        assert_true(fn.get("child_session") is None, "finish omitted child_session is not null")
        assert_true(fn.get("out") == "/abs/out.json", "finish out mismatch")
        parse_iso(fn.get("ts"))

        # 3. Test non-null class, write, child_session
        thread_id_2 = "660e8400-e29b-41d4-a716-446655440001"
        res = subprocess.run(
            [
                sys.executable,
                EVENTS_PY,
                "start",
                thread_id_2,
                "flash-high@agy",
                "scout",
                "low",
                "360",
                "/abs/dir",
                "/abs/brief.md",
                "/abs/out.json",
                "/write/worktree",
            ],
            env=env,
        )
        assert_true(res.returncode == 0, f"events.py start with class exited {res.returncode}")

        res = subprocess.run(
            [
                sys.executable,
                EVENTS_PY,
                "finish",
                thread_id_2,
                "flash-high@agy",
                "scout",
                "45",
                "0",
                "done",
                "sess-abc-123",
                "/abs/out.json",
            ],
            env=env,
        )
        assert_true(res.returncode == 0, f"events.py finish with class exited {res.returncode}")

        with open(ledger_path) as f:
            lines = [l.strip() for l in f if l.strip()]
        assert_true(len(lines) == 5, f"expected 5 lines in ledger, got {len(lines)}")

        s2 = json.loads(lines[3])
        assert_true(s2.get("class") == "scout", "start class != 'scout'")
        assert_true(s2.get("write") == "/write/worktree", "start write != '/write/worktree'")

        fn2 = json.loads(lines[4])
        assert_true(fn2.get("class") == "scout", "finish class != 'scout'")
        assert_true(fn2.get("child_session") == "sess-abc-123", "finish child_session != 'sess-abc-123'")

        # 4. Unknown CLI usage exits 2
        for bad_args in [
            [],
            ["bogus"],
            ["meter"],
            ["start", "t", "l"],
            ["finish", "t", "l"],
        ]:
            res = subprocess.run([sys.executable, EVENTS_PY] + bad_args, capture_output=True)
            assert_true(res.returncode == 2, f"bad CLI {bad_args} expected rc 2, got {res.returncode}")

    print("PASS: all events.py tests passed")
    sys.exit(0)


if __name__ == "__main__":
    main()
