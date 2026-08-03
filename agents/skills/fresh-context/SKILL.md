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
