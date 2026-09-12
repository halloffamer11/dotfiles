---
name: delegate-agy
description: Typed-only. Run one brief on Antigravity through the delegate dispatcher, with ranking constrained by prose.
disable-model-invocation: true
argument-hint: "[plain-language constraints]"
---

# /delegate-agy

Typing `/delegate-agy` means *use the Antigravity harness*; which lane inside it is your judgement constrained by the user's plain words in `$ARGUMENTS`.

Resolve the lane using the existing ranker:

    python3 ~/.claude/skills/delegate/scripts/rank.py <class> --harnesses agy --json

This returns `{"class", "floor", "ceiling", "margin", "gate", "pick", "rows": [...]}` with `lane`, `model`, `effort`, `tier`, `pace`, `eligible`, and `reason` on each row.

1. Filter the rows by applying the user's plain-language constraints:
   - **Exclusions**: drop any model or lane the user asked to avoid or exclude.
   - **Effort cap**: a phrase like "maximum effort medium" means the chosen lane's `effort` must be at or below `medium` on the ordered scale `low < medium < high < xhigh`. Filter the ranked rows by their `effort` field. Antigravity carries effort in the model name, so `--effort` is ignored with a note; select effort via the lane.
   - Consider only `eligible: true` rows.
2. Select the top surviving row.
3. If constraints eliminate every lane, **STOP immediately** and name the constraint that did it. Falling back to a lane the user excluded is worse than not dispatching; say so clearly and do not dispatch.
4. State the pick and the reason in one line before dispatching.
5. Dispatch the survivor:

    python3 ~/.claude/skills/delegate/scripts/delegate.py dispatch --harness agy --lane <name> --class <class> --brief </abs/brief.md> --cwd "$PWD" [--write </abs/worktree>]

Pass the same `<class>` you ranked with: the prompt's tool-call leash is chosen from it, and a dispatch with no class is leashed by default.

A missing `agy` binary fails before dispatch with a plain message. Read-only runs have no terminal on this harness. Run in the background when the lane is slow; read `<run>/return.json` when notified.

Arguments typed after the skill name: `$ARGUMENTS`.
