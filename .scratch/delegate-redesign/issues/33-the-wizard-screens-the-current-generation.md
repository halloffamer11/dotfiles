# 33 — The wizard refreshes to the current generation, then screens it

**What to build:** `make delegate-wizard` stays the one command. When it starts, it
refreshes the benchmark rows and the model list itself. Every current-generation model
of every harness then shows on the carry (screening) page, at every effort, and
superseded models leave the catalog. Today a new model reaches the catalog only after
five manual steps: `discover.py`, `discover.py --efforts` with `TODO` stanzas pasted
by hand, a hand-written Claude agent file, `effort.py aa` copied over the accepted
rows, then the wizard.

Orin, 2026-09-22: "I just want a simple interface to the tool not a list of commands to
remember … why not add it to the delegate-wizard so it's one command that refreshes
efficiently?" · "new generation models supersede old one" · "the screening page in the
tool should always have the refreshed list of current generation models at each tier.
Claude and codex have multiple model levels but grok and agy only have 1-2. The
expectation is for all models to be shown initially for screening."

**Blocked by:** None — can start immediately.

## Rule

Orin's rules are the three quotes above. The points below are session decisions that
put them into practice; Orin may overrule any of them.

**What each harness offers.** The harness's own list is the source: `codex debug
models`, `agy models` and `grok models`, which `discover.py` already reads. Claude Code
names no model (`claude --help` offers only the aliases `fable`, `opus` and `sonnet`).
For the claude harness, the refreshed Artificial Analysis rows name the models. A
`Claude <Level> <version>` name maps to `claude-<level>-<major>[-<minor>]`, and only
for a level that the catalog already has on the claude harness (fable, opus, sonnet,
haiku). A level keeps its catalog model unless a newer version is named.

**Current generation.** Each harness shows its own vendor's models only: `gpt-*` on
codex, `gemini-*` on agy, `grok-*` on grok and `claude-*` on claude. Other vendors'
models that agy serves (`claude-sonnet-4-6`, `claude-opus-4-6-thinking`,
`gpt-oss-120b`) are not shown. A model hidden by its harness (codex
`"visibility": "hide"`) is not shown. A model's **level** is its slug with the version
number removed, after the agy effort suffix is stripped (`catalog.agy_family`). For
example, `gpt-6-sol` and `gpt-5.6-sol` are both level `gpt-sol`, and `gemini-3.8-flash`
is level `gemini-flash`. A model is **superseded** in either of two cases:
- The harness says so. codex `upgrade` is set on `gpt-5.5`.
- Another model on the same harness has the same level and a higher version.

The others are the current generation.

**What the refresh proposes.** The refresh runs in memory at the start. Nothing is
written until the wizard's confirm, and quitting writes nothing.
- Every effort of every current-generation model gets a Lane if the catalog has none.
  The efforts come from `discover.py`, which is still the only thing that may say an
  effort exists.
- A new Lane's name is `<level word><version digits>-<effort>@<harness>`, and it never
  collides with an existing Lane of another model. Expected on today's fixtures:
  `sol6`, `luna6`, `opus55`, `grok47`, `grok47fast` and `pro31`.
- A new Lane with a **predecessor** takes that predecessor's place: the superseded
  model's Lane at the same effort. It inherits `enabled`, `tier`, `order`, `meter`,
  `meter_weight` and `timeout`. Its note says `UNMEASURED: meter_weight and timeout
  copied from <lane>`.
- A new Lane with no predecessor starts carried. It is marked on no Tier page, so it
  ends on Tier 1 unless Orin marks it higher. Its meter, `meter_weight` and `timeout`
  are copied from the same harness's Lane at the same effort, with the same
  `UNMEASURED` note. An `ultra` Lane is always generated off (settled, ticket 15).
- Every new Lane gets `price` with all four keys `null` and the note `UNPRICED`. Prices
  come from vendor pages, never from a predecessor.
- Superseded Lanes leave `lanes.json` on save.
- A claude Lane has a native agent file, `agents/agents/lane-<name before @>.md`.
  The save writes the file for each new claude Lane, in the same form as the existing
  files, and removes the file of each superseded claude Lane.
- A current-generation Lane that the catalog already has keeps every field as it is.
  A catalog that is already current produces no change.

**Pages.** The start page states the changes, one line per model, for example
`gpt-5.6-sol → gpt-6-sol: sol6-*@codex replace sol-*@codex (6 Lanes)`. It also states
new models that have no predecessor and where the benchmark rows came from. The carry
page lists only current-generation Lanes, grouped as today, and the pre-screen runs on
them as today. A Lane with no benchmark row says so.

**Refreshing efficiently.** At start, the wizard fetches the Artificial Analysis rows
in process with `effort.py`'s `aa` path, into `~/.cache/delegate/bench/aa/`. It skips
the fetch when a fetch from the last 24 hours is there. The fetched rows replace the
repo's AA rows in the `--effort-rows` list. When the fetch fails, the wizard uses the
repo rows and the start page gives the reason. Terminal-Bench stays on the repo rows,
because its extraction needs a worker. The fetch and the harness probes run
concurrently.

**Projects.** A project's `.delegate/routing.json` `project_order` entry, or
`.delegate/lanes.json` entry, may name a Lane that the global catalog no longer has.
It is ignored, with one warning on stderr that names it. It must never stop routing:
today it raises `CatalogError`. The next project save drops it. This checkout's own
`.delegate/routing.json` names `luna-max@codex` and `luna-xhigh@codex`, so the case is
live.

**Make.** `make delegate-wizard` relinks the per-file agent links in
`~/.claude/agents` after the wizard exits. This is the `stow -R agents` step of
`make skills`, so a new native Lane's agent is live with no second command.

## Scope

Paths are relative to `agents/skills/delegate/` unless they are shown from the repo
root:
- `scripts/discover.py`: current generation, superseded, and the level and name rule.
- `scripts/setup.py` and `scripts/setup_tui.py`: refresh at start, the pages, and the
  save of Lanes and agent files.
- `scripts/effort.py`, only if the `aa` path needs a callable entry.
- `scripts/catalog.py`: stale project names warn.
- Tests: `tests/test_discover.py`, `tests/test_setup.py`, `tests/test_setup_tui.py`,
  `tests/test_catalog.py`, and new fixtures under `tests/fixtures/`.
- Root `Makefile` (`delegate-wizard`).
- Docs: `SKILL.md`, the skill `CLAUDE.md` (setup and discover entries), and root
  `CONTEXT.md` (new terms **Level**, **Generation** and **Superseded**).

The root `CLAUDE.md` is the session's to update at landing.

Out of scope:
- prices (the session fills them in after Orin's run);
- a Terminal-Bench refresh;
- measuring `meter_weight` and `timeout`;
- the carry rule;
- `discover.py --efforts`, which stays as it is.

Fixtures captured 2026-09-22 are in `.scratch/delegate-redesign/_work/fixtures-2026-09-22/`:
- `codex-debug-models.json`
- `agy-models.txt`
- `grok-models.txt`
- `claude-help.txt`
- `aa-accepted-2026-09-22.json`

Trim what the tests need into `tests/fixtures/`. Tests use no network and no live CLI.
They check the rule on fixtures, never Orin's Tiers.

## Acceptance

**Status:** ready-for-agent

- [x] On today's fixtures and the repo catalog, the refresh proposes these changes:
  - new: `sol6-*@codex` (low…ultra), `luna6-*@codex` (low…max), `opus55-*@claude`
    (low…max), `grok47-high@grok`, `grok47fast-high@grok`, `pro31-high@agy` and
    `pro31-low@agy`;
  - removed: `sol-*@codex`, `luna-*@codex`, `opus-*@claude` and `grok46-high@grok`;
  - not shown: `gpt-5.5`, `gemini-3.7-flash`, `gemini-3.6-flash`, `grok-4.6`,
    `grok-4.5`, agy's other-vendor models, and the hidden codex models;
  - unchanged: `astra-*`, `terra-*`, `flash-*@agy`, `fable-*`, `sonnet-*` and
    `haiku-high`.
- [x] Each successor Lane has its predecessor's `enabled`, `tier`, `order`, meter,
  weight and timeout. Every new Lane has a `null` price with an `UNPRICED` note, and
  `ultra` is off.
- [x] The saved catalog passes `scripts/catalog.py check`. The saved agent files for
  new claude Lanes match the existing form, and the superseded ones are gone. A second
  refresh on the saved catalog proposes nothing.
- [x] `bench.collect` gives the fetched `Claude Opus 5.5` rows to the `opus55-*`
  Lanes and the `Grok 4.7` high row to `grok47-high@grok`.
- [x] The fetch is skipped when the cache is less than 24 hours old. A failed fetch
  falls back to the repo rows, and the start page says why.
- [x] A project file that names a removed Lane gives a warning, not an error, and
  `rank.py` still ranks in that project.
- [x] `--plain` prints the same change lines as the start page.
- [x] All 13 suites under `tests/` pass.

## Settled facts this ticket rests on

Read on 2026-09-22 from the fixtures above:
- codex lists `gpt-6-astra`, `gpt-6-sol`, `gpt-6-luna`, `gpt-5.6-sol`, `gpt-5.6-terra`,
  `gpt-5.6-luna` and `gpt-5.5`. `gpt-5.5` carries
  `upgrade → gpt-5.6-sol, retiring 2026-10-14`. `gpt-reserve` and `codex-auto-review`
  are hidden.
- grok lists `grok-4.7` (its default), `grok-4.7-build-fast`, `grok-4.6` and
  `grok-4.5`.
- agy lists Gemini 3.8, 3.7 and 3.6 Flash, Gemini 3.1 Pro (high, low), and three
  other-vendor models.
- The Artificial Analysis rows added since 2026-09-13 include `Claude Opus 5.5`
  (low…max) and `Grok 4.7` (high, xhigh). They have no `GPT-6 Sol` or `GPT-6 Luna`
  rows yet.
- Claude Opus 5.5 (`claude-opus-5-5`) costs $4 in / $20 out per 1M tokens, and $0.20
  for cache reads. Opus 5 costs $5 / $25.

## Landed

The refresh runs at the start of `make delegate-wizard`, in memory, and writes
nothing until the confirm.

- `scripts/discover.py`: `model_level`, `mark_generation`, `lane_stem`,
  `claude_generation`, `refresh_catalog` and `map_lanes`. Every model entry
  carries `level`, `version` and `superseded`, so `discover.py --json` shows the
  generation too.
- `scripts/setup.py`: `refresh_effort_rows` (the in-process Artificial Analysis
  fetch, its 24-hour cache and its fallback), `published_model_names`,
  `native_agent_text`, `native_agents_dir` and `save_native_agents`. The fetch
  runs in a thread beside the harness probes.
- `scripts/setup_tui.py`: `refresh_lines`, and the start page's rows note.
- `scripts/effort.py`: `run_aa`/`check_files` take `quiet`, for a caller that
  prints its own line.
- `scripts/catalog.py`: `warn_stale_lane`; a project `project_order` or
  `.delegate/lanes.json` entry naming a lane the catalog lost warns and is
  ignored rather than raising.
- Root `Makefile`: `delegate-wizard` restows `~/.claude/agents` after the wizard.
- Fixtures: `tests/fixtures/refresh-2026-09-22/`, trimmed from the captures named
  above, with the catalog of 2026-09-22 frozen beside them — the refresh's own
  first run changes the live one, so the tests never read it.

Decisions this session made where the ticket left the code a choice; Orin may
overrule any of them:

- A variant level is named from the level it extends, and only a
  current-generation level counts. codex still lists `gpt-5.5`, whose level is
  the bare `gpt`, and that must not make `gpt-6-sol` read `gpt6sol`; with it
  superseded, `grok-4.7-build-fast` still reads `grok47fast` beside `grok47`.
- Where a generated name would collide with a lane on another model, a counter
  follows the stem (`sol62-high@codex`). Nothing on today's fixtures collides.
- A new lane with no predecessor copies its meter, weight and timeout from a
  lane the refresh keeps, and failing that from one it adds, so the note never
  names a lane that is leaving.
- `basis` on a new lane states what it replaces, or that the model is new on the
  harness; an `ultra` lane keeps the existing ultra basis.
- The agent files are written only when the catalog being written is this
  checkout's own; any other catalog gets a note saying so. That is what keeps a
  test from writing into `agents/agents/`.
- `--no-discover` skips the row fetch as well, since it means acquire nothing.
- Prices: `.scratch/delegate-redesign/research/2026-09-22-new-model-prices.md`
  holds the figures for the lanes this refresh adds. Filling them in is the
  session's, after Orin's run.
