# quota-axi vs delegate metering (0.1.44 / 9c7d135)

## Reference in brief

quota-axi 0.1.44 is an npm CLI that reports local provider quota windows and never routes (`package.json:2-5`, `README.md:19-20`, `VISION.md:15-20`). Adapters (`src/providers/*`) read local auth, call first-party usage/loopback/CLI probes, and emit a normalized `ProviderQuota` (`types.ts:250-295`, `types.ts:319-324`). Shared derivations then add per-window `pace`, scope `effectivePercentRemaining`, `runway`, and `selection.spendPriority` (`pace.ts:48-105`, `pace.ts:107-246`, `pace.ts:324-360`, `interpretation.ts:16-34`). Output tiers: compact TOON (`quota[]` / `exhaustion[]` / `attention[]`), `--json` schemaVersion 5 with derivation inputs demoted, `--full` restores them, `--tui` is presentation only (`README.md:359-410`, `commands.ts:53-60`, `render.ts:74-93`). Stated non-goals: not a router, proxy, login manager, hosted service, or desktop app; never mint/rotate credentials or spend the quota being measured (`VISION.md:65-72`, `README.md:785-795`). VISION.md:43 says a number that has stopped being true is never served; shipped code still returns stale raw windows labelled `stale` with effective remaining unknown (`interpretation.ts:51-64`, `AGENTS.md:7`).

## Concept map

| Delegate term | quota-axi nearest | Delegate rule | quota-axi rule | Relation |
| --- | --- | --- | --- | --- |
| Meter | `scope` (+ `provider`) | One subscription quota; lanes share it (`CONTEXT.md:85-87`). Catalog keys: `claude-fable`, `claude-general`, `codex`, `grok`, `agy-gemini` (`lanes.json:3-33`). Observation key is `lane` = `{harness}-{meter}` (`usage.py:64`). | One row per measurable scope (`all_models`, `model:*`, `all_products`, `product:*`) (`README.md:363-366`, `interpretation.ts:205-219`). | Differ: we key by catalog Meter; they key by provider scope. Field name `lane` is not a Lane (`rank.py:151-152`). |
| Window | `window` | 5-hour or weekly (`CONTEXT.md:92-93`). `binding` = tighter of the two (`usage.py:53-56`). | `id`/`kind`; Claude `five_hour`+`seven_day`[+model]; Codex duration-identified + `model:<id>:5h/7d`; Grok `credits`+`product:*`; agy four grouped windows (`README.md:587-601`). | Agree on min remaining. Differ: they keep model/product/code-review scopes separate; we fold model weekly into `remaining_weekly` (`usage.py:166-169`). |
| Remaining | `effectivePercentRemaining` | `r = min(known remaining fractions)` (`usage.py:51-52`). | `Math.min` of bounding-window `percentRemaining` (`interpretation.ts:569-574`). Stale omits the number (`interpretation.ts:56-64`, `README.md:472`). | Agree on min when fresh. Differ: we still publish `r` from a TTL cache (`usage.py:219-223`); they refuse effective remaining on stale. |
| Pace | `spendPriority` (`selection`) | `pace = remaining_weekly / cycle_left`; `cycle_left = clamp((reset_wk-now)/WEEK, 0.02, 1)`; `WEEK = 7*86400` (`usage.py:33-34`, `usage.py:60-62`). 1.0 on track; >1 unused (`CONTEXT.md:101-104`). Ranking sorts pace desc (`rank.py:205-211`). | Per window: `reserve = percentRemaining - timeRemainingPercent`; `burnMultiple = percentUsed/elapsedPercent` (`pace.ts:68-86`, `README.md:478-481`). Scope scalar: cycle-weighted mean of `percentRemaining/timeRemainingPercent - burnMultiple`, clamp ±100 (`pace.ts:308-359`, `README.md:544-552`). Positive = unused allowance. | Differ. Direction for ranking agrees (prefer unused). Their `pace.status: ahead` means burning faster (`pace.ts:514-520`); our "ahead" means unused. We use weekly only; they weight every bounding window so 5h cannot dominate (`pace.ts:309-313`). We assume 7d even when Grok reports another period (`usage.py:208-212`). |
| Burn rate | `burnMultiple` | Defined as remaining drop across readings (`CONTEXT.md:106-107`). No Python computes it. | Cycle-average from one `generatedAt`; not cached (`pace.ts:84-86`, `cache.ts:430-446`, `test/cache.test.ts:332-357`). | Differ. Neither stores a history series. Their figure is one-snapshot; ours is specified and unimplemented. |
| Gate | `runway` / `usableRunwaySeconds` | Lowest remaining that still takes a job (`CONTEXT.md:99-100`). Rank: `r < routing.gate` (default 0.1) (`rank.py:139`, `rank.py:176-179`). Unknown `r` never vetoes (`rank.py:176`, `test_rank.py:286-289`). | `exhausted_now` / `projected_exhaustion` / `through_reset` / `unknown`; finite seconds only for the first two (`pace.ts:107-245`, `README.md:519-524`). Advisory; "never overrides runway" as completion-risk (`types.ts:146-147`). | Differ. We threshold Remaining. They publish time-to-empty. No Gate counterpart. |
| Margin | (none) | Steal if later pace ≥ pick pace + `routing.margin` (`CONTEXT.md:109-111`, `rank.py:215-222`). | Explicitly not a router (`README.md:565-566`, `VISION.md:15-20`). `models --sort runway` is an opt-in comparator (`models.ts:27-46`). | No counterpart. Routing-only. |
| meter weight | (none) | Catalog number; "feeds the report, not ranking" (`CONTEXT.md:89-90`). Validated (`catalog.py:369-372`). Unused by `rank.py` and `report.py`. Spec: future capacity, recorded not built (`2026-09-08-delegate-redesign.md:87`). | No per-job weight. | No counterpart. Catalog-only on our side. |
| unknown probe | `attention` + no `quota[]` row; `selection.status: unknown` | CLI absent / timeout / parse fail → `r`/`pace` None, `status: unknown`, exit 0 (`usage.py:21-22`, `usage.py:74`, `usage.py:116`). Rank sorts last, never blocks (`rank.py:206`, `SKILL.md:32`). | Unknown/stale scope omitted from `quota[]`; named in `attention[]`; `spendPriority` literal `unknown`, never `0` (`README.md:392`, `render.ts:157-158`, `pace.ts:321-323`). | Agree: no invented number for ranking. Differ: they keep a structured reason/remedy (`advice.ts:14-57`); we put a `note` string (`usage.py:70`). |

