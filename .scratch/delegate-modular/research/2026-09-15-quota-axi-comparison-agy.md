# Comparison: Delegate Usage Metering vs. quota-axi

## Reference in brief

quota-axi (release 0.1.44, commit 9c7d135 of 2026-09-15) is an npm CLI that reports local LLM quota windows in an AXI-shaped call (`README.md:13-19`, `package.json:2-3`).
Its architecture separates into four layers:
1. Provider adapters discover local credentials, auth runtimes, or Keychain items, querying first-party endpoints or local loopbacks (`README.md:267-279`, `src/providers/index.ts:18`).
2. A normalized schema model (`schemaVersion: 5`, `ProviderQuota`) normalizes heterogeneous vendor payloads into uniform windows and states (`README.md:351-358`, `src/types.ts:250-280`).
3. Pure derivation functions compute cycle-average window pace, effective availability across bounding windows, usable runway, and the `spendPriority` selection scalar (`src/pace.ts:48-105`, `src/pace.ts:107-246`, `src/pace.ts:324-360`, `src/interpretation.ts:16-35`).
4. Output tiers separate concise decision blocks (default TOON/JSON) from audit details (`--full`) and an interactive terminal UI (`--tui`) (`README.md:332-348`, `README.md:394-410`, `src/render.ts:39-75`).
Stated non-goals: quota-axi never routes jobs, never recommends models or providers, never proxies traffic, never logs in, never drives browsers or imports cookies, and never mints or exchanges OAuth refresh tokens (`README.md:19`, `VISION.md:16-20`, `VISION.md:24-33`, `VISION.md:67`).

## Concept map

