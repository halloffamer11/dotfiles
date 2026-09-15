# Delegate refactoring consultation

Direction for a modular skill. Baseline is the current code, not the 2026-09-08
pseudocode (`classTier`, weekly-only Gate, no Order). Both reviews record that
drift (astra Seams "Documentation differences"; grok Seams "Catalog on disk",
"Ranking rule").

## Story to module map

| Capability | Today | Reviews | Gap |
|---|---|---|---|
| Setup: harness detection | `setup.py:291` always runs ADS `discover.mjs` via `read_discovery` (`setup.py:27`). Then `discover.discover` (`setup.py:302`, `discover.py:370`) queries the CLIs. Per-harness probe errors continue (`discover.py:441`). A `discover.mjs` failure aborts the wizard (`setup.py:39`). `--no-discover` skips only the Python pass (`setup.py:298`). | Grok Finding 4 (high): setup discovers twice; drop `discover.mjs` from the main path. Astra Finding 8 / Leaks: authentication discovery and model discovery are different observations. | One discovery result. A failing harness must report and continue. No Node script on the default path. |
| Setup: tier count | Tiers are the closed set 1–4. Floor/ceiling validation (`catalog.py:526`), wizard pages (`setup_tui.py:533`), and `tier_leaders` (`rank.py:286`) all hard-code that range. | Neither review treats N-tiers as a seam. Both treat 1–4 as the ranking domain. | No knob. Adding one would rewrite validation, the wizard, the page, and every test. Keep four. |
| Setup: classes and definitions | Closed tuple `CLASSES` (`catalog.py:51`). Global `routing.json` must name every class with floor and ceiling (`catalog.py:487`, `catalog.py:502`). Unknown names are rejected (`catalog.py:506`; `test_catalog.py:390`). Prose is one line in `SKILL.md:12`. No `classes.md`. | Both reviews call `catalog.load_catalog` the catalog seam. Neither found a classification module. | Numeric ranges live in JSON. Judgment lives in skill prose that already drifts from the live catalog (`SKILL.md:35` tells a scout to take `--tier 3`; stow `routing.json:4` gives scout ceiling 2). |
| Setup: tier mapping with benchmark assist | TUI: carry, four tier pages, review order, routing (`setup_tui.py:533`). HTML board is the first input; `o` opens it; Copy-as-lines / `v` / `--tiers-from` apply `<lane> <1-4\|off>` (`CLAUDE.md:23`, `setup_tui.py:83`). Carry rule is `dominating_effort` / `propose_enabled` (`setup_tui.py:430`, `setup_tui.py:494`). `--plain` walks every lane and then routing (`setup.py:326`). Enter with no edits keeps current tiers (`CLAUDE.md:23`). | Astra Finding 2 and grok Finding 1 (high): carry policy sits in the TUI; `bench_page.py:28` imports it and parses reason prose. Astra Finding 7: `--plain` shells `bench.py` (`setup.py:118`) while the TUI calls `bench.collect` (`setup.py:341`). | Carry/order belong beside `bench.collect`. The wizard is still a full pass. No surgical `--set-tier` / `--add-class` / `--meters`. |
| Routing: classification the orchestrator loads | `SKILL.md:20` says "Pick the class." Rank takes a class name and looks up floor/ceiling (`rank.py:245`). Typed wrappers also take a class (`delegate-codex/SKILL.md:14`). | Astra Pass-through: wrappers are a real entrypoint, not a new abstraction. Grok Pass-through: same. | No Markdown guide with signals, examples, counter-examples, or when to raise `--tier`. The orchestrator guesses from one line. |
| Routing: deterministic tier and usage selection | `rank_range` (`rank.py:123`) is the rule: enabled, floor..ceiling, `r < gate` veto, CLI present; sort `(unknown, tier, unordered, order, -pace, name)` (`rank.py:205`); Margin steal (`rank.py:218`). `rank` and `tier_leaders` call it (`rank.py:268`, `rank.py:287`). `delegate.run` reprints the same header (`delegate.py:847` vs `rank.py:458`). | Both Seams "Ranking rule": keep `rank_range`; dispatch duplicates Range checks and the heading (astra Finding 8, grok Finding 5). Unused `rank(..., effort=None)` (`rank.py:252`). | One formatter. Range validation stays in ranking. Dispatch consumes a validated Pick. |
| Routing: out-of-usage warning and ask | `rank.py:458` prints `STOP: no lane eligible for <class>`, then the veto rows, then `sys.exit(1)` (`rank.py:462`; JSON form `rank.py:456`). `delegate.run` does the same (`delegate.py:850`, `delegate.py:907`). Guarded by `test_rank.py:363`. `SKILL.md:32` says stop and start nothing. It does not tell the session to ask. | Both treat STOP as the ranking contract. Neither asked for an interactive prompt inside the script. | Machine contract is already stop + reasons + exit 1. The missing piece is skill prose that asks the human for direction. Do not put a prompt in `rank.py`. |
| Usage metering on/off with gate and margin | Always on. `gate` and `margin` are required global keys (`catalog.py:488`; live values `stow/.../routing.json:25`). Three Gate rules: `usage.GATE = 0.10` stamps `status` (`usage.py:32`, `usage.py:57`); `rank_range` uses `routing.gate` with `r < gate` (`rank.py:139`, `rank.py:176`); `report.py:206` hard-codes "under 10%", `report.py:175` filters `status == "ok"`, `report.py:627` ORs weekly remaining `<=` Gate with that status. No on/off key (`catalog.py:478` allowed keys). | Grok Findings 2–3 (high): Gate is three rules; `meter_observations` (`rank.py:83`) is unused by viewers. Astra Finding 1 (medium): same split; a local check with Gate 0.0 and remaining 0.05 produced an eligible Codex lane whose observation still said `unavailable`. | One eligibility predicate. One observation reader. An explicit meters on/off switch, default on. |
| Dispatch with container and git hygiene | `dispatch` resolves, builds a prompt, allocates an exclusive Run dir, then relays or prints a native line (`delegate.py:715`, `delegate.py:351`, `delegate.py:440`, `delegate.py:765`). `--write` must already be an existing directory (`delegate.py:199`). No worktree create. No container. Relays pass `--read-only` when there is no write dir (`delegate.py:451`). Native path exits before ledger and `return.json` (`delegate.py:765`). Courier assumes `run=` and `return.json` (`courier.md:15`). | Astra Finding 4 / grok Finding 6: native is not isolated from relay prep; ADS check runs first (`delegate.py:244`). Astra Finding 3: `map_result` coerces the return contract. | Session owns worktree creation (`SKILL.md:28`). Do not add a container layer. Native handoff still needs a structured record. |
| Herdr observation and hot-loaded order | Each rank/dispatch calls `load_catalog` (`rank.py:387`, `delegate.py:875`). Project `project_order` reorders carried lanes inside global Tiers (`catalog.py:727`, `catalog.py:628`). Gate and Margin already project-override (`catalog.py:574`). Dashboard spec: Herdr is presentation only (`docs/superpowers/specs/2026-09-13-delegate-dashboard-plugin.md:77`). Prototype UI is on another branch (`CLAUDE.md:14`). `tools/delegate-mon/` is a separate ledger TUI. | Astra "What is already right": keep `load_catalog` as the effective-read path. Grok same. | Hot-load already works because every command re-reads disk. A production Herdr pane is not a skill-module problem. |
| Project-specific rules | `<git-root>/.delegate/routing.json`, partial, merged per class and per key (`catalog.py:680`, `SKILL.md:17`). Setup loads global files with `load_json` and never `load_catalog` (`setup.py:72`), so a wizard start does not apply Project order. | Grok Seams "Catalog on disk": that cross-cut. Astra Seams: keep effective routing separate from the editable global catalog. | Setup must edit global documents. Ranking already sees the project file. A project class-guide overlay does not exist. |
| Distribution via a skills installer | Live catalog is stow links (`Makefile:103`, `SKILL.md:16`). `make skills` stows this repo's skills (`Makefile:74`). `npx skills` is used for herdr and humanizer, not delegate (`Makefile:81`). Redesign spec mentioned `npx skills add` for ADS relays (`docs/superpowers/specs/2026-09-08-delegate-redesign.md:142`). `/delegate setup` is an argument to the same skill (`SKILL.md:18`), not a separate `/delegate-setup`. | Out of both reviews' script inventory. | Publishing the skill through npx would copy instructions without the stowed catalog. That is the wrong installer for this tree. |