`limitedBy` ↔ our `binding` (`usage.py:53-56` vs `interpretation.ts:575-580`). `confidence` (`early` if elapsed < 10%, else `established`, `pace.ts:14-17`, `pace.ts:98-99`) has no delegate counterpart.

## Per-provider probe comparison

| Harness | Source we read | Source they read | Windows we resolve | Windows they resolve | Auth | Staleness | Failure |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Claude | `claude -p --permission-mode plan --output-format json /usage` (`usage.py:151`). Regex on prose (`usage.py:155-169`). Reset text `Mon D at H:MMam tz` (`usage.py:132-147`). | `GET https://api.anthropic.com/api/oauth/usage` plus profile (`claude.ts:48-49`). Credentials: `.credentials.json` then macOS Keychain (`README.md:633-635`). `limits[]` preferred over fixed fields (`claude.ts:785-802`). | `Current session` + `Current week (all models)` + `Current week (<model>)` folded as `min(all-models, model)` (`usage.py:158-169`). | `five_hour`, `seven_day`, optional `seven_day_opus`/`extra_usage`, `model:<slug>` (`README.md:590-591`). Account windows bound every model (`interpretation.ts:185-219`). | We: CLI session. They: oauth/keychain; `--allow-keychain-prompt`; `claude doctor` only as delegated refresh, never as the probe (`README.md:662-663`, `AGENTS.md:63`). | We: 10 min TTL served as current (`usage.py:31`, `usage.py:219-223`). They: cache `0600`, context-scoped, pace not stored; stale ⇒ effective unknown (`cache.ts:43`, `cache.ts:160-178`, `interpretation.ts:51-64`). | We: `note="probe failed"`, unknown row (`usage.py:152-154`). They: 401 vs 403 distinguished; Keychain deny preserves cache, does not claim sign-out (`README.md:447-448`, `README.md:664`). |
| Codex | `codex app-server` JSON-RPC `account/rateLimits/read` (`usage.py:76-91`). `primary`/`secondary` by `windowDurationMins` ≥ 24h (`usage.py:97-103`). | HTTP `chatgpt.com/backend-api/wham/usage` then `.../codex/usage` (`codex.ts:46-48`); then Pi `openai-codex`; then `codex -s read-only -a untrusted app-server` (`README.md:669-687`, `codex.ts:281-288`). | One 5h + one weekly (`usage.py:103-104`). | Exact 18000s / 604800s as `five_hour`/`weekly`; extra `model:<id>:5h/7d`, `code_review_*`; unfamiliar durations stay honest (`README.md:593`). Inherited zero vs live model windows ⇒ `boundConflict` (`interpretation.ts:497-554`, `CHANGELOG.md:45`). | We: whatever the running CLI uses. They: `auth.json` OAuth only (no API key); stored expiry advisory (`README.md:672-675`). CLI RPC is also their refresh (`README.md:686`). | Same TTL vs labelled stale. Codex cache identities must match (`README.md:811`, `test/cache.test.ts:58`). | We: exception → unknown (`usage.py:105-106`). They: source handover on credential failure only; transport failure does not switch (`AGENTS.md:30`). |
| Grok | `grok agent stdio` then `_x.ai/billing` (`usage.py:182-199`). `creditUsagePercent` missing ⇒ 0% used (`usage.py:173-178`, `usage.py:203-205`). | HTTP `grok.com/grok_api_v2.GrokBuildBilling/GetGrokCreditsConfig` (`grok.ts:42-43`). Auth: `~/.grok/auth.json` then Pi `xai` (`README.md:637`). Model-catalog liveness if consumer billing rejects (`README.md:708-712`). Refresh delegate: `grok models` (`README.md:711`, `grok.ts:108-115`). | One rolling meter into weekly; no 5h (`usage.py:210-212`). Period type is noted, not used for cycle length. | Shared `credits` + `product:<slug>` (`interpretation.ts:277-307`, `grok.ts:62-69`). Pace from `startsAt`/`resetsAt` (`README.md:595`). | We launch an agent stdio session. They never start `grok agent`; only `grok models` (`README.md:714`, `README.md:793`). Soft expiry is `expired_refreshable`, not sign-out (`README.md:441-442`). | We cache the derived weekly pace. They reject legacy `api` snapshots (`README.md:811`). | Missing percent = 0 used (`usage.py:205`) vs their proto3-zero rule only when a valid current period is present (`README.md:596`). |
| agy | `agy --print /usage --output-format json` (`usage.py:115`). Groups → `gemini` / `claude-gpt` (`usage.py:122-128`). | Loopback `RetrieveUserQuotaSummary` on 127.0.0.1 first, then the same print command (`agy.ts:28-29`, `agy.ts:42`, `agy.ts:98-125`, `README.md:739-742`). No credential files (`README.md:642`). | 5h + weekly per group; `r` and 7d pace invented (`usage.py:49-62`). | `gemini_5h`, `gemini_weekly`, `claude_gpt_5h`, `claude_gpt_weekly` (or `model:<slug>`). Combined bound unknown; pace unknown (`interpretation.ts:121-126`, `README.md:600`). | We: CLI present. They: current-user process table, then CLI print (`README.md:740-742`). | Same TTL vs labelled stale. | We: `probe failed` / `no groups` (`usage.py:116`, `usage.py:129`). They: unresolved windows in `attention[]` (`README.md:56-59`). |

