---
name: delegate-grok
description: Typed-only. Run one brief on a named Grok lane or model through the delegate dispatcher, with no meter read and no ranking.
disable-model-invocation: true
---

# /delegate-grok (--lane <name> | --model <slug>) </abs/brief.md> [--write </abs/worktree>] [--effort low|medium|high|xhigh]

Resolve the lane against the catalog and dispatch it. No meter is read, nothing is ranked. Shared logic lives in `delegate.py`; this file only names the harness.

    python3 ~/.claude/skills/delegate/scripts/delegate.py dispatch --harness grok --lane <name> --brief </abs/brief.md> --cwd "$PWD" [--write </abs/worktree>] [--effort <e>]

`--model <slug>` in place of `--lane` resolves the model to its lane on this harness; an unknown model fails with the lanes on this harness listed. A missing `grok` binary fails before dispatch with a plain message. Grok's read-only mode is best-effort; the run directory records a tripwire when the tree changed. Run in the background when the lane is slow; read `<run>/return.json` when notified.

Arguments typed after the skill name: `$ARGUMENTS`.
