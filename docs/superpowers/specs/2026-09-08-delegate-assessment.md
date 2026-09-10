# Delegate skill: assessment and the two paths on the block

Date: 2026-09-08. Author: toolsmith session (Fable) with Orin. Status: **superseded 2026-09-08 by `2026-09-08-delegate-redesign.md`; neither option was taken.**
Next step: a grilling session (`mattpocock-skills:grilling`; Orin called it "grill-with-docs") on simplicity and execution, then a design spec for the chosen path.

Published assessment page: https://claude.ai/code/artifact/3bf1bc04-733e-436d-ba06-751edbb9f1c3
Provenance (scout briefs and results, fetched reference docs, report HTML): `~/.cache/delegate/assessment-2026-09-08/`

## 1. What each thing is today

### The current delegate skill (dotfiles `agents/skills/delegate`, branch `delegate-rebuild`)

A **routing layer** with a thin dispatcher. When the session dispatches work:

1. `rank.py <class>` reads `lanes.tsv` (lane, harness, model slug, work classes) and `usage.py` (remaining quota per meter) and prints eligible lanes, best first, by weekly pace.
2. The session writes a brief file (Objective, Definition of done) and spawns the `courier` sub-agent (Haiku, 2 turns, Bash only).
3. The courier runs `dispatch.sh <lane> <brief> <out.json>` in the foreground with the maximum Bash timeout (10 min).
4. `dispatch.sh` assembles a prompt (preamble + brief), runs one fixed command per harness (`codex exec`, `agy --print`, `grok --prompt-file`), and `extract.py` reduces the CLI envelope to the return schema (status done/partial/blocked, deliverable, evidence, open_questions, changed_files). Events go to `~/.cache/delegate/ledger.jsonl`.
5. The courier relays the out file verbatim. The session adjudicates and logs with `report.py log`.

Hooks: `delegate-gate.py` (PreToolUse on Agent|Workflow) denies Claude-model workers without a `why-claude:` reason; `delegate-ledger.py` and `delegate-usage-prime.sh` feed the ledger. A Rust TUI (`monitor/`) reads the ledger.

Unique asset: **quota-paced routing** (usage.py meters, pace formula, rank.py). Nobody else has built this.

### amElnagdy/delegate-skills (github.com/amElnagdy/delegate-skills, b781ee2, 2026-08-31)

A **dispatch layer** with no routing. 17 skills, one per harness CLI (codex-delegate, agy-delegate, grok-delegate, claude-delegate, cursor-delegate, ...), plus `delegate-setup`, which discovers installed CLIs and writes a fleet config (`~/.config/delegate-skills/config.json`, per-repo `.delegate/config.json`): named lanes such as `feature`, `tests`, `ui`, each bound to one implementer and optional dials (model, effort, timeout, readOnly, sandbox). Install any subset: `npx skills add amElnagdy/delegate-skills --skill codex-delegate`.

When the orchestrator dispatches:

1. It writes a brief file (their template: goal, current state, change, leave untouched, gate commands, report contract).
2. It runs `node <skill>/scripts/relay.mjs --brief brief.txt --cd <repo> [--lane <name> | --model <slug>] [--read-only] [--timeout 2h]` in a background shell.
3. The relay (720 lines of Node per harness, 80 to 90 percent shared code pinned by a parity test) probes the CLI version, spawns the CLI in its own process group, arms a watchdog (SIGTERM then SIGKILL), captures the event stream, and writes a per-run directory: `brief.txt`, `events.jsonl`, `final.txt`, `stderr.txt`, `result.json` (status completed/failed/timeout/aborted/<cli>_unavailable, exitCode, finalMessage, touchedFiles, readOnlyViolation, thread id for resume).
4. The orchestrator polls for `result.json`, re-runs the gates, reads the diff, and commits itself. Rework goes back with `--session <id>`.

Deliberately absent: quota or usage awareness, ranking among lanes, sub-agent integration, structured output schema. Tests run against a fake CLI on Linux and Windows in CI; no live CLI runs.

## 2. The differences that matter

| | Current delegate | amElnagdy |
|---|---|---|
| Picks the lane | rank.py by remaining quota and class | You do, by name or by skill |
| Keeps worker output out of session context | Yes (courier relays a file) | No (orchestrator reads result.json itself; same effect if it reads only the file) |
| Run timeout enforced | agy only; Codex and Grok unbounded | All harnesses, with process-tree kill |
| Survives a run longer than 10 min | No: courier is time-boxed at 10 min | Yes: background shell plus poll |
| Failure states | done/partial/blocked, reason often lost | 5 statuses plus named error text, full stderr kept |
| Structured return | JSON schema enforced by the CLI | Free text finalMessage |
| Resume a worker | No | Yes |
| Read-only check after the run | No | Git fingerprint tripwire (has a subdirectory bug) |
| New model in catalog | Edit one row; nothing warns you | Edit config or pass --model; nothing warns you |
| Dependencies | sh, python3 | Node 18+, git |
| Portability | Claude Code only | Any agent with a shell |

## 3. The problems found (ledger of 74 dispatches since 2026-09-03)

