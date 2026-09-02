# Model routing (three tiers, roles not versions)

updated: 2026-09-01

Consumers: anything choosing a model for a subagent, workflow stage, teammate,
or external CLI. Three steps: (1) classify the work, (2) pick the harness for
that class, (3) resolve the role to a live slug with scripts/resolve-model.sh.

## 1. Three model tiers
| tier | roles (family) | give it |
|---|---|---|
| 1 — frontier | claude-deep (Fable) first; then claude-hard (Opus), codex-hard (Sol) | the plan, live-context work, ambiguous debugging, architecture, adjudication, final synthesis, review of anything tier-2 produced |
| 2 — capable workers | codex-routine (Terra), claude-routine (Sonnet), grok-code (Grok) | well-scoped implementation, tests, refactors with a clear spec, self-contained lanes, first-pass review |
| 3 — utility workers | gemini-* (Flash, free), codex-mechanical (Luna), claude-utility (Haiku) | bounded work with a checkable definition of done: renames, formatting, high-volume file-by-file transforms, scaffolding, extraction, search and summarization |

Tier rule: work never goes DOWN a tier from where it belongs. Sending work
UP a tier is a quota decision, not a quality one (§3). Within tier 3, Flash
is always first because agy is effectively free; Luna and Haiku are
fallbacks when agy is absent or unavailable.

## 2. Harness by purpose (stable pins, independent of quota)
- **Lead / deep reasoning:** claude-deep (Fable). Owns the plan, the live
  context, final synthesis, and all verification of delegated work.
- **Independent review of Claude-authored work:** codex-hard (Sol) via the
  native reviewer (`codex review`); tier-2 output is reviewed by a tier-1
  model of another family. House rule: reviewer ≠ author's family.
- **Self-contained implementation lanes:** codex-routine (Terra) first;
  claude-routine (Sonnet) when the lane needs Claude-side context or codex is
  unavailable. codex-hard only for security-sensitive or nonlocal invariants.
- **All tier-3 work:** gemini-mechanical via agy. The agy subscription is
  effectively free at our volumes, so tier-3 work never spends Claude or Codex
  quota while agy is present. Fallbacks in order: codex-mechanical, then
  claude-utility (Haiku) only when both external lanes are absent.
- **Routine overflow:** gemini-routine (flash-high) takes routine-coding
  when codex r < 40% and the brief has a crisp definition of done.
- **Second scaffold / third family:** grok-code is the tier-2 worker of a
  fourth family — use it for an independent second implementation or a
  review when both Codex and Claude have already touched the work, and as
  a council panelist. agy also serves claude-* and gpt-oss slugs; use those
  only deliberately for a different-scaffold opinion, never for balancing.

## 3. Balancing (CONSULT_BALANCE=1) — unchanged arithmetic
r = min(remaining_5h, remaining_weekly) from scripts/usage.py. r < 10% →
unavailable; reset ≤ 30 min → ask. Pins in §2 apply first; balancing chooses
among what the pins leave open, highest r wins, within 15 points prefer the
pin's first choice. Tier-1 work never degrades below tier 1; if no tier-1 lane is available,
stop and report the earliest reset. A lane whose usage is `unknown` (probe failed) is eligible by pin or
capability but never wins a balancing choice over a lane with a known r.
grok has a weekly meter only (no 5h window), so its r is its weekly r.

## 4. Council (unchanged)
Lead = claude-deep. Quorum ≥ 2 families besides the lead's; below quorum
report DEGRADED and stop. Never simulate absent panelists.

## 5. Refresh
- Slug patterns: scripts/resolve-model.sh (the only version-aware file).
- Recipes and their `verified-against` stamps: references/<harness>.md.
- Adding a harness: references/<name>.md + a probe line in probe.sh + a
  usage probe in usage.py + a row in §1 + rerun evals/browser/run.sh.
