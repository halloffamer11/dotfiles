# Model routing preferences

updated: 2026-08-03
status: DRAFT — rankings seeded from global CLAUDE.md 2026-08-03; Orin corrects, agents never edit.

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
- hard-coding: GPT-5.6 Sol > Opus 5 > Gemini 3.1 Pro (high)
- routine-coding: GPT-5.6 Terra > Sonnet 5 > Gemini 3.6 Flash (high)
- mechanical: GPT-5.6 Luna > Gemini 3.6 Flash (medium)
- review: top-ranked deep-reasoning or hard-coding model NOT in the author's
  family (house rule: reviewer ≠ author's family)

## Exclusions
- never: Haiku (any version) — below the quality floor for this workflow
- caution: GPT-OSS 120B — comparison lane only; never final authority for
  high-stakes work

## Harness selection (when >1 installed harness serves a model)
- Prefer the model's native harness: Codex↔GPT, Claude Code↔Anthropic
  (Fable/Opus/Sonnet), Antigravity↔Gemini.
- Kiro is the flexible lane: first choice for open-weight models (GLM etc.),
  otherwise a deliberate second-scaffold option — the same model through a
  different harness gives a different response.

## Council defaults
- lead/adjudicator: highest-ranked available deep-reasoning model
- quorum: ≥2 model families besides the lead's; below quorum, report DEGRADED
  and stop — never simulate absent panelists

## Machine notes (policy — probe.sh observes actual availability)
- kiro: work machine only; per-invocation model pinning unverified

## Refresh (run when a CLI updates, then bump `updated:`)
- codex: `codex --version`; models: `codex debug models` (verify subcommand
  still exists via `codex debug --help`)
- antigravity: `agy --version`; models: `agy models` (slug IDs)
- claude: `claude --version`; aliases sonnet/opus/fable or full IDs — no list
  command; check Claude Code release notes
- kiro: `kiro-cli --version`; models: `kiro-cli chat --list-models`
