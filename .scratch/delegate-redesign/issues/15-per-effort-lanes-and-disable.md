# 15 — One lane per effort level, and a way to switch lanes off

**What to build:** Today one model appears once, at one effort chosen when the lane was authored — `luna-low@codex` exists and `luna-medium@codex` does not, so the medium setting is unreachable without hand-editing the catalog. Orin wants every effort level a harness offers to be its own lane, and a way to switch off the ones he does not want in play.

`codex debug models` reports six efforts for `gpt-6-astra` and `gpt-5.6-sol` (`low, medium, high, xhigh, max, ultra`) and five for `gpt-5.6-luna`. Enumerating them turns six lanes into roughly thirty. That is fine for ranking, which is a sort, but it makes the wizard's tier screens long and most of those rows will never be used — hence the switch.

**Lane identity stays honest.** The effort is in the key (`luna-low@codex`), so one lane per effort keeps the key matching its contents. This is why effort must not become an editable field on an existing lane: editing it would either make every log line name a lane that lies, or force a key rename mid-wizard. Enumerate instead.

**An `enabled` field** on each lane, defaulting to true. `rank.py` treats a disabled lane as ineligible with reason `disabled`, alongside the existing ceiling and gate reasons, so `--dry-run` still explains itself. `catalog.py` validates it as a boolean. The wizard toggles it, and disabled lanes are dimmed on the tier screens rather than hidden — a lane you switched off should stay visible enough to switch back on.

Generating the lanes is `discover.py`'s job (ticket 13): it already lists every model each harness offers, and knows which have no lane. Extend it to emit a lane stanza per effort for a named model, printed for the human to paste, not written to the catalog. Meter, weight, timeout and price still need a human.

**Blocked by:** 13 (discovery), 12 (the wizard screens this adds a toggle to).

**Status:** open, raised by Orin 2026-09-09: "we should have each level. so luna-low, luna-med, luna-high would all be lanes. add an option to disable or turn off certain lanes."

- [ ] `enabled` is a validated boolean on every lane, defaulting to true when absent so existing catalogs keep working
- [ ] `rank.py` reports a disabled lane as ineligible with reason `disabled`, and never picks one
- [ ] The wizard toggles `enabled` on the cursor row and shows disabled lanes dimmed, not hidden
- [ ] `discover.py --efforts <model>` prints a ready-to-paste lane stanza per effort the harness reports
- [ ] `tests/test_rank.py` covers a disabled lane that would otherwise be the pick
- [ ] Orin enumerates the codex efforts he wants and switches off the rest in one wizard run
