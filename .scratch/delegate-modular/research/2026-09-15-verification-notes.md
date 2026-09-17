# Verification notes for the 2026-09-15 research set

Orchestrator's adjudication record for the eight notes in this directory. Every worker
ran in its own Herdr worktree with `--write`; each return was checked for `status`,
`changed_files`, a clean `git status`, and the brief's gate tests before merge. The two
notes written last were also put through a 42-agent verification workflow (one extractor
per note, one checker per cited claim, three adversarial refuters per headline
recommendation, one completeness critic per note). Read the notes with these caveats.

## Spot-checked at merge (no workflow)

| Note | Lane | Check |
|---|---|---|
| `deep-modules-review-grok46` | grok46-high@grok | 8 of 8 sampled `file:line` citations match the source. |
| `deep-modules-review-astra-xhigh` | astra-xhigh@codex | 7 of 7 sampled citations match; the worker reproduced six defects locally. |
| `refactoring-consultation` | grok46-high@grok | 8 of 8 sampled citations match. |
| `aa-boards-from-accepted-rows` | luna-high@codex | 5 coverage-matrix cells re-derived from `aa-accepted.json`; all match. |
| `web-boards` | luna-high@codex | Browser use proven in the run's `events.jsonl`; the DeepSWE table matches an independent fetch row for row. The return's `evidence` array was empty, against the brief. |
| `quota-axi-comparison-grok` | grok46-high@grok | 6 of 6 sampled citations match on both trees. |

## `multi-domain-tiers-scope` (astra-high@codex): merge with notes

Claims checked: 13 supported, 2 partial, 1 unsupported. Refuted 1 of 3 lenses.

- The pick of option (b), per-domain Tier per Lane, is the worker's own judgment. Its two
  citations to the consultation (§Target seams / Catalog on disk; §Dropped as speculative)
  do not discuss the (a)/(b)/(c) alternatives. Treat the pick as proposed, not derived.
- The "audit consumers beyond rank_range" list misses `browser_probes.py:73`
  (`lane_def.get("tier", 999)` in `pick_lowest_tier_lane`). Ticket M9 converts the scalar
  `tier` without touching that file, and `test_browser_probes.py` has no tier test, so
  probe-lane selection would silently fall back to name order. Add the file to M8.
- Two interpretive phrases in "What the benchmarks say" (the Sol/Terra "reversal candidate",
  the "no finance, investing or supply-chain tiers" clause) are the worker's framing, not
  text from the benchmark notes.
- `sources.json:28` is cited where the Terminal-Bench 2.1 versus 4.0 caution sits at line 39.
- The `boards.json` `speaks_to` relabeling the note relies on is only implicit in ticket M5.
- One garbled heading ("HTML page") was repaired at merge; nothing else was changed.

## `quota-axi-comparison-agy` (flash-high@agy): merge with notes, read beside the grok note

Claims checked: 6 supported, 7 partial, 3 unsupported. Refuted 2 of 3 lenses.

- Unsourced numbers: "5–20+ seconds" refresh, "<500ms" after HTTP probes, "200–800ms" Node
  spawn, "90% of the value", "~150 lines". None has a citation or a measurement.
- The adoption argument leans on "no Node.js runtime" for option (a). Node is already a hard
  dependency of the relay path (`delegate.py:444` spawns `node relay.mjs`; `setup.py:35`
  runs `discover.mjs`), and this machine has v26. The Keychain-prompt and agy
  `unknownSemantics` arguments in the same section do hold. The recommendation (a) still
  stands, for those reasons and because both notes reach it, but not for the Node reason.
- Opportunity 1 says `report.py` should "consume rank rows". The accepted consultation puts
  the shared `eligible(observation, gate)` predicate in `usage.py` and has `rank_range`,
  `limits --eligible` and the statusline call it at meter granularity. Follow the
  consultation; ranking rows are lane-keyed and lossy for a per-meter check.
- Opportunity 5 (delegated credential refresh on a 401) cites `delegated-refresh.ts:57-89`,
  which holds type definitions only; nothing in either tree implements the described flow.
  The grok note advises against delegated refresh on the rank path.
- Opportunity 9 cites `usage.py:95-104` for Claude model-limit parsing that lives at
  `usage.py:149-167`.
- Contradiction with the grok note: this note keeps `min(5h, weekly)` for agy; the grok note
  says stop inventing an agy combined bound and sort agy unknown-last until a vendor shows a
  joint bound. Orin's call; the grok position matches quota-axi's own code.
- Required reading not cited: `SKILL.md`, the delegate `CLAUDE.md`, redesign spec §4–5,
  quota-axi's `AGENTS.md`, `CHANGELOG.md` and its test files. `AGENTS.md` says never probe
  Claude through the CLI because it spends the quota being measured; `usage.py:151` does
  exactly that while `usage.py:13` claims zero tokens. The grok note raises this; this one
  does not.
- Not stated in the note: quota-axi's `pace.status: ahead` means burning faster than the
  clock, the opposite of delegate's "pace above 1 means quota will expire unspent".

## Cross-note facts worth carrying

- Both deep-modules reviews and both quota notes converge on one defect: the gate is
  computed in three places (`usage.py:32,57`; `rank.py:139,176`; `report.py:175,206,627`).
  The grok review rates it high, the astra review medium.
- Both quota notes recommend keeping delegate's probes and porting quota-axi's derivations
  (reserve in percentage points with a deadband, usable runway, bound conflict), not running
  the CLI as a backend.
