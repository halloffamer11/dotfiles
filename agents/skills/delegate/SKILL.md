---
name: delegate
description: Route worker-shaped work to the right model, harness, and quota — a well-scoped lane of implementation, verification, scouting, or mechanical work handed to another agent CLI (Codex, Antigravity, Grok, headless Claude), an independent review from another model family, or a second opinion. Use before any Agent, Workflow, or teammate spawn to rank lanes (scripts/rank.py <class>), and to answer questions about remaining subscription usage or reset times (scripts/usage.py, scripts/probe.sh). Not for work that needs this session's live context, and not for trivial single-file edits that are faster inline.
---

# Delegate — classify, rank, dispatch, verify

The session (Fable) plans, holds the live context, adjudicates, and
synthesizes. Everything worker-shaped goes out through a lane: one model
through one harness on one usage meter. External lanes are the default at
every quota level; a Claude worker is the exception and needs a reason.

Files: `lanes.json` (the registry), `scripts/rank.py` (the arithmetic),
`scripts/dispatch.sh` (the one way to run a child), `schemas/return.json`
(the fixed return shape), `templates/brief.md` (the preamble every child
gets), `references/routing.md` (the rules in prose), `references/<harness>.md`
(each CLI's recipe and quirks).

## 1. Classify
Pick the class from lanes.json: `lead design review hard-impl impl verify
scout mechanical browser council` (rules in references/routing.md §1). A
workflow stage name maps through the `stages` table, so `rank.py refute`
works. Work never goes down a tier from its class.

## 2. Rank
    python3 scripts/rank.py <class> [author-family]
Prints the eligible lanes best first. Worker classes pin external lanes
first and Claude lanes last, so an external lane wins whenever one is
available: the balancing happens on every call, not only when Claude is
low. With `DELEGATE_BALANCE=1` (personal machines, `~/.zshrc.local`) the
live meters decide between eligible lanes: highest remaining r wins, pin
order breaks near-ties only above the 40% line, unavailable lanes are
skipped, a tier-1 class with no lane says STOP with the earliest reset.
Without it, pin order is the answer. For `review` pass the author's family
so the reviewer is never the author's family. Take the top lane; a lower
one needs a stated reason. Record one line:
`delegate: <class> → <lane> (rank #n, r=NN%[, reason])`.

## 3. Dispatch
Write the task as five lines — `objective:`, `scope:`, `constraints:`,
`done:`, `return:` — nothing else. dispatch.sh adds the non-interactive
preamble, the convergence budget, the write rule, and the return schema,
and it retries once on the next-newest model slug if a freshly listed
version fails.

- **Courier (the default from a session):** Agent tool with
  `subagent_type` `agy-runner` | `codex-runner` | `grok-runner`. Each is a
  Haiku relay that runs one dispatch.sh call and returns the schema object
  verbatim, so the child's exploration never enters this context. State
  the role (lanes.json `role`), the working directory, effort, and — only
  when the user authorized implementation — the isolated git worktree.
  Couriers never need a reason.
- **Claude worker (the exception):** an Agent spawn on Sonnet or Opus, or
  a built-in like Explore, is allowed only with `why-claude: <reason>` in
  the prompt — it needs the Skill tool or this session's live context. The
  PreToolUse hook denies the spawn otherwise, and denies Opus workers or
  effort above medium when any Claude lane is below 40%.
- **Workflow stage:** `agent(brief, {agentType: 'agy-runner', label})`.
  Every `agent()` names `agentType` or `model`; a `model` stage needs a
  `// why-claude:` line in the script. The hook denies scripts that miss
  either, fan-outs over 8 without a `budget`, Fable workers, and stock
  workflows launched by name. Above 12 agents it asks you to split into
  phases and re-rank between them.
- **Teammate:** "spawn a teammate using the agy-runner agent type". The
  definition's model and tools apply; its `skills:` field is ignored,
  which is why the recipe lives in dispatch.sh, not in the courier.
- **Inline (this context runs dispatch.sh):** only for a short expected
  return, or to see raw child output when debugging the delegation.
- **Resume, when it is cheaper:** the `delegate:` line carries the child's
  session id. `--resume <id>` continues that child for a follow-up that
  builds on its findings and is smaller than a cold spawn. A large or
  unrelated follow-up starts fresh. An option to right-size, not a rule.
- **sol@codex at high effort** outruns the 10-minute Bash ceiling: run the
  courier or the inline call with `run_in_background` and poll the out file.
- **Herdr visibility lane:** only when the user asks to watch and
  `HERDR_ENV=1` (references/herdr.md). Never auto-select.

## 4. Verify
The return object is a claim. `status` other than `done` is a partial
result, not a success. Read the files in `evidence`, diff the
`changed_files`, run the checks you would run for your own work. Size a
review to the artifact: one pass of 3–4 finders plus your own reading; one
refuter only for a finding you cannot adjudicate; never a workflow review
and an external review of the same diff.

## Invariants
- Headless only; stdin closed; prompts via file; caller's Bash timeout.
- Read-only sandbox unless the user authorized implementation, then an
  isolated worktree. Never permission-bypass or full-access flags.
- Models by role through resolve-model.sh; empty output = lane unavailable.
- Children never delegate and cause no external side effects (template).
- Quota failure: `usage.py --refresh`, mark the lane unavailable, re-rank
  once. Exhaustion signals (usage_limit_reached, RESOURCE_EXHAUSTED,
  free-usage-exhausted, a named plan cap) fail over; a bare 429/529 backs
  off and retries the same lane once.
- Version drift (`<cli> --version` ≠ the recipe's `verified-against`): run
  that subcommand's `--help`, adapt, retry once, report the drift. Never
  edit references/*.md or routing.md yourself; propose the diff.

## The ledger
`~/.claude/hooks/delegate-ledger.py` records lane r at every spawn and
subagent stop; `--report --since 24` shows drain per lane, Claude's share
of it (target ≤ 40%), and dispatch counts. Read it before a second wave of
any fan-out and when asked "what did that cost".

## Browser lanes
Authenticated and unauthenticated browser capability is profiled per lane
in `evals/browser/_profile.md` (rerun `evals/browser/run.sh` after any CLI,
extension, or grant change). Classify the reasoning part as above; the
profile gates eligibility. Recipes: each harness reference's Browser section.