| Delegate term | quota-axi counterpart | Delegate rule & file:line | quota-axi rule & file:line | Comparison |
| --- | --- | --- | --- | --- |
| **Meter** | `provider` + `scope` / `QuotaWindow` | One subscription quota string `f"{harness}-{meter}"` or `harness` shared by lanes (`CONTEXT.md:85`, `stow/delegate/.config/delegate/lanes.json:3-34`, `agents/skills/delegate/scripts/usage.py:64`). | `ProviderId` (`src/types.ts:1-11`) with discrete `QuotaWindow` items (`src/types.ts:178-192`) evaluated under named `scope` (`all_models`, `model:<slug>`, `all_products`, `tools`) (`src/types.ts:195`, `src/interpretation.ts:121-270`). | Differ. Delegate couples a lane to a single combined meter row (`usage.py:64`). quota-axi isolates raw provider windows from evaluation scopes (`src/types.ts:195`). |
| **Window** | `QuotaWindow` (`window`) | Hardcoded 5-hour and weekly quota periods (`agents/skills/delegate/scripts/usage.py:49-56`, `CONTEXT.md:92`). | `QuotaWindow` with `kind` (`session`, `weekly`, `monthly`, `model`, `credits`, `unknown`), explicit `windowSeconds`, `startsAt`, `resetsAt` (`src/types.ts:178-192`, `README.md:451-455`). | Differ. Delegate hardcodes exactly two periods (`5h`, `weekly`). quota-axi supports arbitrary heterogeneous windows with explicit durations and cycle boundaries. |
| **Remaining** | `effectivePercentRemaining` & `limitedBy` | `r = min(known)` between `remaining_5h` and `remaining_weekly`, 0.0..1.0 float (`agents/skills/delegate/scripts/usage.py:51-52`, `CONTEXT.md:95`). | `effectivePercentRemaining = Math.min(...remaining)` over `boundedBy` windows for that scope, integer 0..100 (`src/interpretation.ts:569`, `src/types.ts:197`). Bounding window IDs reported in `limitingWindowIds` (`src/interpretation.ts:575-580`, `README.md:365`). Undefined if any bound is unknown or on `boundConflict` (`src/interpretation.ts:535-559`). | Agree on `min` aggregation; differ on type (0..1 float vs 0..100 integer) and strictness (quota-axi yields unknown on any missing bound or conflict; delegate takes `min` of whatever known windows exist). |
| **Pace** | `QuotaPace.reservePercentPoints` / `burnMultiple` / `EffectivePaceSummary` | `pace = round(weekly / cycle_left, 3)` where `cycle_left = min(1.0, max(0.02, (reset_wk - NOW) / 604800))` (`agents/skills/delegate/scripts/usage.py:59-62`, `CONTEXT.md:102`). Higher means quota will expire unspent. | `reservePercentPoints = percentRemaining - timeRemainingPercent` (signed residual capacity vs linear clock, ±1% deadband for on_pace) (`src/pace.ts:70-74`, `src/types.ts:74-78`). `burnMultiple = percentUsed / elapsedPercent` (`src/pace.ts:85`, `src/types.ts:80`). | Differ. Delegate uses ratio of remaining quota to remaining time (1.0 = on track, >1.0 = surplus). quota-axi computes linear reserve difference in percentage points (`reservePercentPoints`), normalized burn speed (`burnMultiple`), and categorical status (`ahead`, `on_pace`, `behind`, `unknown`). |
| **Burn rate** | `runway` (`usableRunwaySeconds`, `projectedExhaustedAt`, `projectionConfidence`) | Defined as rate remaining falls across readings over time (`CONTEXT.md:106`); not computed in code (`agents/skills/delegate/scripts/usage.py:9-12`). | Derived from cycle-average burn: `burnPerMs = percentUsed / elapsedMs`, projecting `msToExhaust = remainingBudget / burnPerMs` (`src/pace.ts:88-102`). Aggregated into `usableRunwaySeconds` and `projectedExhaustedAt` with `confidence` (`early` if elapsed < 10%, else `established`) (`src/pace.ts:18`, `src/pace.ts:98-100`, `src/pace.ts:237-246`). | Differ. Delegate names the concept but implements no rate calculation. quota-axi computes cycle-average burn rate and finite exhaustion runway in seconds. |
| **Gate** | `runway.status` (`exhausted_now`, `projected_exhaustion`) & `attention` | Lowest remaining fraction a meter may have and still take a job: `r < routing.gate` (default 0.10) vetoes lane in `agents/skills/delegate/scripts/rank.py:176` (`CONTEXT.md:99`, `stow/delegate/.config/delegate/routing.json:26`, `agents/skills/delegate/scripts/usage.py:32`). | No gating counterpart. Quota-axi is data only; it reports completion-risk facts (`exhausted_now`, `usableRunwaySeconds`, or `attention` warnings) but never filters or vetoes (`README.md:19`, `VISION.md:16`, `src/types.ts:95-109`). | Delegate enforces routing gates; quota-axi has no counterpart by design. |
| **Margin** | `selection` (`spendPriority`) | Surplus pace required for a lower-priority or higher-tier lane to steal pick: `r['pace'] >= pick_row['pace'] + margin` (`agents/skills/delegate/scripts/rank.py:33-38`, `agents/skills/delegate/scripts/rank.py:220`, `stow/delegate/.config/delegate/routing.json:25`, `CONTEXT.md:109`). | No routing/steal counterpart. Closest data signal is `spendPriority`: cycle-weighted mean of `(percentRemaining / timeRemainingPercent - burnMultiple)` clamped to [-100, 100] (`src/types.ts:133-158`, `src/pace.ts:312-360`). | Delegate uses margin as a selection threshold in ranking; quota-axi computes a non-prescriptive comparative data scalar. |
| **meter weight** | None | Relative consumption weight of a lane against its meter, used for plan cost calculation (`stow/delegate/.config/delegate/lanes.json:41`, `agents/skills/delegate/scripts/report.py:153-164`, `CONTEXT.md:89`). | No counterpart. Quota-axi does not model lanes, job sizes, or consumption weights (`README.md:291`, `VISION.md:67`). | Delegate-only concept; no counterpart in quota-axi. |
| **unknown probe** | `state.status` (`unavailable`, `auth_required`, `error`), `QuotaPace.status: "unknown"`, `attention[]` | Missing CLI, timeout, or probe failure sets `r: None`, `pace: None`, `status: "unknown"`; ranked last among eligible lanes (`agents/skills/delegate/scripts/usage.py:21-22`, `agents/skills/delegate/scripts/usage.py:57`, `agents/skills/delegate/scripts/rank.py:206-211`). | Fine-grained taxonomy: `state.status` (`unavailable`, `auth_required`, `rate_limited`, `error`), `authStatus` (`usable`, `expired_refreshable`, `unusable`), `QuotaPaceReason` (`stale`, `missing_usage`, `missing_cycle`, etc.), and `attention[]` diagnostic entries (`src/types.ts:36-48`, `src/types.ts:56-64`, `README.md:373-384`). | Agree on fail-safe unknown propagation without crashing; quota-axi provides structured diagnostics and recovery commands rather than generic "unknown". |

## Per-provider probe comparison

