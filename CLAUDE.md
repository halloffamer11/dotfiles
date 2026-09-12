# Dotfiles

Machine configuration and agent tooling managed as one Git repository.

## Start here

- Read `Makefile` before changing installation or stow behavior.
- Read `references/CLAUDE.md` for repository-wide operating context.
- Read `CONTEXT.md` for the domain vocabulary (today: delegate's terms).
- Each active skill under `agents/skills/` owns its detailed context.
- `tools/` holds what a skill uses but does not execute: `tools/delegate-mon/` is a
  Rust crate, the `delegate-mon` monitoring TUI, built out to its plan and owning
  its own CLAUDE.md. It reads the same meters and ledger as the delegate skill and
  is not part of the redesign thread below.

## Active work

The delegate redesign is the only live thread. Spec
`docs/superpowers/specs/2026-09-08-delegate-redesign.md`; tickets in
`.scratch/delegate-redesign/issues/`, each carrying its own decisions and a
"Landed" note; skill context `agents/skills/delegate/CLAUDE.md`. Tickets 01-17, 22
and 23 are landed, and the boxes left unticked there are Orin's own confirmations,
which each ticket's Status line names.

**Ticket 22 landed on `main` as `71e285c`** (2026-09-11), on top of `ea5430b`: each
class has a floor and a ceiling (`routing.json` `classes`), no class reaches tier 4,
`run --tier` raises the floor for one job, and Claude lanes run natively as the
`lane-*` agents in `agents/agents/`.

**Branch `bench-aa-effort-slugs`** (worktree
`~/.herdr/worktrees/dotfiles/delegate-lane-catalog`) is three commits past
`ea5430b`: tickets 18-21, open and `ready-for-agent`, written 2026-09-11 from Orin's
first wizard run, plus its own rewrite of this section. It must merge `main` before
`main` can take it; expect a conflict in this file only.

`~/.claude/skills/delegate` and the four `delegate-*` wrappers symlink into
`~/dotfiles`, the **main** checkout, so the installed skill is whatever `main` holds.

**Open, in priority order:**

1. **Orin's own wizard run.** Nothing in the workflow is known to be wrong now:
   attribution is per lane (ticket 17), every codex effort is a lane, and each page
   makes one decision per line. The tiers on the 19 generated codex lanes and the
   three native Claude lanes are provisional by construction — `meter_weight`,
   `timeout` and `tier` are not measurements. Each such lane says so in its `note`.
2. **Tickets 18-21**, on the branch above, in that order: 18 reads Artificial
   Analysis from the JSON every `/models/<slug>` page embeds, which retires the
   chunked worker path that failed at chunk 6 of 7 on 2026-09-10; 19 gives claude,
   agy and grok the per-effort lanes only codex has today; 20's glossary half is done
   by ticket 22's `CONTEXT.md`, its start-page half is not; 21 (blocked by 18) makes
   the report and the tier pages read per-effort rows.

**Waiting on Orin** (nothing else blocks on these):

- Ticket 23, delegate meter rows under the status line, is on `main` and live
  in Orin's status line since 2026-09-11. The alignment fix and the
  `report.py statusline off|on|toggle` switch are one commit past `main` on
  `worktree/quiet-forest-811d`, no conflict:
  `git -C ~/dotfiles merge --ff-only worktree/quiet-forest-811d`. The stowed
  `statusline.sh` calls the installed skill, which is `main`'s, so the fix shows
  only after that. Ticket 23 holds the row format and the decisions; its last
  open box is the WezTerm chord for the switch.
- Run the wizard against the repo catalog, then link the live folder to it. From
  `~/dotfiles`:
  `python3 agents/skills/delegate/scripts/setup.py --config-dir stow/delegate/.config/delegate --effort-rows .scratch/delegate-redesign/_data/tbench-accepted.json`
  then move the plain `lanes.json` and `routing.json` out of `~/.config/delegate` and
  run `stow -d stow -t ~ -R delegate` (never `--adopt`, which would pull the 10-lane
  live file over the repo's). Ticket 22's last section has the full steps. The run
  closes tickets 06, 07, 07b and 15's last box. The carry page should propose
  `astra-xhigh@codex` off as dominated by high and the three `ultra` lanes off as
  never carried. It should also settle `astra-high@codex`: `6e0f0b1` said its price
  is sourced as `10 / 1 / 12.5 / 50`, but the stowed catalog has `price` null with
  the note "not sourced", and its `meter_weight` 40 is a placeholder. Find the source
  before pasting the figures.
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
- Each class has a floor and a ceiling; the floor is the default, and tier 4 is
  reached only by naming a lane until setup says otherwise. Tiers are what Orin sets:
  tests check the rule on fixtures, never his tiers (ticket 22).
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

Single-context: the glossary is the root `CONTEXT.md`; `docs/adr/` does not exist
yet. See `docs/agents/domain.md`.
