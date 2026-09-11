---
name: delegate
description: Route worker-shaped work (implementation with a spec, verification, review, scouting, mechanical transforms) to an external worker on one lane, picked by tier and remaining subscription usage. Use before any Agent, Workflow, or teammate spawn, and to answer questions about remaining usage. Not for work that needs this session's live context.
---

# Delegate

The session plans, adjudicates, and synthesizes. Worker-shaped work goes out on a **lane**: one (harness, model, effort) tuple that drains one subscription **meter**. `/delegate` is the model-invocable entry point that reads meters and ranks lanes. The typed-only wrappers `/delegate-claude`, `/delegate-codex`, `/delegate-agy`, `/delegate-grok` run one harness with prose-constrained ranking.

## Terms

Every term this skill uses (harness, lane, meter, class, tier, floor, ceiling, range, pace, gate, margin, native lane, disposable browser, agent profile, and the rest) is defined once in `~/dotfiles/CONTEXT.md`. Read it before the first run in a session. The classes: `scout` (find, ground, summarize), `mechanical` (renames, transforms, extraction), `impl` (implementation with a spec), `review` (independent review of a diff; reviewer family differs from author), `hard-impl`.

## Files

- `~/.config/delegate/lanes.json`: meters and lanes (harness, model, effort, meter, meter weight, timeout, price, tier, basis; optional `enabled`, and `published_as` — the names benchmark sources print for this lane's model, e.g. `"published_as": ["Fable 5.1"]` on a `claude-fable-5-1` lane, needed only where case and separators alone do not bridge the two). Global only.
- `~/.config/delegate/routing.json`: `classes` (floor and ceiling per class), `margin`, `gate`. A project overrides any key at `<git-root>/.delegate/routing.json`; `classes` merges per class and per key.
- Both are strict JSON, validated on read with a plain-language message naming the field and the rule, formatted on write, and accept `note` fields anywhere. `python3 ~/.claude/skills/delegate/scripts/catalog.py show` prints the effective catalog for the current directory; `scripts/catalog.py check <file>` validates one file. The starting catalog ships in `assets/samples/`; `/delegate setup` is the wizard that builds or revises it (direct command: `python3 ~/.claude/skills/delegate/scripts/setup.py`). When `$ARGUMENTS` asks for setup (e.g. `/delegate setup`), run `python3 ~/.claude/skills/delegate/scripts/setup.py`.

## 1. Classify and write the brief

Pick the class. Write a Markdown brief with two headings, nothing else: `# Objective` and `# Definition of done`. Name every file the worker must read. Put the gate commands the worker must run in the definition of done. Save it under the session scratchpad with an absolute path.

## 2. Run

    python3 ~/.claude/skills/delegate/scripts/delegate.py run <class> --brief </abs/brief.md> --cwd </abs/project> [--write </abs/worktree>] [--tier <n>] [--no-leash] [--dry-run]

Run it with `run_in_background` so the session keeps working; the notification carries the `delegate:` line with `run=<dir>`, and `<dir>/return.json` is the result. The command prints the ordered lanes with one reason each, then dispatches the pick. `--dry-run` stops after the print. `--tier <n>` raises the floor for this job (must stay within the class range); `dispatch` keeps `--effort`. `--no-leash` drops the tool-call leash in the prompt; set it when the job is large. `--write` is the only way a worker gets a shell and edits; the worktree is the blast radius, never a primary checkout.

A native pick prints `delegate: native …`; spawn the named agent with the Agent tool, with `subagent_type` set to the agent and `run_in_background`, and the prompt `Read <prompt> and follow it.`; its final message is the return claim; log it with `report.py log --lane <lane> --secs <s> --status <status> --work … --verdict … --class …`.

The rule: each class has a floor and a ceiling in `routing.json`. Eligible lanes are enabled, have `floor <= tier <= ceiling`, meter remaining at or above `gate`, and the harness CLI on PATH; sort by tier ascending, pace descending, then lane name ascending to break a tie; the first is the pick unless a later lane's pace beats the pick's pace by `margin`, which steals the job. Because pace already orders lanes inside a tier, a steal only ever crosses tiers. A meter whose probe is unknown sorts last and never blocks. When nothing is eligible the command stops with the reasons and starts nothing. Meters are probed at run start and run finish.

The floor is the default; pass `--tier <n>` when the job needs judgment. Example: a scout that finds a file gets no flag; a scout that judges which of the given web pages are relevant gets `--tier 3`.

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
