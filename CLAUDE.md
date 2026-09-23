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

**Delegate entry points** (redesign tickets 33-36, landed and pushed 2026-09-22, `71c6661`):
- `delegate global` runs the setup wizard from any directory.
- `delegate project` opens the dashboard for the Git project of the current directory.
- `make configs` links the command into `~/.local/bin`.

At start the wizard refreshes the Artificial Analysis rows (cached 24 h in
`~/.cache/delegate/bench/aa/`, falling back to `.scratch/delegate-redesign/_data/`) and
each harness's model list, then screens the current generation. The rules are in
tickets 33 and 35 and in the skill `CLAUDE.md`. Orin's first refreshed run is `776df1a`.
- The new Lanes are priced from
  `.scratch/delegate-redesign/research/2026-09-22-new-model-prices.md`. The exception is
  `grok47fast-high`, which has no published price.
- This checkout's git-ignored `.delegate/routing.json` holds
  `project_order: ["luna6-max@codex"]`.

**Dashboard `deck`** (production since 2026-09-20). Its spec is
`docs/superpowers/specs/2026-09-13-delegate-dashboard-plugin.md`, whose branch-only rule
Orin replaced on 2026-09-20. Its tickets are 10-14 of
`.scratch/delegate-dashboard-plugin/issues/`, and `tools/delegate-dashboard/CLAUDE.md`
owns the keys, the model boundary and the save rules. A project's `.delegate/` policy
never goes to main. Open, all Orin's:
- his confirmations in tickets 12 and 13 (`v` does nothing; staging, undo and save
  driven once);
- the worker decisions that ticket 13 lists;
- ticket 10's one decision (project saves keep the canonical `catalog.edit_catalog`
  document shape).

**Delegate redesign:** spec `docs/superpowers/specs/2026-09-08-delegate-redesign.md`, and
tickets in `.scratch/delegate-redesign/issues/`, each with its decisions and a Landed
note. Tickets 01-19 and 22-36 are landed. A box left unticked there is Orin's own
confirmation, and the ticket's Status line names it. Skill context:
`agents/skills/delegate/CLAUDE.md`. Project policy (tickets 02-04 of the dashboard effort,
32, 33, 36): `project_order` reorders carried Lanes inside their effective Tiers, and a
project `lanes.json` may set a Lane's Tier. An entry that names a removed or off Lane
gives a warning and never stops routing.

**Other efforts:**
- `.scratch/delegate-modular/` (complete 2026-09-16; its `CLAUDE.md` holds the record).
  The root `prompt.md` is its original research brief, kept as scope history.
- `.scratch/delegate-browser/issues/` 01-07: browser setup and parity. Read the browser
  section of the skill `CLAUDE.md` and
  `.scratch/delegate-browser/research/2026-09-10-browser-routes.md` before changing
  browser dispatch.
- `.scratch/dotfiles-bootstrap/issues/` 01-05: bootstrap and maintenance, not started.
  01 and 02 can start now.

**Live configuration:** `~/.config/delegate/{lanes,routing}.json` are stow links into
this repo. The plain files in `~/.config/delegate/_pre-stow-2026-09-13/` are unused.
Current Tier and Order values belong to the catalog. The long form
`make -C <checkout> delegate-wizard` still works, and `WIZARD_ARGS` adds setup flags.

**Open, in priority order:**

1. **Tier 1 depends on codex alone.** It holds only `luna6-high@codex`, and
   `catalog.py check` warns about that. When codex is under the Gate, `scout` and
   `mechanical` overflow to Tier 3 (ticket 29). The coverage is Orin's to set, in the
   wizard or per project.
2. **Order inside a Tier:** Orin's open question (capability against cost), not yet a
   ticket. The session's position (2026-09-22):
   - capability belongs in the Tier boundaries, and inside a Tier the cheapest Lane
     comes first;
   - Pace and Margin then spread the load;
   - the real cost is `meter_weight`, which is not measured; the page's "Price per
     model" chart shows only list price, as a stand-in.
3. **Unmeasured figures:** `meter_weight` and `timeout` on the generated Lanes are
   copies, and each Lane's note says `UNMEASURED` and names the source Lane. The grok and
   agy cache-write prices are not published.
4. **The Claude Meter probe hangs inside this project.** `claude -p ... /usage` did not
   return within 45 s from a dotfiles checkout, and takes about 3 s from `~`. The probe
   runs from `~` (`fb845e3`), and the cause is not known.

**Waiting on Orin** (nothing else blocks on these):

- Ticket 23: press ⌥⌘D once in each direction (the status-line meter rows and
  `report.py statusline off|on|toggle`). `~/.hammerspoon` is the Makefile's
  whole-directory symlink, never a stow package.
- Type each of the four `/delegate-*` wrappers once, with a plain-language constraint
  (ticket 11).
- Two one-liners in his own files, outside this repo (ticket 09):
  - `~/.claude/hooks/delegate-gate.py` names `{SKILL_DIR}/delegate.py`, which moved to
    `scripts/delegate.py`, so the hook still advises a path that does not exist.
  - `export DELEGATE_BALANCE=1` is still line 1 of `~/.zshrc.local`.
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

Coverage is uneven and the three sources are not interchangeable:
- swerb reaches only `gpt-5.6-sol` and `gpt-5.6-luna`, but publishes slugs.
- Artificial Analysis and Terminal-Bench are wider, but publish display names
  (ticket 16).

Cost is per task on swerb and on Artificial Analysis, but Terminal-Bench's
`display_cost` is a whole-run figure. Even the two per-task numbers measure different
task sets, so never compare costs across sources. AA's cost per task is the
Intelligence Index's, one figure per variant. AA does not measure Haiku at a Lane's
effort (`sources.json` says why). Nothing reads `~/.config/delegate/aa-key`. If the file
still exists it must never be stowed or committed, because this repo is public.

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
- A new generation supersedes the old one, and every current-generation model shows
  for screening, at every effort (Orin, 2026-09-22; tickets 33 and 35). agy shows only
  its Gemini models. Orin: "ignore the Gemini Claude pool".
- Effort is fixed per Lane, and ranking picks a Lane, never an effort. The one path
  for a different effort is a named `dispatch --effort` (Orin, 2026-09-22; the comment at
  the Pick in `rank.py`).

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
