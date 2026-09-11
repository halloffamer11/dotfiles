# 22 — class range (floor and ceiling), and native Claude lanes

**What is wrong:** on 2026-09-11 `delegate.py run scout` in `sienna_purch` picked
`fable-xhigh@claude`, and `run review` picked it in every project. Three causes:

1. Eligibility was `tier >= need`. A class had a floor and no ceiling, so a tier-4
   lane was eligible for every class.
2. The `claude-general` meter (Opus, Sonnet, Haiku) had no lanes. On the Claude side,
   Fable was the only lane.
3. Codex was below the gate. Fable's pace (0.84) beat grok's (0.59) by the 0.2
   margin, so the steal rule moved the job up to Fable.

"Fable never runs as a worker" lived only in `~/.claude/CLAUDE.md`. No routing code
reads that file.

## Related tickets

Tickets 18–21 were opened in parallel on `bench-aa-effort-slugs` on the same day,
so this ticket is numbered 22.

- **Ticket 20:** this ticket's root `CONTEXT.md` is ticket 20's glossary. It carries
  every term that ticket lists, and ticket 20's first box closes when this merges.
  Ticket 20 calls tier "a ceiling"; decision 1 below replaces that sense. Ticket
  20's start-page work is untouched.
- **Ticket 19:** that ticket gives the `claude` harness an effort list. Each Claude
  lane it generates also needs a `lane-<model-effort>.md` agent file (decision 7).
  Haiku 4.5 does not accept effort, so a Haiku lane at any effort is a label only.

## Decisions (Orin, 2026-09-11, grill session)

1. **Each class has a floor and a ceiling.** In `routing.json`,
   `"classes": {"<class>": {"floor": f, "ceiling": c}}` replaces `classTier`, with
   1 ≤ floor ≤ ceiling ≤ 4. A project override merges per class and per key, so
   `{"classes": {"scout": {"floor": 3}}}` keeps the global scout ceiling.
2. **Starting ranges:** scout 2–3, mechanical 1–2, impl 2–3, review 3–3,
   hard-impl 3–3. No class reaches tier 4, so ranking never picks a tier-4 lane.
   Tier 4 is reached only by named dispatch. Setup can change all of this.
3. **The floor is the default.** `run --tier <n>` raises the floor for one job and
   must stay inside the range. The orchestrator uses it when the task needs judgment.
   Example: a scout that finds a file gets no flag; a scout that judges which of the
   given web pages are relevant gets `--tier 3`. Pace can still move a job up inside
   the range.
4. **`--effort` goes from `run`** and stays on `dispatch`. Each effort is its own
   lane with its own tier, so a ranked job must not change a lane's capability.
5. **Veto text,** with one reason per lane, checked in this order:
   - `vetoed:disabled, <lane>`
   - `vetoed:floor, <lane> (tier t) < <class> floor (tier f)`
   - `vetoed:ceiling, <lane> (tier t) > <class> ceiling (tier c)`
   - `vetoed:gate, <lane>: <meter> meter N% left < gate G%`
   - `vetoed:cli, <lane>: <harness> not on PATH`

   The layout of the rank output (grouped by meter, then tier) is for Orin to
   redraft. It is not part of this ticket.
6. **Native Claude lanes.** The orchestrator harness is fixed as `claude` for now
   (`ORCHESTRATOR = "claude"` in `delegate.py`). A lane on the orchestrator's harness
   is native. For a native lane, `run` and `dispatch` write `<run>/prompt.md` with the
   existing `build_prompt`, print
   `delegate: native lane=<lane> agent=lane-<model-effort> prompt=<abs path>`, and
   exit 0. No relay starts. The session spawns that agent with the prompt. The ledger
   hook already records Agent spawns, and `report.py log --lane --secs --status`
   records the result without a relay run. The relay path for `claude` stays, for a
   future Codex orchestrator.
7. **One agent definition per Claude lane,** in
   `agents/agents/lane-<model-effort>.md`. Its frontmatter sets `model` to the full
   model ID and sets `effort`. The Claude Code sub-agent docs list both fields
   (checked 2026-09-11). Haiku 4.5 is not on the platform effort page's list of
   supported models (checked 2026-09-11), so its file leaves out `effort`.
8. **Claude lanes, hand-named.** `claude --help` has no command that lists models
   (checked 2026-09-11), so `discover.py` cannot produce them.
   - `haiku-high@claude`: `claude-haiku-4-5-20251001`, tier 1
   - `sonnet-high@claude`: `claude-sonnet-5`, tier 2
   - `opus-high@claude`: `claude-opus-5`, tier 3

   All three are on `claude-general`. `fable-xhigh@claude` stays at tier 4. `price`
   is null ("not sourced"). `meter_weight` and `timeout` are provisional, and each
   lane's `note` says so.
9. **The glossary is the root `CONTEXT.md`.** `setup-matt-pocock-skills` defaults to
   a single context, and this repo has no monorepo signals. The Terms section in
   `SKILL.md` becomes a pointer to it.
