# Lane benchmark scan — 2026-09-08

Purpose: give a delegation router a comparable capability score per (harness/model, effort) lane. All
numbers below came from web search and page fetches done today (2026-09-08); every cell cites a
source in §2. **Where two sources disagree by more than rounding, both numbers are shown with a ⚠
flag — do not average them.** Aggregator sites in this space frequently republish numbers with
transcription errors, so treat single-source aggregator numbers as lower-confidence than a vendor's
own model/system card or a live leaderboard fetch.

## 1. Benchmark table

Cells: `score [source] (effort/thinking level if stated)`. `—` = not found. `UNVERIFIED` = found only
as a vague claim with no number.

| Model (effort) | SWE-bench Verified | SWE-bench Pro | Terminal-Bench 2.1 | Terminal-Bench 4.0 | Aider polyglot | LiveCodeBench | AA Intelligence Index | AA Coding Agent Index | LMArena (coding/WebDev) |
|---|---|---|---|---|---|---|---|---|---|
| Claude Fable 5.1 (adaptive, max) | — | 81.2% [S1] | — | 55.8% (Anthropic) / 57.9%±3.8 official #1 [S9] ⚠ | — | — | 66 [S6] / 53 tied w/ Astra [S7] ⚠ | 70 (in Claude Code) [S6] | — |
| Claude Mythos 5 / 5.1 | — | 80.3% (Mythos 5) [S1] | — | 60.9% #1 (Mythos 5.1, Anthropic's own) [S9] | — | — | — | — | — |
| Claude Fable 5 (predecessor) | 95.0% UNVERIFIED, single aggregator [S2] | 80.0% [S1] | — | 42.0%→55.8% is the Fable5→5.1 TB4.0 jump Anthropic cites [S8] | — | — | — | — | — |
| Claude Opus 5 (max) | 96.0%, mean of 5 trials [S3] | 79.2% [S1] | 89.1% [S4] | 51.8%±3.4 official / 52.3% Anthropic [S9] | — | — | 63 [S6] | ~equal to Astra's 67 [S6] | leads WebDev Arena ~1704 Elo, Jul 2026 [S13] |
| Claude Sonnet 5 | 92.4% [S3] / 72.7% [S2] ⚠ large disagreement | 63.2% [S1] | — | — | — | — | — | — | — |
| Claude Haiku 4.5 | 73.3%, single aggregator, UNVERIFIED [S2] | — | — | — | — | — | — | — | — |
| GPT-6 Astra (max) | — (Astra's launch table used DeepSWE, not SWE-bench) [S5] | — | — | 57.9%–59% across 3 sources [S5][S9] | — | — | 61 tied w/ Sol [S7] / 53 tied w/ Fable5.1 [S7] ⚠ | 67 [S6] | — |
| GPT-5.6 Sol (max) | — | 64.6% [S1] | 88.8% [S10] / 91.9% public snapshot [S11] ⚠ | — | — | — | — | 80 [S11] | — |
| GPT-5.6 Terra (max) | — | 63.4% [S1] | 87.4% [S10] | — | — | — | — | 77.4 [S11] | — |
| GPT-5.6 Luna (max) | — | 62.7% [S1] | 84.7% [S10] | — | — | — | — | 74.6 [S11] | — |
| Grok 4.6 (high) | UNVERIFIED — "improved sharply from Grok 4.5's 54%," no % given [S12] | — | 88.4% [S10] | — | — | — | UNVERIFIED — "ties GPT-5.6 Sol for 3rd" [S7] | — | — |
| Grok 4.6 (xhigh) | — | — | — | — | — | — | — | — | — |
| Gemini 3.8 Flash (medium, default) | — | — | — | — | — | — | — | — | — |
| Gemini 3.8 Flash (high) | — | 61.6% [S14] | 89.4% [S14] | 19.1% [S14] (different, much harder task set than TB2.1 — not comparable) | — | — | — | — | — |
| Gemini 3.1 Pro (current "Pro") | 80.6% [S15] | — | 85.8% is 3.7 Flash, not 3.1 Pro [S10] | — | — | 91.7% Elo-style LiveCodeBench Pro rank, may be the same lineage listed as "Gemini 3 Pro Preview" [S16] | — | — | — |

Notes on gaps: Aider polyglot's own leaderboard top score in the fetched snapshot was 0.880 by
plain "GPT-5" [S17] — the leaderboard clearly has not been refreshed with any 2026-generation model,
so it is not usable for this comparison at all right now. LMArena/WebDev Arena only turned up one
usable number (Opus 5). LiveCodeBench only turned up Gemini-family numbers.

## 2. Sources (fetched 2026-09-08 unless noted)

- S1 — SWE-bench Pro leaderboard, benchlm.ai, direct fetch, captured by the site 2026-09-08: https://benchlm.ai/benchmarks/swe-bench-pro
- S2 — Aggregator search snippets (not independently verified against a primary source): morphllm.com Claude benchmarks page (fetch blocked, HTTP 429 — https://www.morphllm.com/claude-benchmarks) and alphaXiv Claude Opus 5 system card mirror: https://www.alphaxiv.org/abs/2607.claude-opus-5
- S3 — Search-engine synthesis citing an Anthropic system card for Opus 5 (96.0%, mean of 5 trials) and a DEV Community post for Sonnet 5 (92.4%): https://dev.to/best_codes/anthropic-just-dropped-claude-sonnet-5-and-the-benchmarks-are-kind-of-insane-3ppc
- S4 — alphaXiv Opus 5 system card mirror (Terminal-Bench 2.1: 89.1%): https://www.alphaxiv.org/abs/2607.claude-opus-5
- S5 — GPT-6 Astra coverage: https://www.mindstudio.ai/blog/gpt-6-astra-benchmarks-analysis and Artificial Analysis GPT-6 Astra vs Fable 5.1 comparison page (fetched directly): https://artificialanalysis.ai/models/comparisons/gpt-6-astra-vs-claude-fable-5-1
- S6 — Artificial Analysis GPT-6 Astra vs Claude Fable 5.1 comparison, fetched directly. This page reported AA Intelligence Index = 53 for BOTH models (tied) — conflicts with S7's 66/63/61 figures. Terminal-Bench v4.0 on this page: Astra 59%, Fable 5.1 52%. Cost: Astra $3.26/task vs Fable 5.1 $7.63/task; $7.70 vs $7.175 per 1M tokens; total index run cost $5,324 vs $13,129; Fable 5.1 used ~78k output/47k reasoning tokens per task vs Astra's ~27k/17k. https://artificialanalysis.ai/models/comparisons/gpt-6-astra-vs-claude-fable-5-1
- S7 — Search-engine synthesis of Artificial Analysis coverage citing Fable 5.1 Intelligence Index 66, Opus 5 63, GPT-6 Astra/Sol 61, and Fable 5.1 Coding Agent Index 70 vs Astra 67: https://aiweekly.co/alerts/gpt-6-astra-lands-at-67-on-coding-index-behind-fable-51s-70 and https://x.com/ArtificialAnlys/status/2095595489031000350
- S8 — Anthropic Fable 5.1 launch coverage (TB-Science 24.7%→52.6%, AutomationBench 17.1%→31.4%, TB4.0 42.0%→55.8% Fable5→Fable5.1): https://datasciencedojo.com/blog/claude-fable-5-1-performance-and-safety/
- S9 — Terminal-Bench 4.0 leaderboard synthesis (Astra 58.18% public snapshot / Fable 5.1 57.88%; tbench.ai official Fable 5.1 57.9%±3.8 #1, Opus 5 51.8%±3.4; Anthropic's own numbers: Mythos 5.1 60.9%, Fable 5.1 55.8%, Opus 5 52.3%): https://snorkel.ai/leaderboard/terminal-bench-4-0/, https://benchlm.ai/benchmarks/terminal-bench-4, https://www.tbench.ai/news/terminal-bench-4-0
- S10 — Terminal-Bench 2.1 leaderboard, codingfleet.com, fetched directly, last updated 2026-09-03: https://codingfleet.com/blog/terminal-bench-leaderboard-2026/
- S11 — GPT-5.6 SWE-bench Pro and Terminal-Bench 2.1 numbers plus AA Coding Agent Index (Sol 80, Terra 77.4, Luna 74.6), and Sol's conflicting 91.9% TB2.1 public-snapshot figure: https://layerlens.ai/blog/gpt-5-6-benchmark-review-sol-terra-luna and https://artificialanalysis.ai/articles/gpt-5-6-has-landed
- S12 — Grok 4.6 coverage, no confirmed SWE-bench Verified %: https://codersera.com/blog/grok-4-6-benchmarks-explained-2026/ and https://www.mindstudio.ai/blog/grok-4-6-release-benchmarks. xAI's own model card PDF (https://media.x.ai/v1/website/card-4p6-4cd2dc57.pdf) could not be parsed by the fetch tool (binary/compressed streams) — not independently confirmed from the primary source.
- S13 — WebDev Arena / LMArena coverage (Opus 5 ~1704 Elo, Jul 2026; Kimi K3 leads open-weight at 1679): https://epoch.ai/benchmarks/webdev-arena and general LMArena leaderboard search
- S14 — Gemini 3.8 Flash benchmarks (DeepSWE v1.1 73.7%/74% high/71% medium, TB2.1 89.4%, TB4.0 19.1%, SWE-bench Pro 61.6% vs 3.7 Flash's 60.4%, three thinking levels low/medium/high default medium): https://www.vellum.ai/blog/gemini-3-8-flash-benchmarks-explained and https://emergent.sh/learn/gemini-3-8-flash-benchmarks
- S15 — Gemini 3.1 Pro coding coverage (SWE-bench Verified 80.6%, LiveCodeBench Pro leader at 2,439 Elo, 2M context): https://gitautoreview.com/blog/gemini-3-pro-code-review and https://almcorp.com/blog/gemini-3-1-pro-complete-guide/
- S16 — LiveCodeBench leaderboard search result, captured 2026-08-25 per the site (Gemini 3 Pro Preview 91.7%, Gemini 3 Flash Preview 90.8%, DeepSeek V3.2 Speciale 89.6%): https://pricepertoken.com/leaderboards/benchmark/livecodebench
- S17 — Aider polyglot leaderboard, llm-stats.com, search snippet (top score 0.880, "GPT-5", 22 models, all self-reported): https://llm-stats.com/benchmarks/aider-polyglot
- S18 — Grok 4.6 vs Opus 5 efficiency claim (Grok ~53 turns/0.5B input tokens vs Opus 5 ~103 turns/2.0B tokens; ~4x cheaper on AA-Briefcase): https://www.mindstudio.ai/blog/grok-4-6-release-benchmarks

## 3. Vendor statements about effort/thinking levels

- **OpenAI (GPT-5.6 family):** Sol/Terra/Luna are "one architecture distilled into three capability
  tiers" sharing the same reasoning-effort ladder: none, low, medium, high, xhigh, max. The
  benchmark numbers collected above are at **max**. Terra is pitched as "competitive performance to
  GPT-5.5 while being 2x cheaper," i.e. an explicit prior-generation-parity-at-lower-cost claim, not
  an effort-level claim. [S11]
- **Google (Gemini 3.8 Flash):** three thinking levels, low/medium/high, medium is default. Vendor
  framing is that medium "can still solve complex agentic tasks while reducing token consumption" —
  an efficiency claim, not a stated parity with a specific prior model. High vs medium on DeepSWE
  v1.1: 74% vs 71% — a 3-point gap, not large. [S14]
- **xAI (Grok 4.6):** DeepSWE v1.1 at high effort 65.9% vs xhigh 67.0% — about a 1-point gap for the
  jump to the top effort tier, suggesting diminishing returns above "high." No explicit
  prior-model-parity statement was found in secondary coverage; the primary model card PDF could not
  be parsed by the fetch tool, so this is not confirmed from xAI directly. [S12]
- **Anthropic (Fable 5.1):** coverage explicitly warns "every figure depends on the effort level, so
  a score means nothing without it," and notes both Fable models were scored with production safety
  classifiers switched ON, taking zero credit on any task a classifier intervened on — meaning the
  published numbers are a conservative floor, not a ceiling. The Artificial Analysis comparison page
  tested Fable 5.1 at "Adaptive Reasoning, Max Effort, Default Fallback." [S8][S6]

## 4. Tiering proposal (synthesis — mine, not sourced)

Rule used: primarily the SWE-bench Pro leaderboard (S1, single-source, same methodology across
models, captured today) as the spine, cross-checked against Terminal-Bench 4.0 and the AA Coding
Agent Index where SWE-bench Pro was missing (Astra, Grok 4.6, Gemini, Haiku).

1. **Tier 1 (frontier, SWE-bench Pro ≥79% or clearly AA-equal to that band):** Claude Fable 5.1
   (adaptive/max), Claude Mythos 5.1 (max), Claude Fable 5 (max), Claude Opus 5 (max). GPT-6 Astra
   (max) is placed here tentatively — no SWE-bench Pro number exists for it yet, but its
   Terminal-Bench 4.0 score (~58%) sits at or above Fable 5.1's, and its AA Coding Agent Index (67)
   is close to Fable 5.1/Opus 5's band.
2. **Tier 2 (strong, SWE-bench Pro 60–70%):** GPT-5.6 Sol (max, 64.6%), GPT-5.6 Terra (max, 63.4%),
   Claude Sonnet 5 (63.2%), GPT-5.6 Luna (max, 62.7%), Gemini 3.8 Flash (high, 61.6%). Grok 4.6
   (high) is placed here tentatively on Terminal-Bench 2.1 parity with Sol (88.4% vs 88.8%), not on
   a confirmed SWE-bench Pro number.
3. **Tier 3 (mid, harder to place — thin evidence):** Claude Haiku 4.5 — only one unverified
   aggregator number (73.3% SWE-bench Verified, no Pro/Terminal-Bench found). Placed here by
   Anthropic's known cheap/fast product positioning, not by benchmark evidence.
4. **Tier 4 (insufficient evidence to place at all):** Gemini 3.8 Flash at low/medium thinking (no
   discrete numbers found, only the 71%/74% medium/high DeepSWE pair), Grok 4.6 at xhigh (only the
   1-point DeepSWE delta over high, no other benchmark at xhigh), Gemini 3.1 Pro / Gemini 3 Deep
   Think (SWE-bench Verified found but no Pro/Terminal-Bench/AA-Index cross-check), GPT-6 Astra's
   exact SWE-bench standing (no number published at all, only DeepSWE and Terminal-Bench 4.0).

**Biggest caution for the router:** the Claude Sonnet 5 SWE-bench Verified figure has a 20-point
spread across two sources (92.4% vs 72.7%) that I could not resolve — do not key any threshold off
Sonnet 5's Verified score until this is confirmed against Anthropic's own system card. The AA
Intelligence Index for Fable 5.1 and GPT-6 Astra also has two irreconcilable readings (66/63/61 vs a
flat 53/53 tie) from what should be the same underlying methodology — likely two different snapshot
dates or two different AA index versions, not resolved here.

## 5. Open questions

- Which SWE-bench Verified number is right for Sonnet 5 (92.4% vs 72.7%)? Needs Anthropic's primary
  system card, not aggregator search snippets.
- Is the AA Intelligence Index conflict (66/63/61 tier vs flat 53/53) a stale-cache issue on one of
  the two Artificial Analysis pages, or two genuinely different index revisions? Needs a direct,
  single fresh fetch of artificialanalysis.ai's main leaderboard rather than a bilateral comparison
  page.
- No SWE-bench (any variant) number exists yet for GPT-6 Astra — it may simply not have been run
  yet, three weeks post-launch (2026-09-03).
- No Aider polyglot or LMArena coding numbers exist for any 2026-generation model in what I could
  fetch; both leaderboards look stale relative to this task's model list and need a maintainer-side
  refresh check, not just a better search query.
- Claude Haiku 4.5 has essentially no verified benchmark coverage in this pass — worth a targeted
  Anthropic system-card fetch rather than aggregator search.
- xAI's own Grok 4.6 model-card PDF was not machine-readable by the fetch tool; a manual read or a
  PDF-to-text conversion would likely resolve several of the Grok 4.6 UNVERIFIED cells.

## 6. Lead verification (Fable session, 2026-09-08)

- Claude Sonnet 5, from Anthropic's own system card (PDF, section 8.2, five-trial mean, thinking on): SWE-bench Verified **85.2%**, SWE-bench Pro **63.2%**, SWE-bench Multilingual 78.3%, Terminal-Bench 2.1 **80.4%** (mini-SWE-agent harness). The 92.4% and 72.7% Verified figures in section 1 are both wrong; the 63.2% Pro figure from S1 is confirmed. Source: https://www-cdn.anthropic.com/480e0bb54327b9622282e9c39a83a4f490ed377e/Claude%20Sonnet%205%20System%20Card.pdf
- Same table gives GPT-5.5 SWE-bench Pro 58.6% and Terminal-Bench 2.1 83.4% (Codex CLI), Gemini 3.5 Flash 55.1% and 76.2%, Sonnet 4.6 58.1% and 67.0%.
- GPT-6 Astra: openai.com/index/gpt-6-astra returns a bot-challenge page to automated fetch; the deployment safety card lists no coding benchmarks; the API model page lists pricing ($10 / $1 / $50 per 1M, 1,050,000 context, effort low..max) and no scores. SWE-bench standing remains unpublished as of this date.