quota-axi HTTP for Claude/Codex/Grok honors `HTTP_PROXY` (`README.md:287`). Timeouts: 15s HTTP, shorter RPC (`README.md:286`); we use 60s Claude, 90s agy, 20–25s RPC (`usage.py:79`, `usage.py:115`, `usage.py:151`, `usage.py:186`).

## What quota-axi does better

1. **Fail-closed derivations.** Unknown windows make the whole scope unmeasurable; `0` is never a stand-in (`pace.ts:321-323`, `render.ts:157-158`). We treat missing Grok percent as 0 used (`usage.py:205`) and serve TTL numbers as live (`usage.py:219-223`). Ranking would stop treating a stale or guessed 0 as Remaining.

2. **Cycle evidence instead of a 7-day constant.** They use `startsAt`+`resetsAt` or trusted `windowSeconds` (`pace.ts:458-511`, `README.md:501-505`). We divide every weekly reset by `WEEK` (`usage.py:33`, `usage.py:60-62`), including Grok periods that are not weekly (`usage.py:208-212`) and agy (`usage.py:128`). Pace/Margin steals on Grok and agy are then wrong near a non-7d reset.

3. **Scope-weighted selection.** `spendPriority` weights windows by `cycleSeconds` so a 5h session cannot dominate a week (`pace.ts:309-359`, `README.md:551`). We drop 5h from Pace on purpose (`usage.py:10-12`) but still Gate on `min(5h, weekly)` (`usage.py:51-57`, `rank.py:176`). Ranking should keep 5h as Gate/runway and use a weekly-or-weighted scalar for steal, not one mixed `r`.