| Provider | Side | Sources read | Windows resolved | Auth handling | Staleness handling | Failure handling |
| --- | --- | --- | --- | --- | --- | --- |
| **Claude** | **delegate** | CLI execution: `claude -p --permission-mode plan --output-format json /usage` (`agents/skills/delegate/scripts/usage.py:151`). | Regex on stdout: `Current session` (5h) and `Current week (all models)` (weekly), plus per-model weekly (`agents/skills/delegate/scripts/usage.py:155-169`). | Relies on ambient CLI session auth. No token or Keychain inspection (`agents/skills/delegate/scripts/usage.py:151`). | File cache `~/.cache/delegate/usage.json` with 10-minute TTL (`agents/skills/delegate/scripts/usage.py:31,223`). | Regex failure or non-zero exit sets `note="probe failed"` or `"absent"` on single row (`agents/skills/delegate/scripts/usage.py:150-154`). |
| | **quota-axi** | Direct HTTPS API `https://api.anthropic.com/api/oauth/usage` (`src/providers/claude.ts:48`). Bearer token from `$CLAUDE_CONFIG_DIR/.credentials.json`, `~/.claude/.credentials.json`, or macOS Keychain `Claude Code-credentials[-<hash>]` (`src/providers/claude.ts:12-18`, `src/lib/claude-profile.ts:14-118`). | `five_hour`, `seven_day`, `seven_day_opus`, `extra_usage`, and model windows (`model:<slug>`) from response `limits` (`src/providers/claude.ts:59-63`, `README.md:591-592`). | Checks token expiry; enforces Keychain access marker without prompting unless `--allow-keychain-prompt`; on HTTP 401 runs delegated refresh `claude doctor` if refreshable and no live process (`src/providers/claude.ts:40-45`, `README.md:663,754`). | Normalized cache in `~/.cache/quota-axi/quotas.json`; stale fallback up to 7 days if from same configuration context ID (`src/cache.ts:88`, `README.md:664,809`). | Structured errors (`keychain_access_required`, `keychain_unreachable`, `credentials_expired`); emits `attention[]` with remedy commands (`README.md:440`, `src/providers/claude.ts:46`). |
| **Codex** | **delegate** | Spawns `codex app-server` subprocess, communicates via JSON-RPC over stdin/stdout, calls `initialize` then `account/rateLimits/read` (`agents/skills/delegate/scripts/usage.py:76-94`). | `primary` and `secondary` mapped to `5h` or `weekly` based on `windowDurationMins >= 1440` (`agents/skills/delegate/scripts/usage.py:98-102`). | Relies on `codex app-server` internal auth (`agents/skills/delegate/scripts/usage.py:76`). | File cache 10-minute TTL (`agents/skills/delegate/scripts/usage.py:31,223`). | Subprocess crash or timeout sets `note="probe failed: ..."` (`agents/skills/delegate/scripts/usage.py:105-106`). |
| | **quota-axi** | Direct HTTPS `https://chatgpt.com/backend-api/wham/usage` or `/codex/usage` using OAuth token from `$CODEX_HOME/auth.json`, `~/.codex/auth.json`, or Pi `auth.json`. CLI RPC fallback `codex -s read-only -a untrusted app-server` (`src/providers/codex.ts:45-54`, `README.md:669-686`). | `five_hour` (18,000s), `weekly` (604,800s), model windows `model:<id>:5h` / `model:<id>:7d`, `code_review_*`, and credits (`src/types.ts:178`, `README.md:593`). | Evaluates JWT expiry; Pi broker reads `auth.json` with 64 KiB cap; CLI app-server fallback automatically acts as delegated refresh by renewing token and rewriting `auth.json` (`src/providers/codex.ts:673-686`). | Normalized cache; validates cached identities (ID, label, duration) before reusing (`src/cache.ts:810`, `README.md:810`). | Fallback chain (auth.json -> Pi -> CLI RPC); marks `degradedSources`; detects `boundConflict` if base limit is 0 but model budget has quota (`src/interpretation.ts:535`, `README.md:460`). |
| **Grok** | **delegate** | Spawns `grok agent stdio` subprocess, calls JSON-RPC `initialize` then `_x.ai/billing` extension method (`agents/skills/delegate/scripts/usage.py:182-198`). | Single `weekly` window (`creditUsagePercent`, `billingPeriodEnd`) (`agents/skills/delegate/scripts/usage.py:203-212`). No 5h window. | Relies on `grok agent stdio` internal auth (`agents/skills/delegate/scripts/usage.py:182`). | File cache 10-minute TTL (`agents/skills/delegate/scripts/usage.py:31,223`). | Subprocess crash or timeout sets `note="probe failed: ..."` (`agents/skills/delegate/scripts/usage.py:213-217`). |
| | **quota-axi** | Direct HTTPS POST `https://grok.com/grok_api_v2.GrokBuildBilling/GetGrokCreditsConfig` (gRPC-Web) using token from `$GROK_AUTH_JSON`, `$GROK_HOME/auth.json`, or Pi `auth.json` (`src/providers/grok.ts:42-52`, `README.md:704-709`). | Shared `credits` window, product-scoped `product:<slug>` windows, prepaid balance (`src/providers/grok.ts:62-70`, `README.md:596`). | Direct token inspection; tests stored-expired tokens with read-only model probe (`https://cli-chat-proxy.grok.com/v1/models`); if rejected and refreshable, delegates refresh via `grok models` (`src/providers/grok.ts:45`, `README.md:711,756`). | Normalized cache; only caches snapshots from `web` operation; drops legacy `api` snapshots (`src/cache.ts:811`, `README.md:811`). | Falls back from CLI auth to Pi `xai`; distinguishes `expired_refreshable` from unauthenticated sign-out; provides `remedyCommand: grok` (`README.md:441-443`). |
| **Antigravity (`agy`)** | **delegate** | Spawns `agy --print /usage --output-format json` with 90s timeout (`agents/skills/delegate/scripts/usage.py:115`). | `5h` and `weekly` buckets under `gemini` and `claude-gpt` groups (`agents/skills/delegate/scripts/usage.py:123-128`). | Relies on `agy` CLI internal session (`agents/skills/delegate/scripts/usage.py:115`). | File cache 10-minute TTL (`agents/skills/delegate/scripts/usage.py:31,223`). | Non-zero exit code or JSON parse failure sets `note="probe failed"` (`agents/skills/delegate/scripts/usage.py:116-120`). |
| | **quota-axi** | Scans processes for running Antigravity app or CLI, finds 127.0.0.1 port, queries loopback `/RetrieveUserQuotaSummary` (3s timeout) (`src/providers/agy.ts:28-40`). Falls back to `agy --print /usage --output-format json` (15s timeout) (`src/providers/agy.ts:40-42`). | `gemini_5h`, `gemini_weekly`, `claude_gpt_5h`, `claude_gpt_weekly`, or model-scoped `model:<slug>` windows (`src/providers/agy.ts:28-35`, `README.md:600`). | Reads runtime CSRF token from running process command line or environment when available (`src/providers/agy.ts:50-53`, `README.md:742`). | Cache in quotas.json; does not calculate pace/burn-rate because v1 payload lacks history (`src/providers/agy.ts:744`, `README.md:600`). | If loopback fails, runs print command fallback; if both fail, records failure attempt (`src/providers/agy.ts:95-103`). Note: README:600 claims model windows are resolved, but `interpretation.ts:122-126` sets semantics to `unknown` with no effective remaining. |

