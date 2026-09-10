---
name: delegate-codex
description: Typed-only. Run one brief on a named Codex lane or model through the delegate dispatcher, with no meter read and no ranking.
disable-model-invocation: true
---

# /delegate-codex (--lane <name> | --model <slug>) </abs/brief.md> [--write </abs/worktree>] [--effort low|medium|high|xhigh]

Resolve the lane against the catalog and dispatch it. No meter is read, nothing is ranked. Shared logic lives in `delegate.py`; this file only names the harness.

    python3 ~/.claude/skills/delegate/scripts/delegate.py dispatch --harness codex --lane <name> --brief </abs/brief.md> --cwd "$PWD" [--write </abs/worktree>] [--effort <e>]

`--model <slug>` in place of `--lane` resolves the model to its lane on this harness; an unknown model fails with the lanes on this harness listed. A missing `codex` binary fails before dispatch with a plain message. Run in the background when the lane is slow; read `<run>/return.json` when notified.

Arguments typed after the skill name: `$ARGUMENTS`.
