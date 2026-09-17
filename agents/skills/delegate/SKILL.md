---
name: delegate
description: Route worker-shaped work (implementation with a spec, verification, review, scouting, mechanical transforms) to an external worker on one lane, picked by tier and remaining subscription usage. Use before any Agent, Workflow, or teammate spawn, and to answer questions about remaining usage. Not for work that needs this session's live context.
---

# Delegate

The session plans, adjudicates, and synthesizes. Worker-shaped work goes out on a **lane**: one (harness, model, effort) tuple that drains one subscription **meter**. `/delegate` is the model-invocable entry point that reads meters and ranks lanes. The typed-only wrappers `/delegate-claude`, `/delegate-codex`, `/delegate-agy`, `/delegate-grok` run one harness with prose-constrained ranking.

## Terms

Every term this skill uses (harness, lane, meter, class, tier, floor, ceiling, range, pace, gate, margin, native lane, disposable browser, agent profile, and the rest) is defined once in `~/dotfiles/CONTEXT.md`. Read it before the first run in a session. Class intent, signals, examples, counter-examples, and when to raise live in `assets/classes.md`.

## Files

- `~/.config/delegate/lanes.json`: meters and lanes (harness, model, effort, meter, meter weight, timeout, price, tier, basis; optional `enabled`, and `published_as` — the names benchmark sources print for this lane's model, e.g. `"published_as": ["Fable 5.1"]` on a `claude-fable-5-1` lane, needed only where case and separators alone do not bridge the two). Global only.
- `~/.config/delegate/routing.json`: `classes` (floor and ceiling per class), `margin`, `gate`. A project overrides any key at `<git-root>/.delegate/routing.json`; `classes` merges per class and per key. Floor and Ceiling stay here, never in the Class guide.
- `assets/classes.md`: Class judgment (intent, signals, examples, counter-examples, when to raise `--tier` inside the live Range). A project may overlay matching `##` Class sections at `<git-root>/.delegate/classes.md`; the overlay cannot add a Class or declare Floor or Ceiling. `python3 ~/.claude/skills/delegate/scripts/catalog.py check-guide [file] [--overlay]` validates headings against the closed Class set.
- Both JSON files are strict JSON, validated on read with a plain-language message naming the field and the rule, formatted on write, and accept `note` fields anywhere. `python3 ~/.claude/skills/delegate/scripts/catalog.py show` prints the effective catalog for the current directory; `scripts/catalog.py check <file>` validates one file. The starting catalog ships in `assets/samples/`; `/delegate setup` is the wizard that builds or revises it (direct command: `python3 ~/.claude/skills/delegate/scripts/setup.py`). When `$ARGUMENTS` asks for setup (e.g. `/delegate setup`), run `python3 ~/.claude/skills/delegate/scripts/setup.py`.

## Focused catalog changes

Use `scripts/catalog.py set FIELD JSON_VALUE --scope global|project`,
`range CLASS FLOOR CEILING --scope global|project`, or
`order LANE POSITION --scope global|project`. Tier uses `lanes.<lane>.tier`
(global only); routing fields are `routing.gate` and `routing.margin`.
Order is one-based among carried Lanes in the same Tier. All accept `--cwd`
and `--config-dir`.

Each command first returns a JSON preview: source files and resolved targets,
changed fields, values, Picks and exact-Tier leaders using cached observations.
Apply the same operation with `--apply --expect REVISION` from that preview.
An explicit request for the desired value authorizes preview and apply; do not
ask again. A source change requires a fresh preview. Apply preserves stow links
and writes only the chosen source document. Focused edits preserve other choices;
bulk tier-line imports still turn omitted carried Lanes off.

## Model evidence

Use `scripts/bench.py model MODEL --effort-rows FILE` for a read-only inspection;
repeat `--effort-rows` for accepted datasets and use `--json` for the same records
as JSON. `--epoch-csv FILE` accepts a local snapshot. This command fetches nothing.
It separates Model-family evidence from rows attributable to a Lane’s exact
effort, shows unresolved identity and absent rows, and keeps board versions and
source cost bases separate. Standing is within the loaded snapshot. Research
links remain references until their rows pass the acceptance pipeline.

## 1. Classify and write the brief

Read CONTEXT.md terms if this session has not. Read `assets/classes.md`. If the git root has `.delegate/classes.md`, use each of its `##` Class sections in place of the matching section from the skill guide. Pick exactly one Class; when two seem to fit, the counter-examples decide. Named dispatch skips Range and still writes the Class on the prompt.

Write a Markdown brief with two headings, nothing else: `# Objective` and `# Definition of done`. Name every file the worker must read. Put the gate commands the worker must run in the definition of done. Save it under the session scratchpad with an absolute path.

## 2. Run

    python3 ~/.claude/skills/delegate/scripts/delegate.py run <class> --brief </abs/brief.md> --cwd </abs/project> [--write </abs/worktree>] [--tier <n>] [--no-leash] [--dry-run]

Run it with `run_in_background` so the session keeps working; the notification carries the `delegate:` line with `run=<dir>`, and `<dir>/return.json` is the result. The command prints the ordered lanes with one reason each, then dispatches the pick. `--dry-run` stops after the print. `--tier <n>` raises the floor for this job (must stay within the class range); `dispatch` keeps `--effort`. `--no-leash` drops the tool-call leash in the prompt; set it when the job is large. `--write` is the only way a worker gets a shell and edits; the worktree is the blast radius, never a primary checkout.

A native pick prints `delegate: native …`; spawn the named agent with the Agent tool, with `subagent_type` set to the agent and `run_in_background`, and the prompt `Read <prompt> and follow it.`; its final message is the return claim; log it with `report.py log --lane <lane> --secs <s> --status <status> --work … --verdict … --class …`.

The rule: each class has a floor and a ceiling in `routing.json`. Eligible lanes are enabled, have `floor <= tier <= ceiling`, meter remaining at or above `gate`, and the harness CLI on PATH; sort by tier ascending, then `order` ascending (the lane's place inside its tier, which Orin sets on the setup wizard's review page; a lane without `order` sorts after every lane with one), then pace descending, then lane name ascending to break a tie; the first is the pick unless a later lane's pace beats the pick's pace by `margin`, which steals the job. Because `order` sorts ahead of pace, a steal can happen inside a tier: a lane lower in the order runs when its meter is well ahead of the pick's, which is the load balance. A catalog with no `order` ranks as before, where pace orders a tier and a steal only crosses tiers (ticket 28). A meter whose probe is unknown sorts last and never blocks. When nothing is eligible the command stops with the reasons and starts nothing. When the output starts with `STOP: no lane eligible for <class>`, the process has already exited 1. Show those veto reasons to the user and ask which to do: abort, named dispatch to a lane they name (`dispatch --lane`), or a one-job exception they state in prose. Wait for that answer before starting a worker. `--tier` cannot admit a Range whose every tier is gated. The script does not prompt. Meters are probed at run start and run finish.

The floor is the default; pass `--tier <n>` when the job needs judgment, using a value inside the Range the rank header prints (`floor=` `ceiling=`). `assets/classes.md` says when to raise.

When the user specifies prose constraints in the surrounding request (a harness to prefer or avoid, models to exclude, a ceiling on effort), apply them: read the `rank.py <class> --json` rows, drop the ones the constraints exclude, and dispatch the surviving pick with `delegate.py dispatch --lane <name> --class <class>`. Do not repurpose `--harnesses` as a filter — it declares which CLIs are present, so using it to exclude a harness makes the ranker report `cli absent` for a CLI that is installed. Stop and name the constraint if all lanes are eliminated. Ranking is otherwise unchanged — the class range, pace order, and pace margin still decide.

To constrain a specific harness with plain-language instructions, type one of the wrappers yourself, for example `/delegate-codex dont use astra, maximum effort medium`. They are typed-only; the model never invokes them.

## 3. Verify and log

`return.json` is a claim. `status` other than `done` is not a success; `blocked` carries its reason in `deliverable`. Read the evidence, diff `changed_files`, run the checks yourself. Then log the adjudication with the thread from the `delegate-metrics:` line:

    python3 ~/.claude/skills/delegate/scripts/report.py log --work "<2-4 words>" --run <run-dir> --verdict clean|findings|partial|failed [--outcome "<phrase>"] --class <class>

`--run` takes lane, seconds, status, thread, and the token cost from the run directory; `report.py cost <run-dir>` prints one run's cost breakdown, or `unmeasured` when the relay reported no tokens (Codex today).

`report.py limits` prints remaining quota per meter; `report.py runs` prints recent adjudicated dispatches. Print these, never a hand-built table.

## Workflow callers

A Workflow script has no shell primitive. The `courier` agent is an optional wrapper for that case only: it runs the same `delegate.py` command and relays `return.json`. Nothing on the main path needs it.

## Health

`python3 tests/test_catalog.py`, `tests/test_rank.py`, `tests/test_dispatch.py`, `tests/test_browser_probes.py`, `tests/test_events.py`, `tests/test_report.py`, `tests/test_usage_reset.py`, `tests/test_bench.py`, `tests/test_setup.py`, `tests/test_setup_tui.py` after touching the matching file. `python3 scripts/browser_probes.py` runs the disposable and agent-profile browser probes across all harnesses (`--dry-run` to preview commands); live runs send real workers and spend quota. A native lane's rows read `NATIVE`: dispatch that lane with the probe brief yourself and spawn the agent its native line names. A pass counts only with evidence the browser was used, such as Playwright's page snapshots in the probe's working directory; the nonce alone can be copied from the brief. `sh scripts/ads.sh check` confirms the pinned relays; `sh scripts/ads.sh install` restores them. A model slug that stops resolving is edited in `lanes.json`; `agy models`, `codex debug models`, `grok models` list the current ones.