4. **Runway as completion risk.** Earliest projected empty-before-reset, or `through_reset` (`pace.ts:107-245`). We have `rollover_soon` only when already unavailable and reset ≤ 30 min (`usage.py:35`, `usage.py:58`). A steal onto a meter that empties before the job timeout would be rejected if ranking consumed `usableRunwaySeconds`.

5. **Stale is not current.** Effective remaining/pace/selection become unknown when `state.stale` (`interpretation.ts:31-33`, `interpretation.ts:51-64`, `test/interpretation.test.ts:79-114`). We re-read a cache younger than 10 min as the live document (`usage.py:219-223`, `rank.py:330-340`). `report.py` then ranks that envelope (`report.py:555`).

6. **Claude without a prompt.** First-party usage API + `limits[]` (`claude.ts:48`, `claude.ts:785-802`). We run `claude -p /usage` (`usage.py:151`) while claiming zero tokens (`usage.py:13`). Their tree forbids a Claude CLI probe because it spends the meter (`AGENTS.md:63`). Ranking would see Fable as its own scope instead of `min(all-models, model)` stuffed into `remaining_weekly` (`usage.py:166-169` vs `interpretation.ts:211-214`).

7. **Codex extra limits and bound conflicts.** `additional_rate_limits` / `rateLimitsByLimitId` (`codex.ts:612-636`, `CHANGELOG.md:45`). We keep two positional windows (`usage.py:97-103`). A zeroed base weekly would Gate every Codex lane here (`rank.py:176`); they publish `boundConflict` and leave the model scope unknown (`interpretation.ts:536-554`).

8. **Structured auth and attention.** `authStatus`, `reason`, `remedyCommand`, `degradedSources` (`types.ts:270-293`, `advice.ts:38-57`). We fold failure into `note` (`usage.py:70`) and always exit 0 (`usage.py:22`). `limits` cannot tell "signed out" from "timeout".

9. **Cache hygiene.** `0600`, no secrets, no derived pace, context id for Claude (`cache.ts:160-178`, `test/cache.test.ts:299-357`). We `json.dump` with default perms (`usage.py:227-233`) and persist `pace`/`status`/`gate` (`usage.py:244-245`).

10. **agy honesty.** Combined remaining refused (`interpretation.ts:121-126`). We compute `r` and a 7d pace from grouped buckets (`usage.py:121-128`). agy-gemini can steal on a number they would not publish.

## What the delegate skill does that quota-axi does not, or should not copy

**Strengths (keep).**

- Routing: Floor/Ceiling, Order, Pace sort, Margin steal, Pick (`rank.py:9-38`, `SKILL.md:32`, `routing.json:25-26`). quota-axi must not grow this (`VISION.md:65`, `README.md:565-566`).
- Catalog Meters and `meter_weight` as lane properties (`lanes.json:3-33`, `lanes.json:41`). Their model-kb is editorial buckets, not a dispatch catalog (`model-kb.ts:11-14`).
- Project `routing.json` override (`SKILL.md:17`, `CONTEXT.md:58-59`).
- Ledger + run cost: `events.py` meter/dispatch records (`events.py:36-45`); `report.py cost` / `runs.jsonl` (`report.py:14-18`, `report.py:217-219`). They report subscription windows, not per-run tokens.
- Unknown meter never blocks a Pick (`test_rank.py:286-289`, `SKILL.md:32`). They omit the number; they do not select a worker.