## Target seams

Keep six code seams and one instruction seam. Drop the rest.

### 1. Catalog on disk (real)

Data: global `lanes.json` + global `routing.json` + optional project routing. Effective document:

```
{meters, lanes, routing, sources, files}
```

Callers: every rank, dispatch, report, bench, and setup write. Hides strict JSON, merge, Project order projection, published-name map, atomic `write_json` (`catalog.py:103`, `catalog.py:769`). Implementation stays `load_catalog`, `validate_lanes`, `validate_routing`, `validate_project_routing`, `write_json`. Setup must stop bypassing `load_catalog` for reads; it may still load the two global files as the editable documents (astra Seams "Catalog on disk"; grok same).

Proposed surgical CLI on this seam, not a new module: `catalog.py set` (proposed) for one field (`lanes.<name>.tier`, `routing.gate`, `routing.classes.<class>.floor`, proposed `routing.meters`). Validate, then `write_json`.

### 2. Metering (real; today split)

Data crossing the seam: one observation document. Envelope `{probed_at, lanes:[{lane, r, pace, remaining_weekly, status, ...}]}` as `usage.py:64` writes it. Rank already accepts that envelope and the legacy map (`rank.py:83`).

Callers: `rank_range`, `delegate.run`, `report.limits`, `report.statusline`. Hides vendor probes, cache TTL, Remaining/Pace math, and the Gate predicate.

