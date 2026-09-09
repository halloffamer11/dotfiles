# Delegate redesign: lanes, tiers, trust, and ADS relays

Date: 2026-09-08. Author: toolsmith session (Fable) with Orin. Status: **design agreed, grilling complete; implementation not started.**
Supersedes the Option 1 / Option 2 framing in `2026-09-08-delegate-assessment.md`. Neither option was taken.

Provenance: research in `docs/superpowers/research/2026-09-08-lane-cost.md` and `2026-09-08-lane-benchmarks.md`; selection-rule prototype in `agents/skills/delegate/prototype-lane-selection.html` (throwaway, policy P4); ADS clone used for reading: github.com/amElnagdy/delegate-skills at b781ee2.

## 1. Terms

- **Harness**: a CLI that runs a worker. Four: `claude` (Claude Code), `codex`, `agy`, `grok`.
- **Lane**: one (harness, model, effort) tuple with a record in `lanes.json`. Claude lanes are ordinary lanes.
- **Meter**: one subscription quota, probed by `usage.py`. A lane drains exactly one meter.
- **Class**: a kind of job (`scout`, `mechanical`, `impl`, `review`, `hard-impl`). Each class needs a **tier**.
- **Tier**: capability level 1 (lowest) to 4 (frontier). Set by the human per lane, after reading the benchmark ranking.
- **Trust**: the human's ordering of lanes inside a tier, 1 to 5. Experience, not benchmarks.
- **Pace**: `remaining_weekly / cycle_left` from `usage.py`. 1.0 = spending evenly; above 1 = quota will expire unspent.
- **Brief**: the task file the session writes. **Relay**: the script that runs the harness and writes a run directory. **Run**: one relay invocation and its directory.

## 2. Decisions

1. **Relay layer is ADS.** Install `codex-delegate`, `agy-delegate`, `grok-delegate`, `claude-delegate` from amElnagdy/delegate-skills, pinned to commit b781ee2. Call `relay.mjs` with `--model`, `--effort`, `--timeout`, `--read-only`, `--out-dir`. Never use their `--lane` or their config file. Their `SKILL.md` files are not used.
2. **No LLM courier on the main path.** The session runs the relay with `run_in_background` and reads `result.json` when notified. The courier agent stays only as an optional polling wrapper for Workflow callers, which have no shell primitive.
3. **Two JSON files, ours.** `lanes.json` (global) and `routing.json` (global, per-project override at `<git-root>/.delegate/routing.json`). Strict JSON, formatted on write, validated on read with plain-language errors, `note` fields for comments.
4. **Tier and trust are human-set.** `bench.py` pulls rankings from Epoch AI and Artificial Analysis and writes them under `~/.cache/delegate/bench/`. No skill file reads that directory. The human reads it and edits `lanes.json`.
5. **Selection rule**: tier ceiling, cheapest tier first, trust inside a tier, one pace margin for every override (section 5).
6. **Meters stay primary.** Usage percent from the vendor probes drives the rule. Meter weight, plan, and monthly price feed the report and tiebreaks only.
7. **Entry points are skills.** `/delegate` routes with meters. `/delegate-<harness>` wrappers are typed-only (`disable-model-invocation: true`). No activation switch anywhere else.
8. **Gate hook advises, never denies.** Global CLAUDE.md Delegation section becomes one line naming `/delegate`.
9. **Return schema is requested in the brief** and parsed out of `finalMessage` by our wrapper, on every harness.

## 3. Files

### `~/.config/delegate/lanes.json` (global only)