## What quota-axi does better

1. **Direct HTTPS and Loopback Probing vs. Heavy CLI Subprocesses**:
   - Evidence: Delegate spawns heavy CLI processes for every probe (`claude` timeout 60s, `codex app-server` spawns server, `grok agent stdio` launches agent, `agy` runs 90s `--print /usage`) (`agents/skills/delegate/scripts/usage.py:43-216`). Quota-axi performs lightweight HTTPS/loopback requests (15s timeout for HTTP, 2-3s for loopback) by reading local tokens (`src/providers/claude.ts:48`, `src/providers/codex.ts:46`, `src/providers/grok.ts:43`, `src/providers/agy.ts:28-40`).
   - Impact: Delegate meter refresh takes 5–20+ seconds, blocking dispatch and CLI reports. Direct HTTP probes drop refresh latency to <500ms.

2. **Unified Pace & Usable Runway Math with Deadband vs. Fragile Pacing Ratio**:
   - Evidence: Delegate's `pace` is simply `remaining_weekly / ((reset_wk - now) / 604800)` clamped to a denominator floor of 0.02 (~3.4h) (`agents/skills/delegate/scripts/usage.py:59-62`). Near resets, it distorts. It has no deadband for rounding noise, ignores the 5h window completely for pace, and has no concept of finite exhaustion runway (`agents/skills/delegate/scripts/usage.py:9-12,59-63`). Quota-axi computes linear reserve in percentage points (`reservePercentPoints = percentRemaining - timeRemainingPercent`) with a ±1% deadband (`src/pace.ts:12`, `src/pace.ts:72-74`), computes cycle-average burn rate (`burnMultiple`), and evaluates finite usable runway in seconds (`usableRunwaySeconds`, `projectedExhaustedAt`) across *all* bounding windows (`src/pace.ts:85-101`, `src/pace.ts:107-246`).
   - Impact: Delegate's margin steal (`agents/skills/delegate/scripts/rank.py:220`) currently compares a crude ratio that can trigger false steals near weekly reset. Adopting `reservePercentPoints` or `usableRunwaySeconds` provides an honest surplus/exhaustion metric.

