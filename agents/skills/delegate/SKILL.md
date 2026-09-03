---
name: delegate
description: Route worker-shaped work (implementation with a spec, verification, review, scouting, mechanical transforms) to an external agent CLI — Antigravity, Codex, or Grok — through one dispatcher, and pick the lane by a deterministic read of remaining subscription usage. Use before any Agent, Workflow, or teammate spawn (rank.py <class>) and to answer questions about remaining usage (usage.py --pretty). Not for work that needs this session's live context.
---

# Delegate

The session plans, adjudicates, and synthesizes. Worker-shaped work goes out through a lane: one model on one harness on one usage meter. Rows live in `lanes.tsv`; the command per harness lives in `dispatch.sh`; both are proven by `tests/smoke.sh`.

## 1. Classify, then rank
Classes: `impl` (implementation with a spec), `verify` (refute, check, critic), `review` (independent review of a diff; reviewer family differs from author), `hard-impl`, `scout` (find, ground, summarize), `mechanical` (renames, transforms, extraction).

    python3 ~/.claude/skills/delegate/rank.py <class>

Eligible lanes, best first: highest pace wins (weekly remaining divided by the fraction of the weekly cycle still to run, so quota that would expire unspent is used first), lanes under 10% are skipped. Take #1. A lower lane needs a one-line reason. Record: `delegate: <class> → <lane>`.

## 2. Write the brief
A Markdown file with two headings, nothing else: `# Objective` and `# Definition of done`. Name every file the child must read. Put the gate commands the child must run (tests, build) in the definition of done. Save it under the session scratchpad with an absolute path.

## 3. Dispatch
Through the courier, so the child's output never enters this context. Never pass `model`; the courier is Haiku and only relays.

    Agent subagent_type=courier: lane <lane>, brief </abs/path/brief.md>, cwd </abs/dir>[, write </abs/worktree>][, effort high]

Or inline for a short answer: `sh ~/.claude/skills/delegate/dispatch.sh <lane> <brief> <out.json> --cwd <dir> [--write <worktree>] [--effort low|medium|high]`. Slow lanes (sol@codex at high) run with `run_in_background`.

Read-only lanes have file tools and no shell. Write lanes run full-auto (edits, shell, gate commands) inside the git worktree named by `--write`, and only when the user authorized implementation. The worktree is the blast radius: never point `--write` at a primary checkout.

## 4. Verify
The out file is a claim. `status` other than `done` is not a success. Read the evidence, diff `changed_files`, run the checks. A Claude worker (Sonnet or Opus via Agent) is the exception and needs `why-claude: <reason>` in its prompt; the gate hook denies it otherwise.

## Health
`sh tests/smoke.sh` after any CLI update, or when a lane misbehaves: every lane must PASS. `python3 tests/test_extract.py` after touching extract.py. A slug that stops resolving is edited in `lanes.tsv`; `agy models`, `codex debug models`, `grok models` list the current ones.