Today the probe is `usage.py`, validity is `rank.meter_observations`, eligibility is copied in three places (both reviews, Findings on Gate). Collapse to one module in `usage.py` (keep the file; do not add `meters.py` unless the probe file becomes unreadable):

```
probe(refresh=False) -> document
load_cached() -> document
observations(document) -> map | None
eligible(observation, gate) -> bool   # r is None or r >= gate
```

`rank.meter_observations` moves here or becomes a one-line re-export. Ranking keeps the sort and the steal. Reporting stops reading the cache file itself (`report.py:538`).

On/off is a catalog field on this seam, not a fourth Gate. See §4.

### 3. Ranking rule (real)

Data: class name or exact Tier, effective catalog, observation map, present harnesses. Output: ordered rows with one `pick`, or no pick.

Callers: `rank` CLI, `delegate.run`, statusline badges, Herdr dashboard via `tier_leaders`. Hides Range, Gate veto, Order, Pace, Margin, unknown-last. Implementation: `rank_range`, `rank`, `tier_leaders`, `format_rows` (`rank.py:123`, `rank.py:245`, `rank.py:278`, `rank.py:301`). Delete `delegate._print_rank_output` (`delegate.py:847`). Delete unused `effort` (`rank.py:252`).

### 4. Dispatch / relay (real)

Data in: resolved lane, brief, cwd, optional existing `--write` dir. Data out: Run dir + `return.json`, or a native handoff record `{kind: native, lane, agent, prompt, run}` (proposed). Callers: `delegate.py run`/`dispatch`, courier, browser probes, effort extract.

Hides prompt splice, exclusive Run dir, per-harness relay argv, return mapping. Implementation: `resolve`, `build_prompt`, `allocate_run_dir`, `run_relay`, `map_result` (`delegate.py:129`, `delegate.py:277`, `delegate.py:351`, `delegate.py:440`, `delegate.py:525`). Native branch before ADS check (astra Finding 4). Courier must reject `kind=native` (`courier.md:15`).

Not in this seam: creating git worktrees, starting containers.

