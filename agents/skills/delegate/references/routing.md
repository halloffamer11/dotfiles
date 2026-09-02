# Model routing — classes, lanes, and the rank

updated: 2026-09-02 (draft for Orin; replaces the three-tier prose table)

Consumers: anything choosing a model for a subagent, workflow stage, teammate,
or external CLI. The registry is `../lanes.json`; the arithmetic is
`../scripts/rank.py`. This file states the rules; it names no versions.

## 1. Classify the work (ten classes, every job fits one)
| class | tier | shape |
|---|---|---|
| lead | 1 | plan, live-context debugging, adjudication, final synthesis — the session, never delegated |
| design | 1 | spec amendment, splitting a large plan, synthesis over large inputs |
| review | 1 | independent review of a diff; reviewer family ≠ author family |
| hard-impl | 1 | security-sensitive or nonlocal invariants |
| impl | 2 | self-contained implementation, tests, refactor with a clear spec |
| verify | 2 | refute, verify, standards check, critic, revise |
| scout | 3 | finder, grounding, search-and-summarize, research legwork |
| mechanical | 3 | renames, formatting, high-volume transforms, extraction, scaffolding |
| browser | 2 | eligibility from evals/browser/_profile.md, then classify the reasoning part |
| council | 1 | the council skill; quorum ≥ 2 families besides the lead |

Tier rule: work never goes DOWN a tier from its class. Going UP is a quota
decision the rank makes, never a quality one.

## 2. Lanes (one model through one harness on one meter)
Rows live in lanes.json with list-price burn and the classes each wins.
Summary, tier 1 → 3: fable@claude (lead only) · sol@codex · opus5@claude ·
terra@codex · grok46@grok · opus46@agy · sonnet5@claude · flash-high@agy ·
flash-medium@agy · luna@codex. haiku@claude is the courier relay and never
does work. A lane that wins no class gets no row.

Pins that do not move with quota:
- Review of Claude-authored work: sol@codex via `codex review`. opus46@agy is
  eligible for review only when the author family is not Anthropic.
- opus5@claude and sonnet5@claude are the exception lanes: a worker on them
  needs a `why-claude:` reason (the Skill tool, or this session's live
  context). Worker classes pin them last, so they win only when every
  external lane is out or a reason is stated.
- opus5@claude never exceeds one third of a workflow's agents.
- agy's Claude-family lane (opus46@agy) takes verify/critic/revise stages —
  Claude-family judgement without spending claude-general (Q2, 2026-09-02).
- flash-high@agy is in verify on trial (2026-09-02, Orin: Gemini 3.8 Flash
  high is on par with Grok 4.6). Pinned last among the external lanes; the
  next 3 real verify briefs go to it and grok46 in parallel, adjudicated by
  the session. Move it up or drop it on that evidence. Brief 1 (2026-09-02,
  five code claims over this skill, two planted false): Flash 5/5 with exact
  lines in 1m57s; Grok 5/5 in 1m39s once the harness recipe was fixed
  (references/grok.md, `--json-schema`). Two briefs remain.

## 3. Rank (`rank.py <class> [author-family]`) — balancing at every stage
Pin order already puts external lanes first for every worker class, so the
external default holds at any quota level. With DELEGATE_BALANCE=1 the live
meters choose among the eligible lanes:
- Two numbers per meter from usage.py. r = min(remaining_5h,
  remaining_weekly) is the gate. pace = remaining_weekly ÷ fraction of the
  weekly cycle still to run: 1.0 is even spending, above 1 is ahead (that
  quota expires unspent at the reset), below 1 is behind. The 5h window is a
  rate cap, not a budget — nothing is lost when it goes unused — so the
  weekly allotment is what the rank spends evenly (adopted 2026-09-02, after
  Codex was ranked last all week: its weekly was 75% spent by Sep 1 while
  Antigravity was on course to lose half its cycle unspent).
- status unavailable (r < gate 10%) is skipped; unknown never beats a known
  score. score = pace, or r for a meter with no weekly reading.
- Highest score wins. Within tie_band (0.15) on score and above the
  rebalance line (r 40%), pin order wins, then lower burn.
- Tier-1 class with no available lane → STOP and report the earliest reset.
- With DELEGATE_BALANCE unset, pin order is the answer (optimal mode).
The 40% line is not where balancing starts; it is where the hard stops start
(no Opus workers, at most 4 Claude workers, effort medium).

## 4. Workflows and teams: stage → class
| stage name contains | class | default lane |
|---|---|---|
| finder, scout, grounding, recon, survey | scout | flash-medium@agy |
| sweep, rename, format, extract, scaffold | mechanical | flash-medium@agy |
| refute, verify, check, critic, revise, lens | verify | opus46@agy or grok46@grok by r |
| implement, build, fix, test | impl | terra@codex / grok46@grok by r |
| review | review | sol@codex |
| design, split, amend, spec | design | opus5@claude with why-claude, ≤ 1/3 of agents |
| judge, synthesize, adjudicate | lead | the session — not an agent |

Every `agent()` call names `agentType` (courier) or `model` (with a
`// why-claude:` line in the script); the PreToolUse hook denies scripts
that do not. Fan-out rules (hook-enforced, numbers in lanes.json): above 8
agents a `budget` is required; above 12 the run is split into phases with a
re-rank between them; when any claude lane is below 40%, at most 4 Claude
workers, all at effort medium.

Right-sizing a review (Orin, 2026-09-02): one pass of 3–4 finders plus the
session's own reading. One refuter, only for a finding the session cannot
adjudicate. Never a workflow review and an external review of the same diff.

## 5. Council (unchanged)
Lead = the session. Quorum ≥ 2 families besides the lead's; below quorum
report DEGRADED and stop. Never simulate absent panelists.

## 6. Refresh
- Prices and lane rows: lanes.json (`burn` is 0.75·input + 0.25·output).
- Slug patterns: scripts/resolve-model.sh (the only version-aware file;
  `DELEGATE_EXCLUDE` lets dispatch.sh retry once on the next-newest slug).
- Recipes and `verified-against` stamps: references/<harness>.md; the same
  commands are encoded in scripts/dispatch.sh — change both together.
- Adding a harness: references/<name>.md, a probe line in probe.sh, a usage
  probe in usage.py, a case in dispatch.sh, rows in lanes.json, rerun
  evals/browser/run.sh.