10. **The Delegation section of `~/.claude/CLAUDE.md` goes entirely.** That includes
    "Fable never runs as a worker", `why-claude`, and the Workflow sizing line. The
    skill is the abstraction. This settles ticket 09's open decision. The file is
    Orin's, so he makes the edit.
11. **`/delegate-claude` spawns natively.**

## Slices

**A — range rule.** `rank.py`, `catalog.py`, both `routing.json` files (the sample
and the stowed one), `delegate.py` (`run --tier`, no `run --effort`), `setup.py` and
`setup_tui.py` (read the new shape; no new page), the rule text in `SKILL.md`, and
tests.

**B — native Claude lanes.** The native branch in `delegate.py`, the agent
definitions, the three lanes in the stowed and sample `lanes.json`, the
`/delegate-claude` wrapper, `test_dispatch.py`, and the skill's `CLAUDE.md`.

## Acceptance

- [x] `routing.json` has `classes` with a floor and a ceiling, validated. A file
      that still has `classTier` fails with a message that shows the new shape.
- [x] `rank.py` never picks a lane outside the range, and prints the veto text above
      exactly.
- [x] A `test_rank.py` case replays 2026-09-11: codex gated, scout 3–3, Fable tier 4
      pace 0.85, grok tier 3 pace 0.59. The pick is grok, and Fable is
      `vetoed:ceiling` (case 16).
- [x] `run --tier` narrows a job inside its range and refuses a value outside it
      (exit 2). `run` has no `--effort`.
- [x] A native pick prints the `delegate: native` line and starts no relay
      (`test_dispatch.py` cases 29–31).
- [x] Four `lane-*.md` agent definitions exist, and the three new lanes pass
      `catalog.py check`. They are in the stowed catalog only; the sample stays the
      spec's starting catalog because five suites use it as a fixture.
- [x] No test added or changed here reads `~/.config/delegate`, and none checks
      Orin's tiers. `test_bench_page.py:438`, not changed by this ticket, does read it.

**Verified 2026-09-11** in worktree `delegate-class-range`: all 12 test files pass.
Both slices were implemented by `flash-high@agy` and checked by the lead. The lead
fixed a grep-gaming string concatenation in `catalog.py`, stale "need" and "a
ceiling" wording in four wrappers and the setup TUI, and the sample-catalog
breakage in five suites. **Landed on `main` as `71e285c`.**

## Out of scope (recorded here, not ticketed)

- **`catalog.write_json` replaces a symlink with a plain file.** It resolves `~` and
  relative paths (`abspath`), not links, then calls `os.replace`. Once
  `~/.config/delegate` is stowed, run the wizard only with
  `--config-dir stow/delegate/.config/delegate`. The fix is to resolve the path with
  `realpath` before writing.
- **`catalog.py check --partial` cannot validate a project override.** It needs a
  `version` to tell a lanes file from a routing file, and overrides carry none. This
  predates this ticket; the real loading path accepts overrides.

- **Fan-out-aware ranking.** A fan-out ranks each job against the same meter
  reading, so N concurrent jobs can empty a 5-hour window that the gate saw as
  healthy. See ticket 15's chunk-dispatch section. Burn rate is not a ranking input.
- **Redrafting the rank output layout:** Orin.
- **A setup page for the class ranges,** after the carry and tier pages. TUI work
  goes to a Claude Opus agent under `/frontend-design:frontend-design`.
- **Codex as the orchestrator:** native Codex lanes, and Claude lanes over the relay.
- **Claude model discovery,** if the `claude` CLI gains a command that lists models.

## Orin's steps after merge

- [x] Migrate `~/.config/delegate/routing.json` and
      `~/Documents/daedalus/sienna_purch/.delegate/routing.json` to `classes`.
- [x] Run `make skills` so the `lane-*.md` agent files link into `~/.claude/agents`.
- [x] Delete the Delegation section of `~/.claude/CLAUDE.md`.
- [ ] Run the wizard against the repo catalog, then link the live folder to it. Until
      then the live `lanes.json` has 10 lanes and no native Claude lane can be
      picked; the ceiling blocks Fable either way. From `~/dotfiles`:

          python3 agents/skills/delegate/scripts/setup.py --config-dir stow/delegate/.config/delegate --effort-rows .scratch/delegate-redesign/_data/tbench-accepted.json
          python3 agents/skills/delegate/scripts/catalog.py check stow/delegate/.config/delegate/lanes.json
          mkdir ~/.config/delegate/_pre-stow-2026-09-11
          mv ~/.config/delegate/lanes.json ~/.config/delegate/routing.json ~/.config/delegate/_pre-stow-2026-09-11/
          stow -n -v -d stow -t ~ -R delegate
          stow -v -d stow -t ~ -R delegate

      Do not pass `--adopt`: it would move the 10-lane live file over the repo's.
      Do not copy `aa-key` into `stow/`: stow would link it, and the repo is public.

**Status:** landed 2026-09-11 (`71e285c`); one step left for Orin: the wizard run
and the stow link.
