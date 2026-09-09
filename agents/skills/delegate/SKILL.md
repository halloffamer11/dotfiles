---
name: delegate
description: Route worker-shaped work (implementation with a spec, verification, review, scouting, mechanical transforms) to an external worker on one lane, picked by tier, trust, and remaining subscription usage. Use before any Agent, Workflow, or teammate spawn, and to answer questions about remaining usage. Not for work that needs this session's live context.
---

# Delegate

The session plans, adjudicates, and synthesizes. Worker-shaped work goes out on a **lane**: one (harness, model, effort) tuple that drains one subscription **meter**. `/delegate` is the only entry point that reads meters. The typed-only wrappers `/delegate-claude`, `/delegate-codex`, `/delegate-agy`, `/delegate-grok` run a named lane with no ranking.

## Terms

- **Harness**: a CLI that runs a worker: `claude`, `codex`, `agy`, `grok`.
- **Lane**: one (harness, model, effort) record in `lanes.json`, named `<model-effort>@<harness>`. Claude lanes are ordinary lanes.
- **Meter**: one subscription quota, probed by `usage.py`. A lane drains exactly one meter.
- **Class**: the kind of job. `scout` (find, ground, summarize), `mechanical` (renames, transforms, extraction), `impl` (implementation with a spec), `review` (independent review of a diff; reviewer family differs from author), `hard-impl`. Each class needs a **tier**.
- **Tier**: capability level 1 (lowest) to 4 (frontier), set by the human per lane after reading the benchmark ranking. **Trust**: the human's ordering of lanes inside a tier, 1 to 5, from experience. Nothing computes either.
- **Pace**: weekly remaining divided by the fraction of the weekly cycle still to run. 1.0 is spending evenly; above 1 the quota will expire unspent.
- **Brief**: the task file the session writes. **Run**: one relay invocation and its directory under `~/.cache/delegate/runs/`, never reused.

## Files

- `~/.config/delegate/lanes.json`: meters and lanes (harness, model, effort, meter, meter weight, timeout, price, tier, trust, basis). Global only.
- `~/.config/delegate/routing.json`: `classTier` (class to tier), `margin`, `gate`. A project overrides any key at `<git-root>/.delegate/routing.json`; `classTier` merges per class.
- Both are strict JSON, validated on read with a plain-language message naming the field and the rule, formatted on write, and accept `note` fields anywhere. `python3 ~/.claude/skills/delegate/scripts/catalog.py show` prints the effective catalog for the current directory; `scripts/catalog.py check <file>` validates one file. The starting catalog ships in `assets/samples/`; `/delegate setup` is the wizard that builds or revises it.

## 1. Classify and write the brief

Pick the class. Write a Markdown brief with two headings, nothing else: `# Objective` and `# Definition of done`. Name every file the worker must read. Put the gate commands the worker must run in the definition of done. Save it under the session scratchpad with an absolute path.

## 2. Run

    python3 ~/.claude/skills/delegate/scripts/delegate.py run <class> --brief </abs/brief.md> --cwd </abs/project> [--write </abs/worktree>] [--effort low|medium|high|xhigh] [--dry-run]

Run it with `run_in_background` so the session keeps working; the notification carries the `delegate:` line with `run=<dir>`, and `<dir>/return.json` is the result. The command prints the ordered lanes with one reason each, then dispatches the pick. `--dry-run` stops after the print. `--effort` overrides the lane's effort dial for this job only; the lane's tier is unchanged. `--write` is the only way a worker gets a shell and edits; the worktree is the blast radius, never a primary checkout.

The rule: `need = classTier[class]`; eligible lanes have `tier >= need`, meter remaining at or above `gate`, and the harness CLI on PATH; sort by tier ascending, trust descending, pace descending; the first is the pick unless a later lane's pace beats the pick's pace by `margin`, which steals the job. A meter whose probe is unknown sorts last and never blocks. When nothing is eligible the command stops with the reasons and starts nothing. Meters are probed at run start and run finish.

To run a specific lane without ranking, type one of the wrappers yourself, for example `/delegate-codex --lane terra-high@codex </abs/brief.md>`. They are typed-only; the model never invokes them.

## 3. Verify and log

`return.json` is a claim. `status` other than `done` is not a success; `blocked` carries its reason in `deliverable`. Read the evidence, diff `changed_files`, run the checks yourself. Then log the adjudication with the thread from the `delegate-metrics:` line:

    python3 ~/.claude/skills/delegate/scripts/report.py log --work "<2-4 words>" --run <run-dir> --verdict clean|findings|partial|failed [--outcome "<phrase>"] --class <class>

`--run` takes lane, seconds, status, thread, and the token cost from the run directory; `report.py cost <run-dir>` prints one run's cost breakdown, or `unmeasured` when the relay reported no tokens (Codex today).

`report.py limits` prints remaining quota per meter; `report.py runs` prints recent adjudicated dispatches. Print these, never a hand-built table.

## Workflow callers

A Workflow script has no shell primitive. The `courier` agent is an optional wrapper for that case only: it runs the same `delegate.py` command and relays `return.json`. Nothing on the main path needs it.

## Health

`python3 tests/test_catalog.py`, `tests/test_rank.py`, `tests/test_dispatch.py`, `tests/test_events.py`, `tests/test_report.py`, `tests/test_usage_reset.py`, `tests/test_bench.py`, `tests/test_setup.py`, `tests/test_setup_tui.py` after touching the matching file. `sh scripts/ads.sh check` confirms the pinned relays; `sh scripts/ads.sh install` restores them. A model slug that stops resolving is edited in `lanes.json`; `agy models`, `codex debug models`, `grok models` list the current ones.