- Courier 10 min cap vs runs that take longer: 13 of 74 exceeded it, 9 of 18 Grok runs. This is the "courier timeout" failure.
- `dispatch.sh` line 37 computes `timeout_s`; only agy receives it. Two Grok runs ended by signal at 47 min.
- Codex write runs (3 on sol, 0 done) failed on sandbox limits (Vitest temp files EPERM, loopback refused), not syntax.
- agy: 48 of 50 done. Its problems are quality (fabricated citations in three impl briefs) and one silent empty response. The empty case is exactly what the upstream agy relay detects.
- The courier once rewrote a brief and removed the original file (run ledger). An LLM relay is not deterministic.
- Evidence is ephemeral: raw and error files in system temp, results in session scratchpads. Nothing from last week survives.
- `references/routing.md` and the gate hook docstring describe `lanes.json` and `scripts/rank.py`, which no longer exist.
- `DELEGATE_BALANCE` is honoured by the hook and `probe.sh` but ignored by `rank.py` (always sorts by pace).
- Mode 1 (skill not used unless invoked) is blocked by the global `~/.claude/CLAUDE.md` Delegation section and the PreToolUse hook, not by the skill.

## 4. Option 1: keep routing, harden dispatch, borrow mechanisms

**Merged result, files after:** the same directory. `lanes.tsv`, `rank.py`, `usage.py`, `report.py`, `courier.md`, hooks unchanged in role. `dispatch.sh` grows (or becomes `dispatch.py`) with: enforced timeout and process-group kill (est. 55 to 85 lines), per-run result directory under `~/.cache/delegate/runs/<thread>/` with brief, raw, stderr, result (40 to 65), version preflight (30 to 45), agy silent no-op detection, the five status values as the failure taxonomy, and a catalog drift check (`lanes.tsv` slugs vs `codex debug models` / `agy models` / `grok models`, ~30 lines). `courier.md` changes to background the dispatch and poll for the result file, so the 10 min cap stops mattering. `rank.py` gains the `DELEGATE_BALANCE` switch (off = table order). `routing.md` rewritten or deleted.

**What a dispatch does after:** same five steps as today; step 3 backgrounds; step 4 writes a run directory and always ends in a named status.

**Gain:** you keep every unique piece (pace routing, courier, hooks, TUI, output schema), stay on sh/python, and own the tests. **Lose:** you keep maintaining harness quirks yourself as CLIs change. **Effort:** two to three evenings of Orin's own edits plus smoke runs. Estimates are Astra's from the upstream source, not measured.

## 5. Option 2: keep routing, use their relays as the dispatch backend

**Merged result, files after:** `lanes.tsv`, `rank.py`, `usage.py`, `report.py`, `courier.md`, hooks unchanged. Three upstream skills installed unmodified and pinned to a commit: `codex-delegate`, `agy-delegate`, `grok-delegate` (their SKILL.md descriptions enter every session's skill list). `dispatch.sh` shrinks to: pick the relay for the harness, call `node relay.mjs --brief ... --cd ... --model <slug> [--read-only] --timeout <from effort>`, wait, read `result.json`, map it to your return schema (`extract.py` parses the last JSON object out of `finalMessage`, which the brief must still request because their relays enforce no schema).

**What a dispatch does after:** step 4 is their relay; the run directory, watchdog, preflight, taxonomy, resume, and tripwire come for free; your ledger events wrap it.

**Gain:** hardened dispatch and their CI tracking CLI drift (a Codex stderr fix merged 2026-08-31). **Lose:** Node dependency; three 720-line scripts you do not own; no CLI-enforced output schema; their known agy subdirectory bug until fixed upstream; two layers to debug when a run fails. **Effort:** one evening to wire, then a live read-only trial on Codex and agy (Q1) to confirm their relays behave on this machine.

## 6. Fork amElnagdy and modify on top?

Position: **no fork. Pin, wrap, and send fixes upstream.**

- Their relays are deliberately standalone per skill with no shared module, and a parity test pins the shared 80 to 90 percent byte-for-byte across all 17. A local change to the shared code in one relay breaks parity unless you change all 17, and every upstream release touches that shared code. A fork would conflict on every merge.
- The changes you would want (schema-enforced output, quota routing, courier) all live outside `relay.mjs`. Option 2 already keeps them outside. Nothing needs to be inside their code.
- Fixes you find (the agy cwd join bug is one) go upstream as a PR. The repo has a contributing guide and a claim-implementer issue template; it merged an external PR on 2026-08-31.
- Pin the installed commit and re-run `npx skills add` to update on your schedule. Whether the skills CLI has an update command was not verified; check `npx skills --help` before relying on it.

A fork is justified only if upstream rejects a change you need inside the relay. None is known today.

## 7. Open for the grilling session

- Is Node an acceptable dependency on this machine and the work Mac?
- Does the courier stay an LLM, or become a hook-side script? (Deterministic relay would remove the "courier rewrote the brief" class.)
- Mode 1 needs the global CLAUDE.md rule and the gate hook to be conditional. Which switch: env var, or move the rule into SKILL.md?
- Astra lane: add `astra@codex	codex	gpt-6-astra	review,hard-impl	frontier; catalog 2026-09-08` to lanes.tsv (tabs). Scout class left out on purpose.
- Q1 from the toolsmith session: run a live read-only trial of upstream `codex-delegate` and `agy-delegate` before choosing Option 2.
- Codex write lanes: pass sandbox config for temp writes and loopback so tests can run (see Codex config reference in provenance docs).