### 5. Benchmark decisions (real; today in the TUI)

Data: accepted effort rows + lanes document. Output: structured carry decision `{lane, enabled, kind, source, competitor}` (proposed), plus lane display order. Callers: Wizard and HTML page. Hides domination arithmetic. Move `dominating_effort`, `propose_enabled`, `group_lanes`, `lane_order` out of `setup_tui.py` into `bench.py` beside `collect` (astra Finding 2, grok Finding 1). Renderers keep wording.

### 6. Discovery result (real)

Data: `{harnesses: {name: {status: ok|missing|error, error, discovered_count}}, models, unmapped, retired}` (`discover.py:497`). Callers: setup start facts. Hides CLI parse and drift. Implementation: `discover.discover` (`discover.py:370`). Delete default `discover.mjs` (`setup.py:32`). A harness `error` is a notice, not an abort.

### 7. Class guide (real instruction seam, not a Python module)

Data: Markdown the orchestrator reads. Names must equal `routing.classes` keys. Callers: the session at classify time (`SKILL.md:20`). Hides examples and counter-examples. No scorer. See §3.

### Dropped as speculative

- A Python classifier or "job type" API. Judgment is the orchestrator's; code cannot own it.
- A router facade over catalog+rank+usage. Callers already have three verbs: load, rank, dispatch.
- `events` as a service (astra Pass-through: inline `ledger_finish`).
- A `paths.py` module. Export `usage.get_cache_path` (`usage.py:36`) and use it.
- A frontend interface over TUI and HTML. Share policy data; keep two renderers (astra "What is already right" on `Wizard.handle/view/result`).
- A worktree/container factory. `--write` is a directory the session already made (`delegate.py:199`, `SKILL.md:28`).
- New abstractions over the four typed wrappers (both reviews, Pass-through).
- `setup.show_bench` as a pipeline (astra Pass-through).

## The classification abstraction

Proposed file: `agents/skills/delegate/assets/classes.md`.
Proposed project overlay: `<git-root>/.delegate/classes.md`.

`SKILL.md` step 1 becomes: read CONTEXT.md terms, read `assets/classes.md`, then the project overlay if present, then pick exactly one class, then write the brief.

### Sections of `assets/classes.md`

1. **How to pick.** One class. Never two. If two seem to fit, the counter-examples decide. Named dispatch (`dispatch --lane`) skips class Range; it does not skip writing a class on the prompt (leash depends on it, `delegate.py:264`).
2. **One heading per class**, `## <class>`, names matching `catalog.CLASSES` (`catalog.py:51`).
3. **Out of usage.** When `rank.py` / `delegate.py run` prints `STOP: no lane eligible for <class>` and exits 1, do not invent a lane. Show the veto reasons. Ask the human: named dispatch, abort, or a one-job policy change they state in prose.

### How a class is defined (each `##` heading)

- **Intent.** One sentence. Today's `SKILL.md:12` lines move here: scout = find, ground, summarize; mechanical = renames, transforms, extraction; impl = implementation with a spec; review = independent review of a diff, reviewer family differs from author; hard-impl = the remainder of impl that needs the class ceiling.
- **Signals.** Observable properties of the brief (needs a spec, needs a diff, needs a web pass, is a rename).
- **Examples.** Two or three jobs that are this class.
- **Counter-examples.** Jobs that look like this class and are not. Example: "find the file, then edit it" is impl, not scout.
- **Default tier.** "The floor in `routing.json`. Do not write the number here." Point at the `rank.py` header (`floor=` `ceiling=`), which is the live value.
- **When to raise.** Qualitative: judgment, ambiguity, adversarial input. The flag is `--tier N` and N must stay inside the printed Range (`rank.py:263`, `SKILL.md:34`). Do not hard-code `--tier 3` for scout; that line is already false against stow `routing.json:4`.
- **When not to use this class.**

### How a user adds a class

Not from Markdown alone, and not from the wizard's routing page. The name set is closed in `CLASSES` (`catalog.py:51`, `catalog.py:506`). Adding a class is one catalog change:

