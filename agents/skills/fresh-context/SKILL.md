---
name: fresh-context
description: Pre-context-clear housekeeping — settles unfinished work, deletes session sprawl, and keeps CLAUDE.md/AGENTS.md a lean map so a fresh session can resume from persistent files alone. Use whenever the user is about to clear context or end a session, wants loose ends tied up or the project left session-safe, or types "FC", "/fc", "fresh context", or "wrap up".
---

# Fresh Context

Leave the project so a fresh session can pick up from persistent files alone.
State lives in the files that already own it: plans, specs, issue trackers,
READMEs, commit messages, etc. CLAUDE.md points to those files and never copies
them. Never create handoff, index, or summary files. Never delete a file
without the user's direct approval.

## 1. Settle in-flight work

Inventory what this session left unfinished: uncommitted changes, open items
in the task list, active plans or specs (wherever they live), half-built
features. For each, the decision is **keep or drop**, not finish:

- **Keep** → record its status in the file that owns it: check off completed
  plan steps, note the blocker in the spec, commit WIP to a branch. The task
  list does not survive a clear, so fold open tasks into the owning plan or
  spec, or drop them.
- **Drop** → delete it fully, now: the abandoned code too, not just the plan.

Classify what you can from session context. For the genuinely ambiguous
items, ask the user once with a short keep/drop list, not one question per
item.

## 2. Reverse the sprawl

Sessions create and almost never delete. Sweep for dead code from abandoned
approaches, scratch and temp files, completed or superseded plans and specs,
empty directories, duplicated notes. Propose one deletion list, get
confirmation, then delete.

## 3. Keep the instruction files a map

CLAUDE.md loads into every session, and a worker in another harness reads the
same text through its `AGENTS.md` link. Every line costs context on every task
and competes with every other line for attention. Design for progressive
disclosure:

1. **CLAUDE.md is the map:** standing instructions every session needs, and
   one-line pointers to everything else.
2. **Owning files are the territory:** each tracker, plan, or spec is the one
   source of truth for its own state, whatever workflow produced it. Point at
   each tracker once (its plan file or issues directory), never at single
   tickets, under a heading that says what it holds, such as "Where state
   lives", not "Status".
3. **Detail loads when a task needs it:** through a pointer the agent follows,
   a nested file, or a path-scoped rule.

### Review what this session added

Review only the lines this session added to the instruction files, where
`<start>` is the commit HEAD was at when the session began:

```
git diff <start> -- '*CLAUDE.md' '*AGENTS.md' '*.claude/rules/*'
git status --short -- '*CLAUDE.md' '*AGENTS.md' '*.claude/rules/*'
```

The second command shows new files that are not yet tracked, which the
diff leaves out.

Stable text needs no second review, and rewriting it at every wrap-up only
causes churn. Review every line only when a tripwire fires (below).

### Place each item

Take the first row that fits. The order matters. State comes first, because
state always feels needed in every session. CLAUDE.md comes last, because
every instruction feels like a standing one: use it only when no row above
fits.

| The item is… | It goes to… |
|---|---|
| Status, progress, results, what happened | The owning tracker, plan, or spec, or the commit message. CLAUDE.md keeps one pointer line to the tracker. |
| A decision about one piece of work | That work's plan, spec, or ticket |
| Needed in one directory only | A nested `CLAUDE.md` in that directory, with an `AGENTS.md` link to it. Every harness reads it. |
| Needed for one file type, or a file pattern across directories | `.claude/rules/<topic>.md` with `paths:`. Only Claude reads it. |
| A procedure run on demand | A skill |
| Must happen every time, with no exception | A hook |
| Personal, not for the team | `CLAUDE.local.md` or `~/.claude/rules/` |
| A project-wide decision the agent must not reopen | CLAUDE.md, one line; its reason goes to the project's decisions file. When these lines pass about ten, move them there too and leave one pointer line. |
| Needed in every session, whatever the task | CLAUDE.md, one line |

Do not create a decisions file for one decision; the commit message holds
its reason until there is enough to need a file.

Before you write a nested file or a rule, read `references/scoped-files.md`
for the file shapes and what each one costs in context.

### Write each line as one instruction

One instruction per bullet, concrete enough to check: "run `make test` before
a commit", not "keep things tested". A bullet that runs to a paragraph holds
several rules, and the model follows only some of them. If an item needs a
paragraph, it is detail: move it to the file that owns it and leave a pointer.

### Check the rules files

If the project has `.claude/rules/`, review each file the same way: one topic,
`paths:` unless it applies everywhere, no state, no conflict with CLAUDE.md or
a nested file. When two files disagree, Claude may follow either one, so fix
the conflict in the file that owns the topic.

### Tripwires

From the project root, run `sh <this skill's directory>/scripts/tripwires.sh`;
do not estimate. It prints each instruction file's size and one `FIRE` line
per tripwire. Tripwires detect a skipped placement pass. They are not targets
to fit under.

A tripwire fires when:
- a file is over 200 lines or about 10 KB;
- a line is over 300 characters;
- a link points to anything but a file in the same directory (a link to an
  ancestor's file loads the same text twice);
- a date appears outside a file name: that is state, and it belongs in a
  tracker.

A `WARN` line is a hint to judge, not a failure:
- `status` marks a status word ("landed", "blocked"): move it if it is state,
  keep it if it is a rule.
- `scope` marks a root CLAUDE.md line that names one directory or a file
  pattern: take it through the table even if an earlier session wrote it.

When one fires, run the placement pass over every line of that file. Do not
compress text to fit: that is how bullets become run-on paragraphs. Move text
out **verbatim** to the file the table names (or to `_archive/` when nothing
owns it), check that no line was lost, then rewrite the short file with
pointers. Never drop a rule to make room. An instruction file that the pass
empties joins the deletion list you propose to the user; delete it only
after the user confirms.

## Done

Report in chat: what was kept and where its state now lives, what was
deleted, each item moved out of an instruction file and where it went, and the
tripwire results (lines and bytes per file). No file summarizes the session;
the next session starts from CLAUDE.md.

## Restart prompt

The user is about to clear the context. Give a one-line restart prompt. The
project documents itself, so a plain `resume` is usually enough.

If the next step runs through a skill whose frontmatter has
`disable-model-invocation: true`, the next session cannot see or start that
skill; only the user can, by typing its slash command. Then the prompt must
start with that slash command, with nothing in front of it (it expands only
when it leads the message), in `plugin:skill` form for a plugin skill, and
the context follows:

`/mattpocock-skills:implement ticket 07b from .scratch/delegate-redesign/issues/07b-setup-tui.md`

Find such skills with `grep -l 'disable-model-invocation: true'
<skills-dir>/*/SKILL.md`. Plugin skills are under
`~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/skills/`.