3. **Multi-Window Bounding & Scope Semantics vs. Blind `min(5h, weekly)`**:
   - Evidence: Delegate blindly computes `r = min(five_h, weekly)` across all meters (`agents/skills/delegate/scripts/usage.py:51-52`), conflating independent resources with account-wide bounds. Quota-axi tracks explicit window scopes (`all_models`, `model:<slug>`, `tools`) and defines provider-specific semantics (`src/interpretation.ts:96-135,518-585`). It also detects `boundConflict` when a base limit is 0 but model limit has allowance (`src/interpretation.ts:500-516`).
   - Impact: Prevents delegate from incorrectly gating models when an unrelated or inherited window is 0 (such as Codex base limit vs model limit, or Claude model quota vs general quota).

4. **Delegated Token Refresh vs. Silent Failure on Expired Tokens**:
   - Evidence: If Claude or Grok's OAuth access token expires, delegate's CLI command fails or prompts, resulting in `status: "unknown"` or failure (`agents/skills/delegate/scripts/usage.py:152,216`). Quota-axi recognizes `expired_refreshable` tokens and invokes vendor-owned non-interactive refresh delegates (`claude doctor`, `codex app-server`, `grok models`) without touching refresh tokens or prompting (`src/providers/delegated-refresh.ts:57-89`, `README.md:750-782`).
   - Impact: Prevents delegate meters from going dark overnight or during unattended runs when access tokens expire.

5. **Granular Auth & Failure Taxonomy vs. Binary `ok`/`unavailable`/`unknown`**:
   - Evidence: Delegate uses three statuses: `ok`, `unavailable` (if `r < GATE`), `unknown` (if probe failed) (`agents/skills/delegate/scripts/usage.py:57`). Quota-axi provides `state.status` (`fresh`, `stale`, `unavailable`, `auth_required`, `rate_limited`, `error`), `authStatus` (`usable`, `expired_refreshable`, `unusable`), and structured diagnostic reasons (`keychain_access_required`, `unresolved_windows`, `bound_conflict`) (`src/types.ts:36-48`, `README.md:373-384`).
   - Impact: Delegate CLI and statusline can distinguish a rate limit from an auth failure or absent CLI, enabling specific actionable remedies instead of generic "absent" or "unknown" vetoes.

6. **Context-Scoped Cache Validation vs. Monolithic JSON Dump**:
   - Evidence: Delegate dumps all lanes into a single JSON file `~/.cache/delegate/usage.json` (`agents/skills/delegate/scripts/usage.py:37,227-234`). Reading checks only file modification age (`agents/skills/delegate/scripts/usage.py:223`). Quota-axi caches per provider with schema validation and cryptographic configuration-context IDs (e.g. Claude profile and Keychain service hash, Kimi environment hash) so profile switches never serve wrong cached numbers (`src/cache.ts:64-70,88-100`, `README.md:809-812`).
   - Impact: Eliminates cache pollution when switching workspaces, profiles, or accounts.

## What the delegate skill does that quota-axi does not, or should not copy

The delegate skill encompasses capabilities completely outside quota-axi's data-only scope:
1. **Tiered Capability Routing**: `rank_range` selects eligible lanes by floor, ceiling, gate, CLI presence, sorts by `(tier, order, pace, name)`, and evaluates Margin steal (`agents/skills/delegate/scripts/rank.py:123-242`, `CONTEXT.md:51-114`).
2. **Margin Steal Load Balancing**: Steal rule parameter (`routing.margin`, default 0.20) allowing higher-tier or lower-order lanes to take a job if pace exceeds pick by margin (`agents/skills/delegate/scripts/rank.py:220`, `stow/delegate/.config/delegate/routing.json:25`).
3. **Execution Ledger**: Event logging in `events.py` (`ledger.jsonl`) recording `meter`, `dispatch.start`, `dispatch.finish` (`agents/skills/delegate/scripts/events.py:13-75`, `agents/skills/delegate/scripts/delegate.py:401,691`).
4. **Token Cost Tracking**: Token accounting and dollar pricing per run in `report.py:compute_cost` based on lane input/output/cache token pricing (`agents/skills/delegate/scripts/report.py:217-250`, `stow/delegate/.config/delegate/lanes.json:43-48`).
5. **Project Routing Overrides**: Local `.delegate/routing.json` merging classes, project_order, margin, and gate over global config (`agents/skills/delegate/scripts/catalog.py:628-769`, `CONTEXT.md:58-60`).