1. Append the slug to `CLASSES`.
2. Add floor/ceiling to global `routing.json` and `assets/samples/routing.json`.
3. Add the `##` section to `assets/classes.md`.
4. Extend `test_catalog.py` unknown-class and missing-class cases; extend the routing page (`setup_tui.py:1111`).

Until a real new class exists (knowledge-work or otherwise), do not open the registry. A wizard checkbox that writes a name `rank.py` does not know is a broken seam.

### Source of truth vs the guide

- **Machine source of truth:** `routing.json` `classes` for names, floor, and ceiling. Rank, dispatch, and setup read only that (`rank.py:259`, `catalog.py:497`).
- **Orchestrator source of truth for judgment:** `assets/classes.md` plus project overlay.
- **Validation:** proposed `catalog.py check` extension (or `catalog.py check-guide`): parse `##` headings; global guide headings must equal `CLASSES`; project overlay headings must be a subset; headings not in `routing.classes` fail; the guide must not contain `floor:` / `ceiling:` integers. Numbers in prose are how `SKILL.md:35` drifted.

### Project override

- Floor/ceiling: already `.delegate/routing.json` `classes.<name>.floor|ceiling` (`catalog.py:595`, stow note `routing.json:27`).
- Judgment: optional `.delegate/classes.md` replaces the matching `##` section for that project. It cannot introduce a class name. It cannot change floor or ceiling.

### What stays in code

Validation; the closed name set; 1–4 range; `floor <= ceiling`; the sort; Gate; Margin; `--tier` as a floor raise inside Range; named dispatch skipping Range.

### What belongs in prose

Signals, examples, counter-examples, when to raise `--tier`, what to ask on STOP.

## Usage metering as a switchable module

Default: on. Live catalog already has `gate: 0.1` and `margin: 0.2` (`stow/delegate/.config/delegate/routing.json:25`).

Proposed global key `meters`: boolean, default `true` when absent. Project may set `false`. `validate_routing` gains that key (`catalog.py:478` today would reject it). Do not encode off as `gate: 0`. Gate 0 still sorts on Pace and still steals (`rank.py:218`); that is load-balance with a zero floor, not metering off.

### One module

`usage.py` keeps probes and cache. It also owns:

- `get_cache_path` as the single path (`usage.py:36`; report currently drops `CONSULT_CACHE`, grok Finding 11, `report.py:38`).
- `observations` (today `rank.meter_observations`, `rank.py:83`).
- `eligible(obs, gate)`: unknown (`r is None`) never vetoes; measured `r < gate` vetoes. Stop stamping `status` from a private `GATE` constant (`usage.py:32`, `usage.py:57`). `status` may remain a display field derived from the effective Gate, or go away; ranking must not read it.

`rank_range` asks `eligible`. `limits --eligible` and the statusline gated mark ask the same function, with `routing.gate`, never `0.10` (`report.py:206`, `report.py:175`, `report.py:627`). That is the three-Gate problem both reviews named (grok Finding 2, astra Finding 1).

Pace stays on the observation. Margin stays a ranking parameter. Neither is a second Gate.

### When metering is off

`rank_range` receives `{}` observations (same as missing cache, `test_rank.py:848`). Every lane has unknown Pace. Unknown never steals and never blocks (`rank.py:35`, `rank.py:176`). Sort reduces to `(tier, order, name)`. No vendor probe on `run` or `rank`. Gate and Margin remain stored so turning meters back on does not require a wizard pass. Statusline draws Remaining if a cache exists, but does not mark Gate and does not change the Pick.

### When a class Range is entirely under Gate (meters on)

Keep the current machine contract, already tested:

```
STOP: no lane eligible for <class>
<one veto reason per lane>
```

Exit code **1** (`rank.py:462`, `delegate.py:907`, `test_rank.py:362`). JSON: `"pick": null` and exit 1 (`rank.py:456`). Start nothing.

