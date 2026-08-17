# Model routing preferences

updated: 2026-08-16
status: rankings seeded from global CLAUDE.md 2026-08-03; balancing policy added 2026-08-16. Orin corrects, agents never edit.

Consumers: any agent choosing a model for a subagent, workflow stage, agent-team
teammate, or external CLI delegation. Classify the task with the tier rubric,
walk the ranked list, honor Exclusions absolutely.

## Task tiers
- deep-reasoning — architecture/design, ambiguous root-cause debugging,
  adjudication, final synthesis across many findings, high-stakes review
- hard-coding — multi-file behavioral change, nonlocal invariants,
  security-sensitive work, complex debugging
- routine-coding — well-scoped implementation, tests, refactors with a clear spec
- mechanical — repeatable transforms, renames, formatting, high-volume
  file-by-file work
- review — independent verification of finished work

## Preferences (ranked, harness-agnostic)
- deep-reasoning: Fable 5 > GPT-5.6 Sol > Gemini 3.1 Pro (high)
- hard-coding: GPT-5.6 Sol > Opus 5 > Gemini 3.7 Flash (high)
- routine-coding: GPT-5.6 Terra > Sonnet 5 > Gemini 3.7 Flash (high)
- mechanical: Gemini 3.7 Flash (medium) > GPT-5.6 Luna 
- review: top-ranked deep-reasoning or hard-coding model NOT in the author's
  family (house rule: reviewer ≠ author's family)

## Exclusions
- never: Haiku (any version) — below the quality floor for this workflow

## Harness selection (when >1 installed harness serves a model)
- Prefer the model's native harness: Codex↔GPT, Claude Code↔Anthropic
  (Fable/Opus/Sonnet), Antigravity↔Gemini.
- Kiro is the flexible lane: first choice for open-weight models (GLM etc.), otherwise a deliberate second-scaffold option — the same model through a different harness gives a different response.

## Council defaults
- lead/adjudicator: highest-ranked available deep-reasoning model
- quorum: ≥2 model families besides the lead's; below quorum, report DEGRADED and stop — never simulate absent panelists

## Balancing policy (only when CONSULT_BALANCE=1)
Inputs come from scripts/usage.py (cached; probe.sh prints them). Arithmetic
only — no judgement calls.
- Lanes: codex · agy-gemini · agy-claude-gpt · claude-general · claude-fable
  (Fable has its own weekly meter, so it is a separate lane).
- Effective remaining r = min(remaining_5h, remaining_weekly). Weekly only
  bites when it is the smaller.
- Gate: r < 10% → lane unavailable until its binding window resets.
- Rollover: if an unavailable lane's binding window resets within 30 min,
  surface the reset time and ask the user whether to wait rather than degrade.
- Eligible ranks: rank 1, or rank 2 in the tier list; never Exclusions.
  deep-reasoning: rank 1 only.
- Choose the eligible lane with the highest r; if the top two are within 15
  points, quality rank wins.
- Frontier lanes: Opus 5, Fable 5, GPT-5.6 Sol/Terra. Antigravity/Gemini is
  an overflow lane for routine-coding and mechanical only. If a hard-coding
  or deep-reasoning task has no frontier lane available → stop and report
  the earliest reset; do not fall to agy.
- Internal subagents follow the same rule: never Fable when claude-fable is
  low; when claude-general is low, Agent-tool-shaped work goes to consult.
- Refresh: usage.py serves cache ≤10 min old; a SessionStart hook primes it;
  any quota error forces --refresh. Do not poll more often than that.

## Refresh (run when a CLI updates, then bump `updated:`)
- codex: `codex --version`; models: `codex debug models` (verify subcommand
  still exists via `codex debug --help`)
- antigravity: `agy --version`; models: `agy models` (slug IDs)
- claude: `claude --version`; aliases sonnet/opus/fable or full IDs — no list
  command; check Claude Code release notes
- kiro: `kiro-cli --version`; models: `kiro-cli chat --list-models`
- herdr: visibility lane only — references/herdr.md; re-check `herdr agent` help on herdr updates
- usage: `scripts/usage.py --refresh --pretty` — if a lane goes `unknown` after a CLI update, its /usage output shape drifted
