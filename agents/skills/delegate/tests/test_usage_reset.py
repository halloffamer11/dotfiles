#!/usr/bin/env python3
"""test_usage_reset.py — test claude_reset format parsing and meter cache write append."""
import json, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

# Run from a fresh directory with no Git root above it, so that
# `catalog.find_git_root()` never finds the invoking checkout's own
# `.delegate/routing.json`. Every path this file needs comes from HERE.
_ISOLATED_CWD = tempfile.TemporaryDirectory(prefix="delegate-test-")
os.chdir(_ISOLATED_CWD.name)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "scripts")))
from usage import claude_reset, write_cache, load_cache, lane


def fail(msg):
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def assert_true(cond, msg):
    if not cond:
        fail(msg)


def main():
    # 1. claude_reset tests
    t_3pm = claude_reset("Sep 8 at 3pm (America/New_York)")
    assert_true(t_3pm is not None, "claude_reset('Sep 8 at 3pm (America/New_York)') returned None")

    t_259pm = claude_reset("Sep 8 at 2:59pm (America/New_York)")
    assert_true(t_259pm is not None, "claude_reset('Sep 8 at 2:59pm (America/New_York)') returned None")

    diff = t_3pm - t_259pm
    assert_true(diff == 60.0, f"expected 60s diff between 2:59pm and 3pm, got {diff}")

    t_12am = claude_reset("Sep 8 at 12am (America/New_York)")
    assert_true(t_12am is not None, "claude_reset('Sep 8 at 12am (America/New_York)') returned None")

    assert_true(claude_reset("") is None, "claude_reset('') should be None")
    assert_true(claude_reset("invalid text") is None, "claude_reset('invalid text') should be None")

    # 2. Cache write with DELEGATE_LEDGER + DELEGATE_CACHE in a temp dir appends one meter line
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, "ledger.jsonl")
        cache_path = os.path.join(tmpdir, "cache.json")
        os.environ["DELEGATE_LEDGER"] = ledger_path
        os.environ["DELEGATE_CACHE"] = cache_path

        import time
        now = time.time()
        doc = {
            "probed_at": now,
            "probed_at_iso": "2026-09-02T23:00:00+00:00",
            "gate": 0.1,
            "rollover_min": 30,
            "lanes": [
                {
                    "lane": "test-lane",
                    "harness": "agy",
                    "meter": "gemini",
                    "remaining_5h": 0.8,
                    "remaining_weekly": 0.9,
                    "r": 0.8,
                    "binding": "5h",
                    "reset_5h": 1788406804,
                    "reset_weekly": 1788616225,
                    "pace": 2.5,
                    "status": "ok",
                    "note": None,
                }
            ],
        }

        write_cache(doc, cache_path=cache_path)

        # Check cache written
        assert_true(os.path.exists(cache_path), f"cache file not found at {cache_path}")
        with open(cache_path) as f:
            loaded_doc = json.load(f)
        assert_true(loaded_doc == doc, "cache file content mismatch")

        # Check ledger appended exactly one line
        assert_true(os.path.exists(ledger_path), f"ledger file not found at {ledger_path}")
        with open(ledger_path) as f:
            lines = [l.strip() for l in f if l.strip()]
        assert_true(len(lines) == 1, f"expected 1 line in ledger, got {len(lines)}")

        event = json.loads(lines[0])
        assert_true(event.get("v") == 1, "meter event v != 1")
        assert_true(event.get("kind") == "meter", "meter event kind != 'meter'")
        assert_true(event.get("source") == "probe", "meter event source != 'probe'")
        assert_true(event.get("cache_age_s") == 0, "meter event cache_age_s != 0")
        assert_true(event.get("probed_at") == now, "meter event probed_at mismatch")
        assert_true(event.get("lanes") == doc["lanes"], "meter event lanes mismatch")
        assert_true("ts" in event, "meter event missing ts")

        # Calling load_cache on fresh cache must NOT append to ledger
        loaded = load_cache(max_age_min=10, cache_path=cache_path)
        assert_true(loaded is not None, "load_cache returned None for fresh cache")
        with open(ledger_path) as f:
            lines2 = [l.strip() for l in f if l.strip()]
        assert_true(len(lines2) == 1, f"load_cache unexpectedly appended to ledger; count is {len(lines2)}")

        # 3. Test remaining_weekly_model on model meter lane and general lane
        l_fable = lane("claude", "fable", 0.58, 0.46, None, None, remaining_weekly_model=0.59)
        assert_true(l_fable.get("remaining_weekly_model") == 0.59, "l_fable remaining_weekly_model != 0.59")
        assert_true(l_fable.get("remaining_weekly") == 0.46, "l_fable remaining_weekly != 0.46")

        l_gen = lane("claude", "general", 0.58, 0.46, None, None)
        assert_true(l_gen.get("remaining_weekly_model") is None, "l_gen remaining_weekly_model is not None")

        doc_with_model = {
            "probed_at": now,
            "probed_at_iso": "2026-09-02T23:00:00+00:00",
            "gate": 0.1,
            "rollover_min": 30,
            "lanes": [l_fable, l_gen],
        }
        write_cache(doc_with_model, cache_path=cache_path)
        with open(ledger_path) as f:
            lines3 = [l.strip() for l in f if l.strip()]
        assert_true(len(lines3) == 2, f"expected 2 lines in ledger, got {len(lines3)}")
        event2 = json.loads(lines3[1])
        assert_true(event2["lanes"][0].get("remaining_weekly_model") == 0.59, "ledger event fable remaining_weekly_model mismatch")
        assert_true(event2["lanes"][1].get("remaining_weekly_model") is None, "ledger event general remaining_weekly_model mismatch")

    print("PASS: all test_usage_reset tests passed")
    sys.exit(0)


if __name__ == "__main__":
    main()