**The three-gate problem (not a strength).**

`usage.GATE = 0.10` stamps `status` into the cache (`usage.py:32`, `usage.py:57`). `rank_range` uses `routing.gate` (`rank.py:139`, `rank.py:176`). `report.py:206` prints "under 10%"; `--eligible` keeps `status == "ok"` (`report.py:175`); statusline ORs `remaining_weekly <= gate` with `status == "unavailable"` (`report.py:627`). Reviews: grok46 Finding 2, astra Finding 1. Spec still gates on `remaining_weekly` (`2026-09-08-delegate-redesign.md:94`); implementation gates on `r` (`test_rank.py:262`). quota-axi has one aggregation (`interpretation.ts:518-584`) and does not encode eligibility.

**Do not copy.** npm `update`, `--tui` as a product, Cursor/Copilot/Kimi/Z.AI/Alibaba/OpenCode Go adapters, editorial `models` intelligence buckets, Keychain prompt on the rank path, delegated refresh while Claude Code is the orchestrator (`README.md:767`: live Claude process skips `claude doctor`; a rank-time doctor would still be a second holder).

## Improvement opportunities

Ranked by value over effort. Size S/M/L.

1. **One Gate predicate.** Stop encoding eligibility in `usage.status`. Rank, `limits --eligible`, and statusline consume `routing.gate` on validated Remaining. File: `usage.py`, `rank.py`, `report.py`. Size: S. Reviews: grok46 F2, astra F1. Tests: `test_rank.py` cases 4–5 (`test_rank.py:212-270`); `test_report.py` `--eligible` and statusline ✗ (`test_report.py:114`, `test_report.py:310`). Add a project Gate ≠ 0.10 fixture.

2. **Replace assumed `WEEK` with trusted cycle length; keep weekly-only Pace.** Use `windowSeconds` or `startsAt`/`resetsAt` when the probe supplies them; drop `CYCLE_FLOOR` inflation or match their unmeasurable-near-reset rule (`pace.ts:30-35`). File: `usage.py` `lane()`. Size: M. Tests: `test_usage_reset.py` `lane()`; `test_rank.py` steal (`test_rank.py:172-205`).

3. **Do not treat TTL cache as live Remaining.** Serve cached windows only as diagnostics, or recompute Pace at read time from stored resets (they recompute, never cache Pace: `README.md:509`, `cache.ts:430-446`). File: `usage.py` `load_cache`, `rank.load_cached_usage`. Size: M. Review: grok46 F3. Tests: `test_usage_reset.py` cache load (`test_usage_reset.py:98-103`); `test_rank.py` case 21 (`test_rank.py:858-874`).

4. **Add runway next to Pace for steal.** Reject a steal when `usableRunwaySeconds` is below the lane timeout, or when status is `projected_exhaustion` and the pick is `through_reset`. File: `rank.py` steal loop (`rank.py:215-222`). Size: M. Tests: `test_rank.py` steal cases.

5. **Claude probe off the prompt path.** Read oauth usage (or map quota-axi JSON) so Fable is a scope, not folded weekly. File: `usage.py` `probe_claude`. Size: L. Tests: keep `claude_reset` until the prose path dies (`test_usage_reset.py:27-41`); add a `limits[]` fixture.

6. **Share `meter_observations` and one cache path.** Statusline and limits must not `json.load` a raw envelope (`report.py:538-544`, `report.py:600`). `report.CACHE` drops `CONSULT_CACHE` (`report.py:38` vs `usage.py:37`). Size: S. Reviews: grok46 F3/F11, astra F1. Tests: `test_rank.py` case 21; `test_report.py` malformed-cache / missing-cache (`test_report.py:321-322`).