Do not prompt inside the script. `SKILL.md` (proposed addition next to `SKILL.md:32`) tells the orchestrator: print the reasons; ask the human. Legal answers: abort; named `dispatch --lane` (today skips Gate, `delegate.py:129` has no remaining check — keep that as the escape); or a stated one-job exception the human types. `--tier` cannot help when every tier in Range is gated.

## Setup as a re-runnable, surgical operation

Today a rerun walks start → harnesses → carry → T4..T1 → review → routing → confirm (`setup_tui.py:533`). Catalog values are the defaults (`CLAUDE.md:23`). That is re-runnable only as a full pass. `--plain` is worse: it asks tier per lane (`setup.py:181`).

### Three verbs

1. **First catalog / periodic review.** The TUI, unchanged in page grammar. One decision per line. Confirm writes both global files (`setup.py:375`).
2. **Visual tier mapping.** The HTML page. It does not write `lanes.json`. It writes browser `localStorage` and Copy-as-lines (`CLAUDE.md:23`). The TUI `v` key and `setup.py --tiers-from` remain the apply path. Keep it that way: the page is an input device, the wizard is the writer.
3. **Surgical edit.** Proposed `catalog.py set` and proposed `setup.py --screen <start|carry|tierN|review|routing>`. One-lane tier, one class floor, Gate, Margin, meters on/off, without walking carry. `--plain` remains the non-TTY fallback for a full pass, not for surgery.

Adding a class is not a surgical flag. See §3.

### Discovery wrap

Remove `read_discovery`'s Node call from the default path (grok Finding 4). Keep `--discover-json` for fixtures (`setup.py:270`). `discover.discover` already returns `status: error` per harness (`discover.py:441`). Setup already turns a Python exception into a start-fact string (`setup.py:303`). Make `read_discovery` the same shape: never raise on a missing binary. Print `missing` / `error` and continue. `--no-discover` must skip both paths, not only the second.

### What the TUI keeps

Carry boxes, four tier pages, review order, routing table with the side panel (`setup_tui.py:1121`), clipboard paste, confirm. Policy helpers leave the file (carry/order → `bench.py`; tier-line apply → `catalog.py`, astra order step 8).

### What the HTML page does

Plot, drag tier lines, click-to-tier, Copy-as-lines, sensitivity display. It does not own Gate, Margin, class definitions, or metering on/off. Those are routing-page / `catalog.py set` work.

## Migration plan

Each step is one commit. "Pure" means no intended behavior change. Tests named below already exist unless marked proposed.

Reviews agree on: share cache path, drop unused `effort`, share rank formatting, one discovery, carry out of the TUI, one Gate, `meter_observations` for viewers, native record, test-surface cleanup.

They disagree on order. Astra starts with return-contract behavior, then meters, then native, then probes, then carry. Grok requires pure moves before behavior, and puts return/native late.

Pick grok's pure-then-behavior rule. The story's new behavior (meters switch, class guide, surgical setup) needs one Gate, not a fixed return parser. Defer astra steps 1, 4, 5, 6 (return, native, probe argv, probe grading) until after the routing path. They are real defects; they are not the classification/metering seam. Include astra's tier-line move and bench render once carry has a home.

1. **Share cache path.** Pure. Export `usage.get_cache_path`; `rank.load_cached_usage` and `report.CACHE` call it. Closes grok Finding 11 / astra Finding 1 cache-path part. Tests: `test_usage_reset.py`, `test_rank.py` missing-cache (`test_rank.py:832`), `test_report.py` limits.

2. **Drop `rank(..., effort=None)`.** Pure. Closes both reviews' unused-parameter note. Tests: `test_rank.py`.

3. **Share rank formatting.** Pure. One function prints the class header and rows; delete `delegate._print_rank_output`. Closes grok Finding 5 / astra Finding 8. Tests: `test_rank.py` CLI, `test_dispatch.py` `run --dry-run`.

4. **One discovery on setup.** Pure relative to Python `discover()`. Stop calling `discover.mjs` by default; `--no-discover` skips all discovery; per-harness errors continue. Closes grok Finding 4 / astra Leak on setup. Tests: `test_setup.py`, `test_discover.py`.

