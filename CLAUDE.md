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

**Current generation and the `delegate` command** (redesign tickets 33-35, 2026-09-22).
`delegate global` runs the wizard, and `delegate project` opens the dashboard for the Git
project of the current directory. `make configs` links the command into `~/.local/bin`.

Ticket 33 changed what the wizard does at start. It refreshes the Artificial Analysis
rows (cached 24 h in `~/.cache/delegate/bench/aa/`) and each harness's model list, then
shows the current generation of every harness, at every effort, on the carry page.
- A superseded model's Lanes leave the catalog on save.
- A new Lane starts carried, except `ultra`, and a successor takes its predecessor's Tier
  and Order (ticket 35).
- The benchmark page places any Lane that has rows, and `o` rebuilds the page from the
  wizard's current state (ticket 35).
- New claude Lanes get their agent files, and `make delegate-wizard` relinks them.

The terms are in `CONTEXT.md` (**Level**, **Superseded**, **Generation**). agy shows only
its Gemini models; Orin: "ignore the Gemini Claude pool".

Orin's steps: `make -C ~/dotfiles configs`, then one `delegate global` run. The session's
steps after that run:
- prices for the new Lanes, from
  `.scratch/delegate-redesign/research/2026-09-22-new-model-prices.md`;
- this checkout's `.delegate/routing.json` `project_order`, moved from `luna-*` to `luna6-*`.

**Dashboard: `deck` is production and on main** (merged 2026-09-20, `0ffffea`). Orin
accepted the layout `deck` (ticket 11) and said "lock in the deck layout as the production
version". Tickets 12-14 of `.scratch/delegate-dashboard-plugin/issues/` carry the record:
the one view `deck.py` (12), staged edits with one save, `w` saves and `u`/`U` drop (13),
and `catalog.plan_edits`, the one public in-memory planning path (14). Open it with
`delegate project` from any project directory, or `make delegate-dashboard` for a Herdr
split; the Herdr plugin link points at this checkout. `tools/delegate-dashboard/CLAUDE.md` owns the keys, the model boundary and
the save rules. Open, all Orin's: his confirmations in tickets 12 and 13 (`v` does nothing;
staging, undo and save driven once), the worker decisions ticket 13 lists that he may
overrule, and ticket 10's one decision (project saves keep the canonical
`catalog.edit_catalog` document shape). A project's `.delegate/` policy never goes to main; this checkout's own `.delegate/` is
git-ignored. Every dashboard worktree and branch is removed, the remote one included
(checked 2026-09-22). The Rust monitor `tools/delegate-mon/` stays separate.

**Delegate modular batch complete** (2026-09-16): tickets 01–13 landed, all 13
script suites and full/focused terminal checks passed, and independent review
findings were fixed. Orin accepted the Class guide; its humanizer redraft landed
at `a24d20e`. Read `.scratch/delegate-modular/CLAUDE.md` for the implementation
record and qualified research pointers. Multi-domain scope and the remaining
consultation steps are still proposals.

**Retained work** (2026-09-16): `.scratch/dotfiles-bootstrap/issues/` holds five
unimplemented bootstrap and maintenance tickets, separate from the monitor work.
`prompt.md` is the original modular-research brief, retained as scope history.
Orin set the global Gate to 5% on 2026-09-18 (`5be0848`).

**Project routing backend** (tickets 02-04 of the dashboard effort, and ticket 32): a
project's `.delegate/routing.json` may carry `project_order`, which reorders carried Lanes
inside their effective Tiers, and its `.delegate/lanes.json` may set a Lane's Tier for that
project and nothing else (`catalog.load_catalog()`, `catalog.validate_project_routing()`).
`rank.tier_leaders()` gives one leader per Tier; `rank.meter_observations()` owns Meter
cache validity. Spec `docs/superpowers/specs/2026-09-13-delegate-dashboard-plugin.md`,
whose branch-only rule for the UI Orin's word of 2026-09-20 replaced.

**Delegate redesign follow-ups:** spec
`docs/superpowers/specs/2026-09-08-delegate-redesign.md`; tickets in
`.scratch/delegate-redesign/issues/`, each carrying its own decisions and a
"Landed" note; skill context `agents/skills/delegate/CLAUDE.md`. Tickets 01-19 and
22-28 are landed, and the boxes left unticked there are Orin's own confirmations,
which each ticket's Status line names.

**Delegate browser follow-ups:** the former `worktree/silver-river-1847` work is
merged into `main`; that local branch is closed. Tickets 01–07 in
`.scratch/delegate-browser/issues/` own remaining setup and parity work. Before
changing browser dispatch, read the browser section of
`agents/skills/delegate/CLAUDE.md` and
`.scratch/delegate-browser/research/2026-09-10-browser-routes.md` for the proven
Mac behavior and outstanding Grok, native Claude, and Omarchy work.

**Live configuration:** `~/.config/delegate/{lanes,routing}.json` are stow links
into this repo since 2026-09-13. The replaced plain files in
`~/.config/delegate/_pre-stow-2026-09-13/` are unused. Orin's Tier and Order choices
are recorded in ticket 28; current values belong to the catalog. `delegate global` edits
that catalog from any directory. The long form `make -C <checkout> delegate-wizard` still
works, and `WIZARD_ARGS` adds setup flags. For historical implementation and validation,
read the redesign tickets rather than reconstructing deleted worker branches.

**Open, in priority order:**

1. **Tier 1-2 coverage**: every carried Tier 1-2 Lane drains `codex` (`catalog.py check`
   warns). Since ticket 29 a Gate-only stop overflows one Tier up, so `scout` and
   `mechanical` run on Tier 3 Lanes while codex is under the Gate. The coverage itself is
   Orin's to set in the wizard, or per project since ticket 32.
2. **Unmeasured figures**: `meter_weight` and `timeout` on the generated Lanes are still
   copies; each Lane's note says `UNMEASURED` and from which Lane. Prices are sourced
   since 2026-09-18 (OpenAI and Anthropic pricing pages, named in each note), except the
   grok and agy cache-write prices. The Lanes that ticket 33 adds start with the note
   `UNPRICED`; `grok-4.7-build-fast` has no published price.
3. **The Claude Meter probe hangs inside this project**: `claude -p ... /usage` did not
   return within 45 s from a dotfiles checkout and takes about 3 s from `~`. The probe
   now runs from `~` (`fb845e3`); the cause is not known.

Tickets 29-32 merged to `main` on 2026-09-19 (overflow and the one-Meter warning; the agy
carry rule; agy Remaining and Pace, which reverses modular ticket 13; a project's
`.delegate/lanes.json`). Each ticket names the session decisions Orin may overrule.

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

### Worktrees

One slug names the `.scratch/` effort, the `worktree/<slug>` branch and the Herdr
checkout under `~/.herdr/worktrees/`; never `/tmp`. See `docs/agents/worktrees.md`.

### Domain docs

Single-context: the glossary is the root `CONTEXT.md`; `docs/adr/` does not exist
yet. See `docs/agents/domain.md`.
