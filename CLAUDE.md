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

**Project dashboard prototype**: branch `worktree/delegate-monitor-herdr`; spec
`docs/superpowers/specs/2026-09-13-delegate-dashboard-plugin.md`, tickets
`.scratch/delegate-dashboard-plugin/issues/`. Before changing its TUI, launcher,
or safe-save behavior, read `tools/delegate-dashboard/CLAUDE.md`. Orin's verdict
(2026-09-15, tickets 01 and 09): a Herdr plugin is the right host and project Order,
Gate and Margin give useful steering. Backend tickets 02-04 plus the shared Meter
validity commits landed on `main` at `2a8e323` (2026-09-15, branch
`dashboard-backend`, fast-forwarded by Orin), and the installed skill accepts this
project's `.delegate/routing.json` with its Project order. The prototype UI stays
on this branch per the spec. A production control surface is not ticketed yet.

The delegate redesign is the main live thread. Spec
`docs/superpowers/specs/2026-09-08-delegate-redesign.md`; tickets in
`.scratch/delegate-redesign/issues/`, each carrying its own decisions and a
"Landed" note; skill context `agents/skills/delegate/CLAUDE.md`. Tickets 01-19 and
22-28 are landed, and the boxes left unticked there are Orin's own confirmations,
which each ticket's Status line names.

**Delegate browser use** is the second thread, on branch `worktree/silver-river-1847`
(not merged): tickets 01-07 in `.scratch/delegate-browser/issues/`. Goal: the dispatch
path lets workers use a browser a harness already has — a disposable browser
everywhere, and the Helium "GenAI" agent profile through the Playwright extension — on
the Mac and omarchy. No new config file, flag or ranking change; machine setup happens
in conversation with Orin. Ticket 01 is done: the runner `scripts/browser_probes.py`,
the prompt changes, and the Mac baseline table, with a 2026-09-12 retest beneath it.

State after 2026-09-12, each row proven against Playwright's own snapshots rather
than a worker's marker: **agy** passes; **codex** passes through a home of
delegate's own (`~/.local/share/delegate/codex-home`, built by
`make delegate-codex-home`), which holds one MCP server, so a worker never sees
Gmail, `codex-cli`, `node_repl`, hooks or `~/.codex/AGENTS.md` — ticket 03 is done on the
Mac, proven through the normal dispatch path in a read-only run and a write run,
and only the omarchy setup remains; **grok** has a browser
on write runs only, because its built-in `read-only` sandbox kills every stdio MCP
server on macOS, and the proven fix is a custom sandbox profile, which needs a
relay change (ticket 04); **claude** lanes are native since ticket 22, so ticket 02
is rescoped to the session's own config and a restart. Facts and setup rules:
`.scratch/delegate-browser/research/2026-09-10-browser-routes.md`.

**Ticket 22 landed on `main` as `71e285c`** (2026-09-11), on top of `ea5430b`: each
class has a floor and a ceiling (`routing.json` `classes`), no class reaches tier 4,
`run --tier` raises the floor for one job, and Claude lanes run natively as the
`lane-*` agents in `agents/agents/`.

**Landed on `main` at `d53e5af`** (2026-09-13): tickets 18, 19 and 24-28 on top of
22 and 23. The chain was `bench-aa-effort-slugs` (18, 24), then `t19-efforts-and-rows`,
`t25-wizard-pages`, `t26-page-tiers`, `t27-page-first`, `t28-tier-order`; the last four
worktrees and branches are removed, and `main` merged the browser thread on the way.
Orin's wizard run (2026-09-13, ticket 28's run note) wrote the repo catalog: 18 lanes
on, each with a tier and an `order`, 25 off; `scout` is floor 1 / ceiling 2. The live
`~/.config/delegate/{lanes,routing}.json` are stow links into the repo since the same
day (the plain files it replaced sit in `~/.config/delegate/_pre-stow-2026-09-13/`,
unused), `make skills` linked the 16 `lane-*` agents, and `rank.py impl` through the
installed skill reads the new tiers and orders. `make delegate-wizard` runs the wizard
on the repo catalog with the accepted rows from any directory
(`make -C <checkout> delegate-wizard`; `WIZARD_ARGS` adds flags such as
`--tiers-from <file>`).

**Open, in priority order:**

1. **Housekeeping**: the worktree `~/.herdr/worktrees/dotfiles/delegate-lane-catalog`
   (branch `bench-aa-effort-slugs`) and the worktree and branch `t28-tier-order` are
   merged and can be removed; so are the branches `delegate-lane-catalog` and
   `effort-data-tooling`.
2. **Provisional figures**: the `PROVISIONAL` notes on the generated lanes still say
   "Confirm in the wizard". The tiers are now Orin's; `meter_weight` and `timeout` on
   those lanes are still copies, and `astra-high@codex` has `price` null with the note
   "not sourced" (`6e0f0b1` quoted `10 / 1 / 12.5 / 50` without a source). Find the
   source before pasting the figures, then reword the notes.
3. **Carry-rule limit**: the carry page never proposes an agy flash lane off, because
   each agy effort is a separate model name (ticket 19).

**Waiting on Orin** (nothing else blocks on these):

- Ticket 23, delegate meter rows under the status line, is on `main` and live
  in Orin's status line since 2026-09-11, with the
  `report.py statusline off|on|toggle` switch and its ⌥⌘D Hammerspoon shortcut
  (`~/.hammerspoon` is the Makefile's whole-directory symlink into the repo,
  never a stow package). Ticket 23 holds the row format and the decisions; its
  last open box is one press of ⌥⌘D in each direction.
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
costs across sources. Where a note says AA covers a model, it means the
`/models/<slug>` page payload that `effort.py aa` reads. AA's cost per task is the
Intelligence Index's, one figure per variant, repeated on each component row. AA does
not measure Haiku at a lane's effort (`sources.json` says why).

Since ticket 19 the report, the tier pages and the benchmark page read AA only from
those accepted rows (`bench.py --effort-rows`, `setup.py --effort-rows`), one figure
per lane at the lane's own effort. The free API, `AA_URL`, `load_key` and the
key-file argument are gone, and nothing reads `~/.config/delegate/aa-key` any more;
if the file is still there it is unused, and it must still never be stowed or
committed, since this repo is public. Ticket 18's Landed note carries the
measurements; llm-cost-frontier's `update.py` (catalystneuro, BSD-3) was the
reference for where the dataset sits in the page.

## Settled, do not re-raise

- `lanes.json` and `routing.json` both ship in this public repo via `stow/delegate/`.
  Orin ruled the subscription costs and vendor notes non-sensitive, so no split to a
  forge and no constraint on what the pre-screen may write (2026-09-10).
- `trust` is gone from the design entirely. Ranking sorts
  `(tier asc, order asc, pace desc, lane name asc)`, where `order` is the lane's place
  inside its tier from the wizard's review page and a lane without one sorts after
  every lane with one; the name term is an arbitrary deterministic tie-break. A steal
  by `margin` can happen inside a tier, which is the load balance; a catalog with no
  `order` ranks as before (tickets 01, 02 and 28).
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
- The carry page proposes a lane off when another effort of the same model, for no
  more money, beats it on more than half of the benchmarks one source scored both
  on. The AA composite index is shown and never counted (Orin, 2026-09-11, ticket
  18).
- The benchmark page's frontier is a display aid, not a rule: nothing reads it, and
  the carry rule above is the only thing that proposes a lane off (ticket 24).

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
