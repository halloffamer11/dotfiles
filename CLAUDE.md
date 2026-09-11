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
"Landed" note; skill context `agents/skills/delegate/CLAUDE.md`. Tickets 18-21 are
open and `ready-for-agent` (written 2026-09-11 from Orin's first wizard run); 01-17
are landed, and the boxes left unticked there are Orin's own confirmations, which
each ticket's Status line names.

**`main` is at `ea5430b`, the tip of `bench-aa-effort-slugs`** (2026-09-11): `main`
was merged into the branch on 2026-09-10, then `main` fast-forwarded to it. Commits
after `ea5430b` are on the branch only until `main` fast-forwards again. Suite green
at 374 assertions across 12 files (two of the twelve report one summary line rather
than one line per assertion, so other counts of the same suite run higher). The
branch contains `delegate-lane-catalog`, which is history now, not a second thread.
Tickets 01-17 are implemented, and the catalog carries every effort each codex model
offers — 26 lanes, 19 of them generated and provisionally tiered.

`~/.claude/skills/delegate` and the four `delegate-*` wrappers symlink into
`~/dotfiles`, the **main** checkout, so the installed skill is whatever `main` holds —
since `ea5430b`, all of the redesign.

**Open, in priority order:**

1. **Orin's own wizard run.** Nothing in the workflow is known to be wrong now:
   attribution is per lane (ticket 17), every codex effort is a lane, and each page
   makes one decision per line. It has never been driven by a human against the real
   catalog, and the tiers on the 19 new lanes are provisional by construction —
   `meter_weight`, `timeout` and, below the copied effort, `tier` are not
   measurements. Each new lane says so in its `note`.
2. **Tickets 18-21**, in that order: 18 reads Artificial Analysis from the JSON every
   `/models/<slug>` page embeds (31 of 32 catalog variants in one request, verified
   2026-09-11), which retires the chunked worker path that failed at chunk 6 of 7
   on 2026-09-10 — chunk dispatch is no longer an open problem; 19 gives claude, agy
   and grok the per-effort lanes only codex has today (nine missing); 20 moves the
   glossary to a root `CONTEXT.md`; 21 (blocked by 18) makes the report and the
   tier pages read those per-effort rows instead of the free API's one entry per
   model.

**Waiting on Orin** (nothing else blocks on these):

- Run the wizard once to close tickets 06, 07, 07b and 15's last box, and to
  confirm or correct the provisional tiers on the 19 generated lanes. From the
  worktree root:
  `python3 agents/skills/delegate/scripts/setup.py --config-dir stow/delegate/.config/delegate --effort-rows .scratch/delegate-redesign/_data/tbench-accepted.json`
  The carry page should propose `astra-xhigh@codex` off as dominated by high and the
  three `ultra` lanes off as never carried. It should also settle
  `astra-high@codex`: `main`'s notes (`6e0f0b1`) said its price is sourced as
  `10 / 1 / 12.5 / 50`, but the stowed catalog has `price` null with the note "not
  sourced", and its `meter_weight` 40 is a placeholder. Find the source before
  pasting the figures.
- Type each of the four `/delegate-*` wrappers once with a plain-language
  constraint (ticket 11).
- Two one-liners in his own files, outside this repo (ticket 09):
  `~/.claude/hooks/delegate-gate.py` names `{SKILL_DIR}/delegate.py`, which moved to
  `scripts/delegate.py`, so the hook advises every session to run a path that does
  not exist; and `export DELEGATE_BALANCE=1` is still line 1 of `~/.zshrc.local`.
- Reconcile the live catalog with the stowed one, now that the stowed file is the
  authority (see Settled). The live `~/.config/delegate/lanes.json` is a regular
  file, not a stow symlink, and as of 2026-09-10 it holds 10 lanes against the
  stowed 26; it also lacks `published_as: ["Fable 5.1"]` on the fable lane and keeps
  tier 4 on `astra-low@codex` and `astra-medium@codex`, which the stowed file drops
  to 1. Replacing it is a mutating command in Orin's own home, so it is his to run.
- Decide whether the `~/.claude/CLAUDE.md` Delegation section collapses to one line
  as ticket 09 asks, which would drop the `why-claude` and "a result is a claim"
  rules.
- Walk the eight spec §9 acceptance items and sign each off. §9.2 is signed; §9.6 is
  down to the hook above; §9.7 is the `.zshrc.local` line.

## Benchmark data

`agents/skills/delegate/scripts/effort.py` is a `pack`/`extract`/`check` pipeline;
`check` is the trust boundary and rejects any number not on the page. Approved
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
AA covers a model, it means the `/models/releases/` pages that `effort.py` scrapes,
not the free API that `bench.py` calls (`AA_URL`).

`flash-high@agy` has no rows in any approved source, so its tier is a judgement from
its `basis` note rather than from numbers. The AA figures for `gpt-5.6-sol`,
`gpt-5.6-terra` and `grok-4.6` were measured at low/medium/medium against lanes that
run high; the report prints that caveat per model.

## Settled, do not re-raise

- `lanes.json` and `routing.json` both ship in this public repo via `stow/delegate/`.
  Orin ruled the subscription costs and vendor notes non-sensitive, so no split to a
  forge and no constraint on what the pre-screen may write (2026-09-10).
- `trust` is gone from the design entirely. Ranking sorts
  `(tier asc, pace desc, lane name asc)`; the name term is an arbitrary deterministic
  tie-break, so a steal only ever crosses tiers (tickets 01 and 02).
- One decision per line on each page, with the same `[x]`/`[ ]` marker on every
  page: the carry page selects a model at an effort, the tier pages assign a tier,
  and no page asks a question another page already asked (Orin, 2026-09-10). TUI
  work goes to a Claude Opus agent under `/frontend-design:frontend-design`.
- `stow/delegate/.config/delegate/lanes.json` is the authoritative catalog; the live
  `~/.config/delegate/lanes.json` follows it, never the other way (Orin,
  2026-09-10).
- `ultra` lanes are generated disabled: no source scores them, and automatic task
  delegation contradicts the worker preamble (ticket 15).

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

Single-context: one `CONTEXT.md` and `docs/adr/` at the root; neither exists yet.
See `docs/agents/domain.md`.