5. **Carry/order out of the TUI.** Pure move. Functions go to `bench.py`; `setup_tui` and `bench_page` import them; stop parsing `" wins on "`. Distinct unavailable vs empty proposal. Closes grok Finding 1 / astra Finding 2. Tests: `test_setup_tui.py` domination, `test_bench_page.py`, add structured-kind cases to `test_bench.py`.

6. **One Gate and one observation reader.** Behavior. Ranking eligibility ignores `usage.status`; `limits --eligible` and statusline use `meter_observations` + `routing.gate`. Closes grok Findings 2–3 / astra Finding 1. Tests: `test_rank.py` case 8 (`test_rank.py:363`) and case 21 (`test_rank.py:858`); proposed equality / project-Gate / malformed-cache cases in `test_report.py`.

7. **Meter acquisition.** Pure relative to probe math. One cached-only path, one refresh path; no event on cache read; no probe for `rank.py tiers`. Closes astra order step 3. Tests: `test_usage_reset.py`, `test_rank.py` tiers, `test_report.py`.

8. **Metering on/off.** Behavior. Add `routing.meters` boolean, default true; off feeds `{}` to `rank_range` and skips probes. Closes the story switch. Tests: proposed `test_rank.py` meters-off = missing-cache rows; `test_catalog.py` accepts the new key; `test_setup_tui.py` routing page.

9. **STOP stays exit 1; skill asks.** Behavior in prose only. `SKILL.md` tells the session to ask after STOP. No script change if step 6 kept the contract. Tests: existing `test_rank.py:362`; proposed skill-fixture not required.

10. **`assets/classes.md` plus check-guide.** Behavior for the orchestrator; code only validates headings. Move `SKILL.md:12` into the guide; delete the `--tier 3` scout example. Closes the classification gap. Tests: proposed heading-set checks in `test_catalog.py`.

11. **Surgical catalog writes.** Behavior. Proposed `catalog.py set` and `setup.py --screen`. TUI still does the full review. Tests: `test_catalog.py` round-trip one tier and one Gate; `test_setup.py` `--screen routing` does not rewrite carry.

12. **Tier-line apply in catalog.** Pure move of `apply_tier_lines_to_doc` / order write toward `catalog.py`. Closes astra order step 8. Tests: `test_setup.py`, `test_setup_tui.py`, `test_bench_page.py`.

13. **Bench collect without a subprocess.** Pure. `--plain` calls `collect` + Markdown render; collection stops building a discarded table. Closes astra Finding 7. Tests: `test_bench.py`, `test_setup.py`.

14. **Native handoff record.** Behavior. Branch before ADS; write Run dir + structured native line; courier rejects native. Closes astra Finding 4 / grok Finding 6. Tests: `test_dispatch.py` native, `test_catalog.py` agent correspondence.

15. **Return interpretation.** Behavior. Separate map from persist; keep null lines; apply limits after dispatcher notices. Closes astra Finding 3. Tests: `test_dispatch.py`.

16. **Ledger read API; meter identity.** Behavior/cleanup. `events` gains a scan; statusline uses it. Observation key stops overloading `lane` (grok Findings 7–9). Tests: `test_events.py`, `test_report.py`, `test_usage_reset.py`, `test_rank.py`.

17. **Test surface.** Pure. Public `handle/view/result` and `layout_lines/overlay` only. Closes astra Finding 9 / grok Finding 8 / both order last steps. Tests: the same files, green.

18. **Probe selection/grading.** Behavior, after dispatch is honest. Out of the story path; do not skip forever. Closes astra Findings 5–6 / grok Finding 10. Tests: `test_browser_probes.py`, `test_dispatch.py`.

Do not mix a pure move with a meters-off flag. Do not open `CLASSES` in the same commit as `classes.md`.

## Where the story is wrong or premature