```json
{ "version": "delegate-lanes.v1",
  "meters": {
    "claude-fable":  { "harness": "claude", "plan": "Max 5x",       "price_month": 100, "probe": "usage.py" },
    "claude-general":{ "harness": "claude", "plan": "Max 5x",       "price_month": 100, "probe": "usage.py" },
    "codex":         { "harness": "codex",  "plan": "ChatGPT Plus", "price_month": 20,  "probe": "usage.py" },
    "grok":          { "harness": "grok",   "plan": "SuperGrok",    "price_month": 30,  "probe": "usage.py" },
    "agy-gemini":    { "harness": "agy",    "plan": "Google AI Pro","price_month": 17,  "probe": "usage.py" } },
  "lanes": {
    "fable-xhigh@claude": { "harness": "claude", "model": "claude-fable-5-1", "effort": "xhigh",
      "meter": "claude-fable", "meter_weight": 10, "timeout": "60m",
      "price": { "in": 10, "cache_read": 0.25, "cache_write": 12.5, "out": 50 },
      "tier": 4, "trust": 5, "basis": "frontier; protect: orchestrator meter" },
    "sol-high@codex": { "harness": "codex", "model": "gpt-5.6-sol", "effort": "high",
      "meter": "codex", "meter_weight": 20, "timeout": "40m",
      "price": { "in": 4, "cache_read": 0.4, "cache_write": null, "out": 20 },
      "tier": 3, "trust": 5, "basis": "hardest impl and adversarial review" },
    "terra-high@codex": { "harness": "codex", "model": "gpt-5.6-terra", "effort": "high",
      "meter": "codex", "meter_weight": 10, "timeout": "25m",
      "price": { "in": 2, "cache_read": 0.2, "cache_write": null, "out": 12 },
      "tier": 2, "trust": 5, "basis": "preferred reviewer and implementor" },
    "grok46-high@grok": { "harness": "grok", "model": "grok-4.6", "effort": "high",
      "meter": "grok", "meter_weight": 1, "timeout": "40m",
      "price": { "in": 2, "cache_read": 0.5, "cache_write": null, "out": 6 },
      "tier": 2, "trust": 3, "basis": "sink for terra-grade work; not trusted alone" },
    "luna-low@codex": { "harness": "codex", "model": "gpt-5.6-luna", "effort": "low",
      "meter": "codex", "meter_weight": 1, "timeout": "10m",
      "price": { "in": 0.2, "cache_read": 0.02, "cache_write": null, "out": 1.2 },
      "tier": 1, "trust": 3, "basis": "benchmarks overstate it (Orin)" },
    "flash-high@agy": { "harness": "agy", "model": "gemini-3.8-flash-high", "effort": "high",
      "meter": "agy-gemini", "meter_weight": 1, "timeout": "25m",
      "price": { "in": 0.75, "cache_read": 0.075, "cache_write": null, "out": 3.75 },
      "tier": 1, "trust": 4, "basis": "cheap floor; fabricated citations in 3 impl briefs (ledger)" } } }
```

