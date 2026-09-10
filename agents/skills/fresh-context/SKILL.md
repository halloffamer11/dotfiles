---
name: fresh-context
description: Pre-context-clear housekeeping — settles unfinished work, deletes session sprawl, and updates CLAUDE.md so a fresh session can resume from persistent files alone. Use whenever the user is about to clear context or end a session, wants loose ends tied up or the project left session-safe, or types "FC", "/fc", "fresh context", or "wrap up".
---

# Fresh Context

Leave the project so a fresh session can pick up from persistent files alone.
CLAUDE.md is the only entry point. Never create handoff, index, summary, or
archive files, and no new directories — state belongs in the files that
already own it. NEVER delete files without direct approval.

## 1. Settle in-flight work

Inventory what this session left unfinished: uncommitted changes, open items
in the task list, active plans or specs (wherever they live), half-built
features. For each, the decision is **keep or drop** — not finish:

- **Keep** → record its status in the artifact that owns it: check off
  completed plan steps, note the blocker in the spec, commit WIP to a branch.
  The task list does not survive a clear — fold open tasks into the owning
  plan or spec, or drop them.
- **Drop** → delete it fully, now: the abandoned code too, not just the plan.

Classify what you can from session context. For the genuinely ambiguous
items, ask the user once with a short keep/drop list — not one question per
item.

## 2. Reverse the sprawl

Sessions create and almost never delete. Sweep for dead code from abandoned
approaches, scratch and temp files, completed or superseded plans and specs,
empty directories, duplicated notes. Propose one deletion list, get
confirmation, then delete.

## 3. Update CLAUDE.md

Review and realign to the project. It is an entry point,
not an instruction manual — detail lives in the files it points to. Remove
stale pointers and anything now derivable from the code. Keep it well under
200 lines.

## Done

Report in chat: what was kept and where its state now lives, what was
deleted, and what changed in CLAUDE.md. No file summarizes the session — the
next session starts from CLAUDE.md.

## Restart prompt

The user is about to clear the context or start a new session. Proactively
give a restart prompt that picks the work up where it left off. Keep it to one
line — the project is self-documenting, so a plain `resume` is usually enough.

### Skills the next session cannot start on its own

A skill whose frontmatter carries `disable-model-invocation: true` is hidden
from the model. The next session will not see it in its skill list, will not
find it by name, and may report that it does not exist. Only the user can
start it, by typing its slash command.

So: if the resumed work runs through such a skill — directly, or through a
workflow or plan that calls it — the restart prompt must carry that slash
command explicitly. Do not rely on the next session to reach for it.

Check the frontmatter of any skill you plan to name:

```
grep -l 'disable-model-invocation: true' <skills-dir>/*/SKILL.md
```

Plugin skills live under
`~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/skills/`.

### Writing it

Put the slash command first, with nothing in front of it — no `resume:`
prefix, no lead-in sentence. It expands only when it leads the message.
Context follows it.

- Wrong: `resume: /mattpocock-skills:implement ticket 07b from ...`
- Right: `/mattpocock-skills:implement ticket 07b from .scratch/delegate-redesign/issues/07b-setup-tui.md`

Use the full `plugin:skill` form for a plugin skill. Name a skill only when
the work needs it; otherwise the one-word default stands.
