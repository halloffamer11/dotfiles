#!/usr/bin/env python3
"""test_usage_reset.py — test claude_reset format parsing and meter cache write append."""
import json, os, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))

# Run from a fresh directory with no Git root above it, so that
# `catalog.find_git_root()` never finds the invoking checkout's own
# `.delegate/routing.json`. Every path this file needs comes from HERE.
_ISOLATED_CWD = tempfile.TemporaryDirectory(prefix="delegate-test-")
os.chdir(_ISOLATED_CWD.name)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "scripts")))
import usage
from usage import claude_reset, write_cache, load_cache, load_cached, lane, get_cache_path, eligible, observations


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

        # 4. Cached-only reads emit no meter event and launch no vendor probe.
        calls = []
        orig_codex, orig_agy, orig_claude, orig_grok = (
            usage.probe_codex, usage.probe_agy, usage.probe_claude, usage.probe_grok,
        )
        def boom(name):
            def _boom(*a, **k):
                calls.append(name)
                raise AssertionError(f"vendor probe {name}")
            return _boom
        usage.probe_codex = boom("codex")
        usage.probe_agy = boom("agy")
        usage.probe_claude = boom("claude")
        usage.probe_grok = boom("grok")
        try:
            cached = load_cached(cache_path=cache_path)
            assert_true(cached.get("lanes")[0].get("remaining_weekly_model") == 0.59,
                        "load_cached dropped remaining_weekly_model")
            with open(ledger_path) as f:
                lines4 = [l.strip() for l in f if l.strip()]
            assert_true(len(lines4) == 2, f"load_cached appended a meter event; count is {len(lines4)}")
            assert_true(calls == [], f"load_cached launched probes: {calls}")
        finally:
            usage.probe_codex, usage.probe_agy, usage.probe_claude, usage.probe_grok = (
                orig_codex, orig_agy, orig_claude, orig_grok,
            )

    # 5. Cache path: DELEGATE_CACHE wins, else CONSULT_CACHE, else default.
    with tempfile.TemporaryDirectory() as tmpdir:
        delegate_path = os.path.join(tmpdir, "delegate.json")
        consult_path = os.path.join(tmpdir, "consult.json")
        os.environ["DELEGATE_CACHE"] = delegate_path
        os.environ["CONSULT_CACHE"] = consult_path
        assert_true(get_cache_path() == delegate_path, f"DELEGATE_CACHE should win, got {get_cache_path()}")
        del os.environ["DELEGATE_CACHE"]
        assert_true(get_cache_path() == consult_path, f"CONSULT_CACHE should apply, got {get_cache_path()}")
        del os.environ["CONSULT_CACHE"]
        assert_true(get_cache_path() == os.path.expanduser("~/.cache/delegate/usage.json"),
                    f"default cache path mismatch: {get_cache_path()}")

    # 6. eligible: unknown never vetoes; Remaining equal to Gate is eligible.
    assert_true(eligible(None, 0.1) is True, "missing observation should be eligible")
    assert_true(eligible({"r": None}, 0.1) is True, "unknown r should be eligible")
    assert_true(eligible({"r": 0.10}, 0.10) is True, "r equal to gate should be eligible")
    assert_true(eligible({"r": 0.11}, 0.10) is True, "r above gate should be eligible")
    assert_true(eligible({"r": 0.09}, 0.10) is False, "r below gate should be ineligible")
    assert_true(eligible({"r": 0.50, "status": "unavailable"}, 0.10) is True,
                "cached status must not veto when r is at or above gate")

    # 7. An agy lane runs through the same arithmetic as every other Meter:
    #    Remaining is the lower Window, Pace comes from the weekly Window.
    l_agy = lane("agy", "gemini", 0.80, 0.90, 1788406804, 1788616225)
    l_codex = lane("codex", None, 0.80, 0.90, 1788406804, 1788616225)
    assert_true(l_agy["remaining_5h"] == 0.80 and l_agy["remaining_weekly"] == 0.90,
                "agy windows should remain visible")
    assert_true(l_agy["r"] == 0.80 and l_agy["binding"] == "5h" and l_agy["status"] == "ok",
                f"agy Remaining should be the lower window, got r={l_agy['r']}")
    assert_true(l_agy["pace"] is not None and l_agy["pace"] == l_codex["pace"],
                f"agy Pace should match the other Meters, got {l_agy['pace']}")
    derived = ("r", "binding", "reset_binding", "cycle_left", "pace", "score", "status")
    assert_true(all(l_agy[k] == l_codex[k] for k in derived),
                f"agy and codex should derive the same figures: {l_agy} vs {l_codex}")
    assert_true("assumption" in usage.AGY_COMBINED_NOTE and "not a vendor bound" in usage.AGY_COMBINED_NOTE,
                f"the agy note must call the combined figure an assumption: {usage.AGY_COMBINED_NOTE}")

    # One Window missing: the documented fallback of the other Meters applies.
    for meter_name, five_h, weekly in (("gemini", None, 0.90), ("gemini", 0.80, None)):
        one_agy = lane("agy", meter_name, five_h, weekly, 1788406804, 1788616225)
        one_codex = lane("codex", None, five_h, weekly, 1788406804, 1788616225)
        assert_true(all(one_agy[k] == one_codex[k] for k in derived),
                    f"a one-window agy lane must fall back as codex does: {one_agy}")
    assert_true(lane("agy", "gemini", 0.80, None, 1788406804, None)["pace"] is None,
                "no weekly Window means no Pace, on agy as anywhere else")

    # A fresh agy probe carries the windows, the figures and the assumption note.
    from unittest.mock import patch
    class _R:
        returncode = 0
        stdout = json.dumps({"command": {"data": {"groups": [
            {"name": "Gemini", "buckets": [
                {"window": "5h", "remaining_fraction": 0.80, "reset_time": "2026-09-19T03:00:00Z"},
                {"window": "weekly", "remaining_fraction": 0.90, "reset_time": "2026-09-24T03:00:00Z"}]}]}}})
    with patch.object(usage, "which", return_value=True), \
         patch.object(usage, "run", return_value=_R()):
        probed_agy = usage.probe_agy()
    assert_true(len(probed_agy) == 1 and probed_agy[0]["r"] == 0.80
                and probed_agy[0]["pace"] is not None,
                f"a fresh agy probe must give Remaining and Pace: {probed_agy}")
    assert_true(usage.AGY_COMBINED_NOTE in (probed_agy[0].get("note") or ""),
                f"a fresh agy probe must carry the assumption note: {probed_agy[0].get('note')}")

    # 8. A cached observation written under the old rule — Windows present,
    #    combined Remaining and Pace null — gives the figures with no probe.
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = os.path.join(tmpdir, "old-agy.json")
        old = {
            "probed_at": time.time(),
            "lanes": [{
                "lane": "agy-gemini",
                "harness": "agy",
                "meter": "gemini",
                "remaining_5h": 0.80,
                "remaining_weekly": 0.90,
                "r": None,
                "binding": None,
                "reset_5h": 1788406804,
                "reset_weekly": time.time() + 3.5 * 86400,
                "reset_binding": None,
                "cycle_left": None,
                "pace": None,
                "score": None,
                "status": "unknown",
                "note": "agy combined remaining and pace unknown until a vendor joint bound exists",
            }, {
                "lane": "codex",
                "harness": "codex",
                "remaining_5h": 0.50,
                "remaining_weekly": 0.70,
                "r": 0.50,
                "pace": 1.1,
                "status": "ok",
            }],
        }
        with open(cache_path, "w") as f:
            json.dump(old, f)
        loaded = load_cached(cache_path=cache_path)
        agy_row = next(L for L in loaded["lanes"] if L["lane"] == "agy-gemini")
        codex_row = next(L for L in loaded["lanes"] if L["lane"] == "codex")
        assert_true(agy_row["r"] == 0.80 and agy_row["binding"] == "5h",
                    f"a cached agy Remaining should be the lower window, got {agy_row}")
        assert_true(agy_row["pace"] is not None and agy_row["status"] == "ok",
                    f"a cached agy Pace should be derived, got {agy_row}")
        assert_true(agy_row["remaining_5h"] == 0.80 and agy_row["remaining_weekly"] == 0.90,
                    "cached agy windows should remain")
        assert_true("unknown until a vendor joint bound" not in (agy_row.get("note") or ""),
                    f"the superseded note must not sit beside a figure: {agy_row.get('note')}")
        assert_true(codex_row["r"] == 0.50 and codex_row["pace"] == 1.1,
                    "a probed figure is never recomputed")
        obs = observations(old)
        assert_true(obs["agy-gemini"]["r"] == 0.80 and obs["agy-gemini"]["pace"] is not None,
                    "observations() must give the cached agy Meter its figures")
        assert_true(obs["codex"]["r"] == 0.50, "observations() must leave codex r")
        with open(cache_path) as f:
            on_disk = json.load(f)
        assert_true(on_disk["lanes"][0]["r"] is None,
                    "cache file must not be rewritten on load_cached")

    # Repeated acquisitions in one Python process use the current clock.
    from unittest.mock import patch
    import subprocess
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "clock-cache.json")
        with patch.object(usage, "probe_codex", return_value=[]), \
             patch.object(usage, "probe_agy", return_value=[]), \
             patch.object(usage, "probe_claude", return_value=[]), \
             patch.object(usage, "probe_grok", return_value=[]), \
             patch.object(usage, "append"), \
             patch.object(usage.time, "time", return_value=10000):
            first = usage.probe(refresh=True, cache_path=path)
            assert_true(first["probed_at"] == 10000, "probe must stamp current acquisition time")
            with patch.object(usage.time, "time", return_value=14000):
                assert_true(usage.load_cache(10, path) is None, "cache age must advance in one process")
                second = usage.probe(refresh=True, cache_path=path)
            assert_true(second["probed_at"] == 14000, "second probe must not reuse import time")

        malformed = {"probed_at": time.time(), "lanes": [
            {"lane": "agy-gemini", "r": "bad", "pace": 2.0, "remaining_weekly": 0.9}]}
        with open(path, "w") as f:
            json.dump(malformed, f)
        assert_true(usage.observations(malformed) is None, "malformed agy input must fail validation")
        assert_true(usage.load_cached(path) == {}, "cache normalization must not hide invalid agy data")
        assert_true(usage.load_cache(10, path) is None, "refresh path must reject malformed cached data")

        with patch.dict(os.environ, {"DELEGATE_CACHE": path}), \
             patch.object(usage.subprocess, "run", side_effect=subprocess.TimeoutExpired("probe", 90)) as runner:
            assert_true(usage.acquire(timeout=90) == {}, "bounded acquisition returns unknown on timeout")
            assert_true(runner.call_args.kwargs["timeout"] == 90, "acquisition must keep the wall timeout")
        low = usage.lane("codex", None, 0.05, 0.06)
        assert_true(low["status"] == "ok", "observation status must not encode a private Gate")
        assert_true(usage.eligible(low, 0.0) and not usage.eligible(low, 0.1),
                    "the effective Gate alone determines low-Meter eligibility")

    for stamp in (None, float("nan"), "yesterday", True):
        doc = {"lanes": [{"lane": "codex", "r": 0.5}], "probed_at": stamp}
        assert_true(usage.observations(doc) is None, "envelope needs a finite timestamp")
    assert_true(usage.observations({"codex": {"r": 0.5}}) is not None,
                "legacy bare maps remain timestamp-free")
    for field in ("remaining_5h", "remaining_weekly_model", "reset_5h", "reset_weekly", "reset_binding"):
        for bad in ("bad", float("nan"), True, -1):
            doc = {"probed_at": time.time(), "lanes": [
                {"lane": "codex", "r": 0.5, field: bad}]}
            assert_true(usage.observations(doc) is None,
                        f"malformed {field} must invalidate the entire document")
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "bad-display.json")
        with open(path, "w") as f:
            json.dump({"probed_at": time.time(), "lanes": [
                {"lane": "codex", "r": 0.5, "reset_5h": "bad"}]}, f)
        assert_true(usage.load_cached(path) == {}, "cached viewers reject invalid display data")

    print("PASS: all test_usage_reset tests passed")
    sys.exit(0)


if __name__ == "__main__":
    main()