These are genuine strengths representing delegate's core domain: automated task delegation and cost management. Quota-axi explicitly leaves routing, gating, and execution to consumers (`README.md:19`, `VISION.md:16-20`).

However, the reviews identified architectural flaws in delegate's metering that quota-axi rightly avoids:
- **The Three-Gate Problem** (`.scratch/delegate-modular/research/2026-09-15-deep-modules-review-astra-xhigh.md:102` Finding 1, `...-grok46.md:72` Finding 2):
  Delegate implements Gate in three conflicting places:
  1. `usage.py:32` hardcodes `GATE = 0.10` and sets `status = "unavailable" if r < GATE else "ok"` (`agents/skills/delegate/scripts/usage.py:57`).
  2. `rank.py:139` reads dynamic `routing.gate` (or project override) and checks `r < gate` (`agents/skills/delegate/scripts/rank.py:176`), ignoring `status`.
  3. `report.py:175` filters `status == "ok"` for `--eligible`, while `report.py:206` prints hardcoded "under 10%", and `report.py:627` in statusline checks `(remw <= gate_threshold) or (u_row.get("status") == "unavailable")`.
  If a project sets `gate = 0.05`, a meter at 0.08 is accepted by `rank.py` but stamped `unavailable` by `usage.py`, filtered out by `report.py limits --eligible`, and marked with ✗ on the statusline.
- **Architectural Lesson**: Quota-axi never computes eligibility or gates in its probe or cache layer. It reports pure numbers (`effectivePercentRemaining`, `runway`). Delegate should adopt this separation: strip `GATE` and `status: "unavailable"` from `usage.py`, evaluate `routing.gate` solely in `rank.py`, and have `report.py` consume `rank` observations.

## Improvement opportunities

1. **Unify Gate evaluation in `rank.py` and strip Gate from `usage.py` and `report.py`**
   - File: `agents/skills/delegate/scripts/usage.py`, `agents/skills/delegate/scripts/rank.py`, `agents/skills/delegate/scripts/report.py`
   - Size: S
   - Review finding: Astra Finding 1 (`astra-xhigh.md:102`), Grok Finding 2 (`grok46.md:72`)
   - Test: `agents/skills/delegate/tests/test_rank.py` (cases 4, 5) and `tests/test_report.py`
   - Change: Remove `GATE = 0.10` and `status: "unavailable"` from `usage.py:32,57`. Store raw fractions. Let `rank.py:139,176` be the sole evaluator of `routing.gate`. Have `report.py:175,627` consume `rank` rows.

2. **Route `report.py` statusline and limits through `rank.meter_observations`**
   - File: `agents/skills/delegate/scripts/report.py`
   - Size: S
   - Review finding: Astra Finding 1 (`astra-xhigh.md:102`), Grok Finding 3 (`grok46.md:74`)
   - Test: `agents/skills/delegate/tests/test_rank.py` (case 21) and `tests/test_report.py`
   - Change: Replace raw `json.load` in `report.py:539` with `rank.load_cached_usage` + `rank.meter_observations`, ensuring malformed cache entries degrade cleanly across statusline and limits.

3. **Direct HTTPS and Loopback probes for Claude, Grok, and Antigravity in `usage.py`**
   - File: `agents/skills/delegate/scripts/usage.py`
   - Size: M
   - Review finding: Astra Seams (`astra-xhigh.md:48`), Grok Seams (`grok46.md:30`)
   - Test: `agents/skills/delegate/tests/test_usage_reset.py`
   - Change: Replace subprocess spawning of `claude -p` (60s), `grok agent stdio` (25s), and `agy --print` (90s) with direct reads: Anthropic OAuth usage endpoint (`https://api.anthropic.com/api/oauth/usage`), Grok billing endpoint (`https://grok.com/grok_api_v2.GrokBuildBilling/GetGrokCreditsConfig`), and Antigravity loopback port (`RetrieveUserQuotaSummary`), falling back to CLI only when credentials or loopback ports are absent.

4. **Replace volatile ratio `pace` with linear reserve (`reservePercentPoints`) and deadband**
   - File: `agents/skills/delegate/scripts/usage.py`, `agents/skills/delegate/scripts/rank.py`
   - Size: S
   - Review finding: None (new from quota-axi reference)
   - Test: `agents/skills/delegate/tests/test_usage_reset.py`, `tests/test_rank.py`
   - Change: In `usage.py:61`, replace `pace = round(weekly / cycle_left, 3)` with arithmetic reserve `reserve = round(weekly - cycle_left, 4)` and a 1% deadband (matching `quota-axi/src/pace.ts:12,72`), or guard `cycle_left < 0.05` to prevent false margin steals when weekly reset is imminent.