7. **Rename the observation key to the Meter.** Stop overloading `lane` (`usage.py:64`, grok46 F7). File: `usage.py`, `rank.py:151`, `report.py:600`. Size: S. Tests: `test_usage_reset.py`, `test_rank.py`, `test_report.py`.

8. **agy: unknown combined bound.** Do not emit Pace/`r` as if windows jointly bind (`interpretation.ts:121-126`). File: `usage.py` `probe_agy`/`lane()`. Size: S. Tests: `test_usage_reset.py`; `test_rank.py` unknown-last (`test_rank.py:273-289`).

9. **Codex extra limits + boundConflict.** Parse `rateLimitsByLimitId`; do not Gate a model scope on a contradicted base zero. File: `usage.py` `probe_codex`. Size: M. Tests: new fixture beside `test_usage_reset.py`; `test_rank.py` gate-on-`r` (`test_rank.py:248-262`).

10. **Structured probe failure.** Carry `authStatus`/`reason` instead of `note`; never write `status` from a fixed GATE. File: `usage.py` cache document. Size: M. Tests: `test_usage_reset.py` ledger shape (`test_usage_reset.py:89-96`); `test_events.py`.

## Adoption options

**(a) Keep our probes, borrow the derivations.** Remove from our code: `WEEK` constant, `GATE` stamped into cache, `score` (unused by rank: `usage.py:9` vs `rank.py:155`). Add: port of `computeWindowPace` / `summarizeEffectiveSelection` / `computeEffectiveRunway` into `usage.py` or a sibling module. No npm. Failure modes: our Claude/Grok sources stay weaker; cycle fields missing from a probe still force unknown Pace (correct). Schema stays ours.

**(b) Run quota-axi as the probe backend behind `usage.py`.** Remove the four `probe_*` functions. Add: Node ≥22.19 (`package.json:57-58`), `npx`/global `quota-axi`, schemaVersion 5 (`types.ts:297-299`; already bumped in tree), macOS Keychain grant (`README.md:28-31`), possible `claude doctor` / `grok models` during a read (`README.md:746-757`), 0.1.x churn (`CHANGELOG.md:1-16`). Map JSON scopes onto catalog Meters (`claude` `model:fable` → `claude-fable`, `all_models` → `claude-general`, `agy` unresolved → unknown). Failure modes: rank blocked on npm/network/keychain; delegated refresh races the orchestrator (`README.md:767`); agy has no combined remaining so every agy lane becomes unknown; `--profile-only` would be required for delegate's Codex home (`README.md:321-329`, `delegate.py:425-437`) or the probe reads `~/.codex` not `CODEX_HOME`.

**(c) Both in a transition.** Keep `probe_*` as writer of today's cache. Add a mapper from `quota-axi --json --provider claude,codex,grok,agy` into a parallel document; report can shadow; rank stays on (a) until the mapper matches `test_rank.py`. Failure modes: two numbers on one statusline; mapper lag when schemaVersion moves.

**Recommendation: (a).** Ranking cannot take npm, a Keychain prompt, or schemaVersion 5 as a live dependency. The three-gate bug and the 7-day Pace formula are in our tree regardless of probe source. First-party Claude/Grok HTTP can land later as a probe swap inside `usage.py` without importing the CLI. Do not enable delegated refresh on the rank path.

## Open questions

1. Does `claude -p /usage` spend Max quota? **Recommend:** treat it as spend; quota-axi's tree already does (`AGENTS.md:63`). Swap the probe before copying more regex.

2. Should steal use `spendPriority` (all bounding windows) or weekly-only Pace? **Recommend:** weekly-only Pace for steal (`usage.py:10-12`); 5h remains Gate/runway only.

3. Gate on Remaining vs on runway? **Recommend:** keep Gate on Remaining; add runway as a second veto against the lane timeout (item 4).

4. Pin quota-axi as an optional shadow binary? **Recommend:** no pin until (a) lands; if shadowed later, pin 0.1.44 / 9c7d135 and `--no-credential-refresh`.

5. Invent an agy combined bound from gemini 5h+weekly? **Recommend:** no. Follow `unknownSemantics` (`interpretation.ts:121-126`). agy-gemini unknown-last until a vendor joint bound is shown.
