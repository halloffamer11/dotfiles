# Dotfiles

Machine configuration and agent tooling managed as one Git repository.

## Start here

- Read `Makefile` before changing installation or stow behavior.
- Read `references/CLAUDE.md` for repository-wide operating context.
- Each active skill under `agents/skills/` owns its detailed context.
- `tools/` holds what a skill uses but does not execute: `tools/delegate-mon/` is a
  Rust crate, the `delegate-mon` monitoring TUI, built out to its plan and owning
  its own CLAUDE.md. It reads the same meters and ledger as the delegate skill and
  is not part of the redesign thread below.

## Active work

The delegate redesign is the only live thread. Spec
`docs/superpowers/specs/2026-09-08-delegate-redesign.md`; tickets in
`.scratch/delegate-redesign/issues/`, each carrying its own decisions and a
"Landed" note; skill context `agents/skills/delegate/CLAUDE.md`. The boxes left
unticked in a landed ticket are Orin's own confirmations, which its Status line names.

**`main` and `bench-aa-effort-slugs` have diverged from `ea5430b`** (2026-09-11):

- `main` (`7c966a7`, the `~/dotfiles` checkout) landed ticket 22: each class has a
  floor and a ceiling, no class reaches tier 4, and Claude lanes run natively as the
  `lane-*` agents. It also added a root `CONTEXT.md`, which is ticket 20's glossary.
  Its `CLAUDE.md` is newer than this one on what waits on Orin.