Rules: every lane names a meter that exists; `tier` 1..4; `trust` 1..5; `meter_weight` is relative inside one meter (Codex values from OpenAI's published per-model message ranges; others 1 until measured); `price` cited in the cost research file; `bench` scores are **not** stored here (they live in the bench output, hidden from models). Values above are the starting proposal, to be confirmed at setup.

### `~/.config/delegate/routing.json` (global) and `<git-root>/.delegate/routing.json` (override)

```json
{ "version": "delegate-routing.v1",
  "classTier": { "scout": 1, "mechanical": 1, "impl": 2, "review": 2, "hard-impl": 3 },
  "margin": 0.2,
  "gate": 0.10,
  "note": "override per project: e.g. {\"classTier\": {\"review\": 3}} sends reviews to sol" }
```

A project file may replace any key; a missing key falls back to global. No `mode`, no `balance`, no env var.

## 4. Meters

`usage.py` stays the probe layer (unofficial endpoints on every vendor; see cost research §3). It is called: at session start (existing prime hook), at every run start, and at every run finish. Cache TTL to be read off `usage.py` and stated in the implementation plan. Claude meters: 5h window, all-models weekly, top-model weekly; `binding` picks the tightest. Future measurement, recorded not built: total capacity per model per harness, derived from `meter_weight` and measured tokens, as an alternative to usage percent.

## 5. Selection rule (from prototype P4 plus trust)

```
input: class, lanes.json, routing (effective), meters (usage.py)
need = classTier[class]
eligible = [L for L in lanes if L.tier >= need and meter(L).remaining_weekly >= gate and cli(L.harness) present]
sort eligible by (tier asc, trust desc, pace desc)
pick = eligible[0]
for L in eligible[1:]:
    if pace(L) >= pace(pick) + margin: pick = L      # same tier or higher; one rule
return ordered list with pick first, and the reason per lane (ceiling / gate / stolen-by-pace)
```

Effects: the cheapest allowed tier serves by default; inside a tier the most trusted lane serves; a lane that is ahead of pace by `margin` steals the job whether it is lower-trust in the same tier or a higher tier, so quota that would expire is spent. When no lane is eligible: STOP with the reason. Per-job `--effort` on `/delegate` overrides the lane's effort dial, as ADS does; it does not change the lane's tier.

## 6. Dispatch

`delegate.py dispatch --lane <name> --class <c> --brief <path> --cwd <dir> [--write <worktree>] [--effort e]`:

1. Resolve lane, build the prompt: preamble + read-only or write clause + working directory + brief + **return schema request** (`schemas/return.json`, final message must end with one JSON object).
2. Allocate `~/.cache/delegate/runs/<utc-stamp>-<lane>-<8hex>/`, exclusive, never reused (ADS reuses stale artifacts otherwise).
3. Emit `dispatch.start` to the ledger (`events.py`, unchanged schema, TUI keeps working).
4. Run `node <ads>/<harness>-delegate/scripts/relay.mjs --brief <prompt> --cd <cwd> --model <slug> --effort <e> --timeout <lane.timeout> [--read-only] --out-dir <run-dir>` in the background (the session uses `run_in_background`; the wrapper itself is synchronous).
5. On exit: read `result.json`; map status `completed`→`done|partial|blocked` from the parsed return block, `failed|timeout|aborted|*_unavailable`→`blocked` with `reason` = their `error` or stderr tail; agy silent no-op is `failed` upstream already. Write `<run-dir>/return.json` in our schema. Emit `dispatch.finish` with secs, rc, status, run-dir. Re-probe meters.
6. Print one line: `delegate: <lane> status=<s> secs=<n> run=<dir>`.

Claude lanes: ADS `claude-delegate` relay strips `CLAUDECODE` from the child env (verified in its source, lines 389-392) so `claude -p` runs nested. One smoke run is acceptance item 8.

## 7. Entry points

- `/delegate <class> <brief>`: rank (section 5), print the ordered lanes with reasons, dispatch the pick unless `--dry-run`. This is the only skill that reads meters.
- `/delegate-claude`, `/delegate-codex`, `/delegate-agy`, `/delegate-grok`: frontmatter `disable-model-invocation: true`; take `--lane` or `--model`; call `delegate.py dispatch`; no meter read. About 20 lines each, sibling directories under `agents/skills/`.
- `/delegate setup`: run ADS `discover.mjs`; propose lane records from installed CLIs and the current catalog; run `bench.py`; show the ranking; ask tier and trust per lane; write both files after yes.
- Hook `delegate-gate.py`: keep `additionalContext` (meter table, pointer to `/delegate`); delete every `deny`/`ask` rule; delete `DELEGATE_BALANCE` and `lanes.json` threshold reads.
- Global `~/.claude/CLAUDE.md` Delegation section: one line. `courier.md`: optional, rewritten to background+poll, `maxTurns` raised; not referenced by the main path.

## 8. Benchmarks (`bench.py`)

Sources: Epoch AI CSV `https://epoch.ai/data/eci_benchmarks.csv` (no key, CC-BY, dated, source per row); Artificial Analysis `GET /api/v2/language/models/free` with `x-api-key` (free tier, 100 requests/day, attribution required). Filter to models in `lanes.json`. Columns: DeepSWE, FrontierCode, APEX-Agents, Terminal Bench, SWE-bench Verified from Epoch; coding index, agentic index, Terminal-Bench 2.1, median output tokens/s from AA. One mean-rank column per source. Output `~/.cache/delegate/bench/<date>.md`, never read by a skill. Known gaps on 2026-09-08: Gemini 3.8 Flash absent from Epoch; Astra has no SWE-bench; all scores at max effort.

## 9. Acceptance

1. A Grok run that would take 47 minutes ends at the lane timeout with status `timeout`, partial output kept in the run directory.
2. No run is bounded by a tool-call limit.
3. An agy empty response is `blocked` with a reason, never `done`.
4. Every run leaves a directory under `~/.cache/delegate/runs/` that outlives the session.
5. The brief reaches the CLI byte for byte (relay reads the file we wrote; no LLM in between).
6. Every file the hook or docs name exists (`routing.md` rewritten or deleted).
7. No env var switch remains; `mode` and `balance` do not exist as settings.
8. A Claude lane completes one read-only smoke run through the ADS relay from inside Claude Code.

## 10. Migration

Delete: `lanes.tsv`, `dispatch.sh`, `references/routing.md` (or rewrite), courier as main path. Rewrite: `rank.py` → section 5 over the two JSON files; `extract.py` → parse return block from `finalMessage`; `report.py` → add $ per job from price and plan. Add: `delegate.py`, `bench.py`, `setup`, four wrapper skills, `schemas/lanes.json` and `schemas/routing.json` validators, tests with a fake relay. Keep: `usage.py`, `events.py`, `monitor/`, `schemas/return.json`, prime hook. Pin ADS with `npx skills add amElnagdy/delegate-skills --skill <name>` and record the commit; check `npx skills --help` for an update command before relying on one.

## 11. Out of scope, recorded

Codex write sandbox config (0 of 3 done in ledger; no demand shown). Astra lane row. Total-capacity measurement (section 4). Codex token usage parse from `events.jsonl` (Grok relay already reports usage; Codex relay does not). Fixes to ADS bugs found in the audit (stale artifacts, watchdog hang with escaped grandchild, abort leaving descendants, agy cwd join) go upstream as PRs; the fresh run directory in section 6 sidesteps the first.

## 12. Risks

- Every usage probe is unofficial (cost research §3). A vendor change breaks a meter silently; `status: unknown` must sort last, never block.
- ADS relays are 2,160 lines of Node we do not own. Pinning plus the fresh run dir covers the known bugs; anything else is an upstream PR.
- Nested `claude -p` inside Claude Code is verified in ADS source, not yet on this machine (acceptance 8).
- Benchmark rankings are at max effort and disagree with each other in the mid band; that is why tier and trust are human-set.