**Configurable tier count.** Four tiers are the capability scale the wizard, the page, ranking, and the dashboard already share (`rank.py:286`, `setup_tui.py:14`). A fifth tier is a product change, not a refactor. Keep 1–4. Classes already select a Range inside that scale.

**Classification picks a lane.** Classification picks a class. `rank_range` picks a lane. Mixing them would put judgment into the sort. Keep the split the story also stated: judgment in Markdown, tiers deterministic.

**A Python (or HTML) classifier.** Scoring briefs in code would freeze today's five coding classes and fight the orchestrator. The file the agent loads is the right abstraction. Validate it; do not execute it.

**Open class registry in setup.** `catalog.py:506` rejects unknown names on purpose. Knowledge-work classes need names, floors, and a guide section designed together. Do not add a wizard field that writes a class the ranker cannot rank.

**Metering off as Gate 0 or as "ignore remaining but keep Pace".** Off means no probe, no Gate veto, no steal. Anything else is a different policy.

**Interactive ask inside `rank.py`.** The script is a filter. STOP + exit 1 is the signal. The session asks. An interactive ranker breaks Workflow/courier callers (`courier.md:3`).

**Containers, and dispatch-created worktrees.** Relays already sandbox read-only runs (`delegate.py:451`). `--write` is the blast radius and must pre-exist (`delegate.py:199`, `SKILL.md:28`). The orchestrator (or the human) makes the worktree. A container runtime is a new product.

**npx as the way this skill is installed.** This catalog is stowed from a public repo (`Makefile:74`, `Makefile:103`). `npx skills add` is how *other* skills land (`Makefile:81`) and how ADS was specified (`docs/superpowers/specs/2026-09-08-delegate-redesign.md:142`). Cloning the skill without `lanes.json` / `routing.json` yields a ranker with no catalog. Keep stow. If a public skill listing is needed later, it must install or generate those two files.

**`/delegate-setup` as a second skill.** `/delegate setup` already runs `setup.py` (`SKILL.md:18`). A typed-only alias is fine. A second wizard is not.

**Herdr as the owner of order, Gate, or class definitions.** The dashboard spec forbids that (`docs/superpowers/specs/2026-09-13-delegate-dashboard-plugin.md:77`). Project order already hot-loads through `load_catalog`. Build a production pane later on that seam. Do not put policy writes in the plugin.

**HTML as the setup UI.** The page is the first input for tier lines. It cannot confirm-write the stowed catalog without breaking the symlink rule (`Makefile:103`). TUI/CLI remain the writers.

**Benchmarks assign tiers.** Settled: the human sets Tier; the board assists (`docs/superpowers/specs/2026-09-08-delegate-redesign.md:24`). The carry rule may propose a lane off. It must not write a tier.

**Always-on metering with "warn when a tier is empty".** The current rule is Range-empty, not Tier-empty. A class with floor 2 still runs if tier 2 is gated and tier 3 is not. Warn only when the whole Range has no Pick.

## Open decisions for the maintainer

1. **Closed `CLASSES` tuple vs open names in `routing.json`.** Recommendation: keep the tuple until a concrete extra class exists. Opening the set is a later commit, after `classes.md` is in use.

2. **Meters-off encoding.** Recommendation: explicit `meters: true|false`, default true when absent. Reject overloading `gate`.

3. **Named dispatch vs Gate.** Today named dispatch skips Gate (`delegate.py:129`). Recommendation: keep the skip; it is the STOP escape. If that is too sharp, add an explicit `--force` later rather than silently gating named lanes.

4. **Guide duplication of floor/ceiling numbers.** Recommendation: no numbers in `classes.md`. The rank header is live. Duplicating numbers is how `SKILL.md:35` went stale.

5. **Surgical CLI home.** Recommendation: `catalog.py set` for one-field writes; `setup.py --screen` to jump the TUI. Do not teach `--plain` new mini-wizards.

6. **When to build a production Herdr pane.** Recommendation: after steps 1–8. Observation already works via `load_catalog` + `tier_leaders`. The prototype answered the host question (`CLAUDE.md:14`). A pane is presentation, not a skill refactor.