- This branch (worktree `~/.herdr/worktrees/dotfiles/delegate-lane-catalog`) landed
  ticket 18 (AA rows from the page's own dataset, the majority carry rule) and
  ticket 23 (the benchmark page as plots with settings; its commit `221283c` still
  says 22, the number it held before `main`'s 22 was seen), and holds the text of
  tickets 19-21. Suite green at 394 `PASS` lines across 12 files (two of the twelve
  report one summary line rather than one line per assertion).

The branch must merge `main` before `main` can take it. Both sides changed
`CLAUDE.md`, `agents/skills/delegate/CLAUDE.md`, `scripts/setup.py`,
`scripts/setup_tui.py`, `tests/test_setup.py` and `tests/test_setup_tui.py`, so
expect conflicts in all six. `~/.claude/skills/delegate` and the four `delegate-*`
wrappers symlink into `~/dotfiles`, so the installed skill has ticket 22 and not 18
or 23.

**Open, in priority order:**

1. **Merge `main` into this branch**, resolve the six conflicts, run the whole
   suite, and then fast-forward `main`. For this file, take `main`'s text for the
   stow step and the Delegation section, and keep this branch's for tickets 18 and 23.
2. **Orin's own wizard run.** Nothing in the workflow is known to be wrong now:
   attribution is per lane (ticket 17), every codex effort is a lane, and each page
   makes one decision per line. The tiers on the 19 generated codex lanes and the
   three native Claude lanes are provisional by construction: `meter_weight`,
   `timeout` and `tier` are not measurements. Each such lane says so in its `note`.
3. **Tickets 19-21**, in that order: 19 gives claude, agy and grok the per-effort
   lanes only codex has today, and each Claude lane it makes also needs a `lane-*`
   agent file (ticket 22); 20's glossary half is done by `main`'s `CONTEXT.md`, and
   its start-page half is not; 21 makes the report and the tier pages read the
   per-effort AA rows instead of the free API's one entry per model.

**Waiting on Orin** (nothing else blocks on these):

- After the merge, run the wizard against the repo catalog, then link the live
  folder to it. From the worktree root:
  `python3 agents/skills/delegate/scripts/setup.py --config-dir stow/delegate/.config/delegate --effort-rows .scratch/delegate-redesign/_data/aa-accepted.json --effort-rows .scratch/delegate-redesign/_data/tbench-accepted.json`
  then move the plain `lanes.json` and `routing.json` out of `~/.config/delegate` and
  run `stow -d stow -t ~ -R delegate` (never `--adopt`, which would pull the 10-lane
  live file over the repo's); ticket 22's last section has the full steps. The run
  closes tickets 06, 07, 07b and 15's last box. The carry page should propose
  `astra-xhigh@codex` off ("high wins on aa" or "on tbench") and the three `ultra`
  lanes off as never carried. The `o` key's page opens on the AA Intelligence Index
  and Terminal-Bench, one plot each; nobody has yet hovered or dragged on it with a
  real mouse. The run should also settle `astra-high@codex`: `6e0f0b1` said its
  price is sourced as `10 / 1 / 12.5 / 50`, but the stowed catalog has `price` null
  with the note "not sourced", and its `meter_weight` 40 is a placeholder. Find the
  source before pasting the figures.
- Type each of the four `/delegate-*` wrappers once with a plain-language
  constraint (ticket 11).
- Two one-liners in his own files, outside this repo (ticket 09):
  `~/.claude/hooks/delegate-gate.py` names `{SKILL_DIR}/delegate.py`, which moved to
  `scripts/delegate.py`, so the hook advises every session to run a path that does
  not exist; and `export DELEGATE_BALANCE=1` is still line 1 of `~/.zshrc.local`.
- Walk the eight spec §9 acceptance items and sign each off. §9.2 is signed; §9.6 is
  down to the hook above; §9.7 is the `.zshrc.local` line.

## Benchmark data

`agents/skills/delegate/scripts/effort.py` is a `pack`/`extract`/`check` pipeline;
`check` is the trust boundary and rejects any number not on the page. Artificial
Analysis skips the worker: `effort.py aa` reads the rows out of the dataset every
`/models/<slug>` page embeds and checks them against that payload (ticket 18). Approved
sources and their cautions: `agents/skills/delegate/assets/sources.json`; the
provenance research behind that choice:
`.scratch/delegate-redesign/research/2026-09-09-effort-data-sources.md`. Accepted
rows and their packets are kept as evidence in `.scratch/delegate-redesign/_data/`.

Coverage is uneven and the three sources are not interchangeable: swerb reaches only
`gpt-5.6-sol` and `gpt-5.6-luna` but publishes slugs; Artificial Analysis and
Terminal-Bench are wider but publish display names (ticket 16). Cost is per-task on
swerb and on Artificial Analysis, but Terminal-Bench's `display_cost` is a whole-run
figure. Even the two per-task numbers measure different task sets, so never compare
costs across sources. The AA key is at `~/.config/delegate/aa-key`, mode 600, outside
the repo and in `.gitignore` — never stow it; this repo is public. Where a note says
AA covers a model, it means the `/models/<slug>` page payload that `effort.py aa`
reads, not the free API that `bench.py` calls (`AA_URL`). AA's cost per task is the
Intelligence Index's, one figure per variant, repeated on each component row.

`flash-high@agy` has no rows in any approved source, so its tier is a judgement from
its `basis` note rather than from numbers. The AA figures for `gpt-5.6-sol`,
`gpt-5.6-terra` and `grok-4.6` were measured at low/medium/medium against lanes that
run high; the report prints that caveat per model.

The report still reads AA through the free API and the key; ticket 21 moves it onto
the per-effort rows `effort.py aa` writes and retires both. Ticket 18's Landed note
carries the measurements; llm-cost-frontier's `update.py` (catalystneuro, BSD-3)
was the reference for where the dataset sits in the page.

## Settled, do not re-raise

- `lanes.json` and `routing.json` both ship in this public repo via `stow/delegate/`.
  Orin ruled the subscription costs and vendor notes non-sensitive, so no split to a
  forge and no constraint on what the pre-screen may write (2026-09-10).
- `trust` is gone from the design entirely. Ranking sorts
  `(tier asc, pace desc, lane name asc)`; the name term is an arbitrary deterministic
  tie-break, so a steal only ever crosses tiers (tickets 01 and 02).
- Each class has a floor and a ceiling; the floor is the default, and tier 4 is
  reached only by naming a lane until setup says otherwise. Tiers are what Orin sets:
  tests check the rule on fixtures, never his tiers (ticket 22, on `main`).
- The Delegation section of `~/.claude/CLAUDE.md` is gone (2026-09-11); the skill is
  the only routing rule, and "Fable never runs as a worker" went with it.
- One decision per line on each page, with the same `[x]`/`[ ]` marker on every
  page: the carry page selects a model at an effort, the tier pages assign a tier,
  and no page asks a question another page already asked (Orin, 2026-09-10). TUI
  work goes to a Claude Opus agent under `/frontend-design:frontend-design`.
- `stow/delegate/.config/delegate/lanes.json` is the authoritative catalog; the live
  `~/.config/delegate/lanes.json` follows it, never the other way (Orin,
  2026-09-10).
- `ultra` lanes are generated disabled: no source scores them, and automatic task
  delegation contradicts the worker preamble (ticket 15).
- The carry page proposes a lane off when another effort of the same model, for no
  more money, beats it on more than half of the benchmarks one source scored both
  on. The AA composite index is shown and never counted (Orin, 2026-09-11, ticket
  18).
- The benchmark page's frontier is a display aid, not a rule: nothing reads it, and
  the carry rule above is the only thing that proposes a lane off (ticket 23).

Preserve unrelated working-tree changes. Validate the smallest affected surface
before committing.

## Agent skills

### Issue tracker

Local markdown: tickets in `.scratch/<effort>/issues/`, specs in
`docs/superpowers/specs/`. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default roles, written as a waiting ticket's `**Status:**` value. See
`docs/agents/triage-labels.md`.

### Domain docs

Single-context: the glossary is the root `CONTEXT.md` on `main` (this branch gets it
at the merge); `docs/adr/` does not exist yet. See `docs/agents/domain.md`.
