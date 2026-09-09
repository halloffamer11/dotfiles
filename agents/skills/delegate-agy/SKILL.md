---
name: delegate-agy
description: Typed-only. Run one brief on a named Antigravity lane or model through the delegate dispatcher, with no meter read and no ranking.
disable-model-invocation: true
---

# /delegate-agy (--lane <name> | --model <slug>) </abs/brief.md> [--write </abs/worktree>]

Resolve the lane against the catalog and dispatch it. No meter is read, nothing is ranked. Shared logic lives in `delegate.py`; this file only names the harness.

    python3 ~/.claude/skills/delegate/delegate.py dispatch --harness agy --lane <name> --brief </abs/brief.md> --cwd "$PWD" [--write </abs/worktree>]

`--model <slug>` in place of `--lane` resolves the model to its lane on this harness; an unknown model fails with the lanes on this harness listed. Antigravity carries effort in the model name, so `--effort` is ignored with a note. A missing `agy` binary fails before dispatch with a plain message. Read-only runs have no terminal on this harness. Run in the background when the lane is slow; read `<run>/return.json` when notified.

Arguments typed after the skill name: `$ARGUMENTS`.