5. **Add delegated non-interactive credential refresh for Claude and Grok in `usage.py`**
   - File: `agents/skills/delegate/scripts/usage.py`
   - Size: M
   - Review finding: None (new from quota-axi reference)
   - Test: `agents/skills/delegate/tests/test_usage_reset.py`
   - Change: When token probe receives HTTP 401 and refresh token is present in auth store, invoke non-interactive vendor refresh (`claude doctor` for Claude, `grok models` for Grok) as in `quota-axi/src/providers/delegated-refresh.ts:57-89` before retrying probe once.

6. **Separate Meter identity from Lane in usage cache schema**
   - File: `agents/skills/delegate/scripts/usage.py`, `agents/skills/delegate/scripts/rank.py`
   - Size: S
   - Review finding: Grok Finding 7 (`grok46.md:82`), Astra Seams (`astra-xhigh.md:48`)
   - Test: `agents/skills/delegate/tests/test_usage_reset.py`, `tests/test_rank.py`
   - Change: In `usage.py:64`, change `"lane": f"{harness}-{meter}"` to explicitly emit `"meter": meter_id`, avoiding overloading `"lane"` with meter identity when catalog lanes have distinct names like `fable-xhigh@claude`.

7. **Consolidate cache path resolution in a single function**
   - File: `agents/skills/delegate/scripts/usage.py`, `agents/skills/delegate/scripts/rank.py`, `agents/skills/delegate/scripts/report.py`
   - Size: S
   - Review finding: Grok Finding 11 (`grok46.md:90`), Astra Seams (`astra-xhigh.md:48`)
   - Test: `agents/skills/delegate/tests/test_rank.py` (case 20 missing-cache), `tests/test_report.py`
   - Change: Export `get_cache_path()` from `usage.py` (or shared helper) and import in `rank.py:348` and `report.py:38,535`, restoring `CONSULT_CACHE` support in `report.py`.

8. **Calculate finite usable runway (`usableRunwaySeconds`) across all bounding windows**
   - File: `agents/skills/delegate/scripts/usage.py`, `agents/skills/delegate/scripts/rank.py`
   - Size: M
   - Review finding: None (new from quota-axi reference)
   - Test: `agents/skills/delegate/tests/test_usage_reset.py`, `tests/test_rank.py`
   - Change: Derive `usableRunwaySeconds` from `(resetsAt - now)` and burn rate across 5h and weekly windows (`quota-axi/src/pace.ts:238-245`), enabling ranking and statusline to show "exhausted in Xh" instead of simple percentage.

9. **Parse model-specific quota limits and detect `boundConflict` for Codex and Claude**
   - File: `agents/skills/delegate/scripts/usage.py`, `agents/skills/delegate/scripts/rank.py`
   - Size: M
   - Review finding: None (new from quota-axi reference)
   - Test: `agents/skills/delegate/tests/test_usage_reset.py`, `tests/test_rank.py`
   - Change: In `usage.py:95-104`, parse model-specific limits from Codex RPC (`rateLimitsByLimitId`) and Claude `limits`. Detect `boundConflict` when base limit reads 0 but model limit has allowance (`quota-axi/src/interpretation.ts:500-516`), preventing false gate vetoes.

10. **Adopt structured provider state (`authStatus`, `status`, `reason`) in usage cache**
    - File: `agents/skills/delegate/scripts/usage.py`, `agents/skills/delegate/scripts/rank.py`, `agents/skills/delegate/scripts/report.py`
    - Size: S
    - Review finding: None (new from quota-axi reference)
    - Test: `agents/skills/delegate/tests/test_usage_reset.py`, `tests/test_rank.py`
    - Change: Replace ad-hoc `note="probe failed: ..."` strings (`usage.py:106,120,154,216`) with structured `state: {status: "fresh"|"stale"|"unavailable"|"auth_required", reason: ...}` (matching `quota-axi/src/types.ts:36-43`), enabling `rank.py` and `report.py` to give exact veto reasons (e.g. `vetoed:auth_required` vs `vetoed:cli_missing`).

## Adoption options

