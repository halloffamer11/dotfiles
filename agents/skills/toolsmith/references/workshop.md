# Workshop conventions

A **workshop** is a directory where toolsmith engagements accumulate. Its purpose: a fresh agent starts from a rapid, honest index instead of from zero, and every engagement leaves the workshop more capable than it found it - breadcrumbs for the narrative, deterministic probes for the state. A directory is a workshop when its CLAUDE.md declares itself one and points here.

The founding principle: **the machine is the source of truth; the workshop is a compiled cache of past work.** Nothing in a workshop may produce confidence that state has not changed. Pages therefore carry knowledge and pointers, never current state; current state is always fetched by running a probe.

## Layout

```
<workshop>/
  CLAUDE.md      # auto-loads every session: tenets, rules, one-line-per-topic index
  topics/        # breadcrumb pages, one per domain of past work
  probes/        # deterministic read-only scripts, invoked directly by path
```

The workshop is a git repo. Git history is the only log - never maintain a changelog, activity log, or inventory by hand.

## The index (in CLAUDE.md)

- One line per topic: link + a hook that says when to open it. Hard budget: the whole CLAUDE.md fits one screen.
- Hand-maintained under the update rule below. A topic page without an index line is lost; fix that in the same commit that adds the page.

## Topic pages

One page per domain of work (recording-rig, browser, obsidian...), not per tool. Budget: lean, roughly 100 lines; if a page outgrows that, prune before splitting.

A page earns its tokens only with what an agent cannot cheaply rederive:

- **State pointers** - where truth lives: the probe that checks it, the config file, the source whose header carries the rationale. Never duplicate what a repo, script header, or doc already records; point at it.
- **Decisions** - dated, one line each, with the why when it is not obvious.
- **History** - dated engagement breadcrumbs: what was done, what broke, what was learned.
- **Open threads** - what the next engagement should pick up.

A concrete value may be inlined only when it anchors a decision, and always dated (`2026-08-28 - Helium 0.15.7.1 ...`). A dated value is a hint about the past, never a fact about the present.

## Probes

Deterministic scripts that answer one question about current machine state. The preferred artifact of any engagement: work captured as a probe costs no LLM tokens the next time.

Contract:

- Plain executable bash, invoked by path. No runner, no framework. Probes never call each other and never read the workshop.
- Header block: `# probe:` name, `# what:` the question it answers, `# scope:` local | server | all, `# read-only:` statement.
- Read-only commands only. No network unless the filename ends `.net.sh`.
- Deterministic output: stable ordering, one status line per check. Exit 0 = healthy, nonzero = a check failed. Finish in a couple of seconds.
- Server probes run from the local machine over ssh (`server-*.sh`); nothing deploys to the server.

## Update protocol - every engagement, before it closes

- **Update what you touch.** Any fact you verified, any decision made, any gotcha hit in a domain you worked on goes into that topic page, dated. Stale claims you disproved get corrected or deleted, not annotated.
- **File new probes.** If the engagement ran the same deterministic check twice, it should have been a probe; write it before closing.
- **Prune.** Anything a probe can now answer comes out of the prose.
- **Keep the index current** and commit with a short message. Leaving an engagement without filing back is a defect: the next agent pays for it.