- **Option (a): Keep our probes and borrow the derivations.**
  - *What it removes*: Eliminates the fragile pace ratio calculation, ad-hoc status checks, and the three-gate discrepancy across `usage.py`, `rank.py`, and `report.py`.
  - *What it adds as a dependency*: Zero external dependencies. Stays pure Python 3 standard library (`json`, `subprocess`, `time`, `datetime`). No npm, no Node.js runtime, no Keychain prompts, no version churn, and no schema synchronization.
  - *Failure modes*: We retain ownership of probe maintenance when vendor wire formats drift (e.g. Codex app-server RPC schema, Claude CLI output regex, Grok billing RPC).
- **Option (b): Run quota-axi as the probe backend behind `usage.py` and map its JSON.**
  - *What it removes*: Removes ~150 lines of vendor probe code in `usage.py` (`probe_codex`, `probe_agy`, `probe_claude`, `probe_grok`, `claude_reset`). Outsources reverse-engineering of vendor endpoints, tokens, and refresh delegates.
  - *What it adds as a dependency*: Requires Node.js >= 22.19 (`README.md:219`). Requires npm/pnpm package installation or `npx` network execution. Requires one-time `--allow-keychain-prompt` for macOS Keychain access to read Claude tokens (`README.md:28-30,313`). Tight coupling to quota-axi's schema version churn (`schemaVersion: 5`, `README.md:351`).
  - *Failure modes*: Node/npx execution latency (spawning Node on every refresh adds 200–800ms); npm network failure if using npx; macOS Keychain prompt blocks non-interactive agent sessions if unapproved; quota-axi version upgrade changes schema; Antigravity in quota-axi reports `unknownSemantics` with no effective remaining percentage (`src/interpretation.ts:122-126`), which would break delegate ranking unless `usage.py` synthesizes `r` from raw windows.
- **Option (c): Both in a transition.**
  - *What it removes*: Removes nothing immediately; maintains duplicate probe paths.
  - *What it adds as a dependency*: Dual maintenance overhead, two distinct probe behaviors, diverging pace and remaining values depending on whether Node/quota-axi is installed.
  - *Failure modes*: Split-brain behavior between environments with and without quota-axi; subtle ranking differences across developer machines.

**Recommendation**: Adopt **Option (a)** (keep our probes and borrow the derivations).
*Reason*: The delegate skill operates inside headless, automated agent sessions where Node 22+ requirements, npm network overhead, macOS Keychain interactive prompts, and quota-axi's omission of Antigravity effective availability (`src/interpretation.ts:122-126`) introduce unacceptable operational fragility and latency. Borrowing quota-axi's clean mathematical derivations (linear reserve, deadband, cycle-average runway, bound conflict logic) directly into Python delivers 90% of the value with zero dependency friction.

## Open questions

1. **Should Antigravity (`agy`) window relationships remain modeled as `min(5h, weekly)` in delegate, given quota-axi marks them `unknownSemantics`?**
   - *Recommended answer*: Keep delegate's `min(5h, weekly)` for each agy bucket (`gemini` and `claude-gpt`). Unlike quota-axi which refuses to combine windows without official proof of joint bounding (`src/interpretation.ts:123-126`), delegate's routing requires a concrete availability bound to schedule work.
2. **Should delegate switch from ratio-based `pace` (`remaining / cycle_left`) to quota-axi's arithmetic reserve (`reservePercentPoints`) or `burnMultiple`?**
   - *Recommended answer*: Switch Margin steal evaluation (`agents/skills/delegate/scripts/rank.py:220`) to arithmetic reserve `reserve = remaining_weekly - time_remaining_fraction` with a ±0.01 deadband. This avoids mathematical blowup when `cycle_left` approaches zero near weekly reset.
3. **Should delegate's `usage.py` read macOS Keychain for Claude Code tokens or continue using `claude -p` CLI?**
   - *Recommended answer*: Continue using `claude -p` (or `$CLAUDE_CONFIG_DIR/.credentials.json` when present). Avoid querying macOS Keychain directly via `security` to prevent blocking non-interactive agent sessions on Keychain permission dialogs.
4. **Should delegate adopt `spendPriority` as an alternative to `margin` in ranking?**
   - *Recommended answer*: No. `spendPriority` (`src/pace.ts:347`) weights multi-cycle forfeiture across windows into a scalar [-100, 100], which does not map cleanly to delegate's tiered capability model where Tier and Order take precedence over quota balancing. Keep `margin` as the tier-steal threshold.
5. **How should Codex model-specific quotas (`rateLimitsByLimitId`) be represented in `lanes.json`?**
   - *Recommended answer*: Associate model-specific Codex lanes with a sub-meter key (e.g. `codex-gpt-5.1` vs `codex`), allowing `rank.py` to gate specifically on the model's budget rather than the shared primary bucket.
