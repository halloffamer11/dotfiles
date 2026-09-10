Note: crate moved to tools/delegate-mon/ on 2026-09-09.

# Delegate monitoring TUI — Design Spec

- **Date:** 2026-09-02
- **Status:** Approved
- **Working dir:** `/Users/dreiss/dotfiles`
- **Research:** `agents/skills/delegate/tui-research.md`
- **Mockup:** `agents/skills/delegate/tui-mockup.txt`

## 1. Goal

A local, read-mostly monitoring cockpit for delegate meters and in-flight dispatches. The TUI consumes a versioned JSONL event contract. It does not own ranking or dispatch.

## 2. Scope

**In**

- Rust crate at `agents/skills/delegate/monitor/` (binary `delegate-mon`).
- Ratatui 0.30 + crossterm. No async runtime.
- Event contract v1 written by `usage.py` and `dispatch.sh` into `$DELEGATE_LEDGER` (default `~/.cache/delegate/ledger.jsonl`).
- Panels: meters, open threads, burn (1h / 24h / 7d), rank overlay.
- Keys: `q` quit, `r` refresh (`usage.py --refresh` off the UI thread), `k` rank overlay, `Tab` cycles rank class, `1`/`2`/`3` burn window, `j`/`k` or arrows in the threads table.
- `claude_reset` in `usage.py` parses weekly strings without minutes (`Sep 8 at 3pm`).

**Out**

- Dispatch, resume, stop, kill, or Herdr pane control.
- Rewriting `rank.py` logic inside the TUI.
- Rewriting the Claude hook as the source of truth.
- A background daemon besides the TUI process.
- `notify` crate in v1 (250 ms size/mtime tick is enough).
- Installing the binary via brew/stow. Run with `cargo run` from the crate.

## 3. Key decisions

1. **Store crate + channel loop.** `store` folds JSONL into a snapshot and has no Ratatui types. `tui` is Model / Message / update / view. Workers: keys, file tick, on-demand probe/rank. Chosen over a single poll loop (store and UI mix; refresh still needs a thread) and the Ratatui component template (ceremony for three panels).
2. **TUI is a reader.** Writers are `usage.py` (meter lines on cache write) and `dispatch.sh` (start/finish). The Claude hook keeps appending legacy `r` snapshots.
3. **Class is an explicit `--class` flag** on `dispatch.sh`. A lane row can list several classes (`flash-high@agy` is four). Optional for back-compat; SKILL.md and courier always pass it. Missing class renders as `—`.
4. **Finish `status` comes from extracted `out.json`**, not `rc`. `rc != 0` with no object still maps to `blocked`.
5. **Weekly burn uses `meter.remaining_weekly` only.** Hook `r` is `min(5h, weekly)` and is excluded from the chart.
6. **Orphan starts** (no finish) become `stale` after `timeout_s` on the start event. Observation only. No PID liveness check in v1.
7. **Live meters also read `usage.json`.** The panel does not wait for a dispatch to show current remaining / pace / cache age.

## 4. Event contract v1

Path: `$DELEGATE_LEDGER` or `~/.cache/delegate/ledger.jsonl`. One JSON object per line. Unknown `kind` is ignored. A row with no `v` and no `kind` is `legacy.hook`.

### 4.1 `meter`

Emitted by `usage.py` whenever it writes the cache (probe path), not when it serves a fresh cache. Same lane objects as `usage.json`.

```json
{
  "v": 1,
  "kind": "meter",
  "ts": "2026-09-02T23:00:00-04:00",
  "source": "probe",
  "cache_age_s": 0,
  "probed_at": 1788403774.3,
  "lanes": [
    {
      "lane": "agy-gemini",
      "harness": "agy",
      "meter": "gemini",
      "remaining_5h": 0.87,
      "remaining_weekly": 0.90,
      "r": 0.87,
      "binding": "5h",
      "reset_5h": 1788406804,
      "reset_weekly": 1788616225,
      "pace": 2.58,
      "status": "ok",
      "note": null
    }
  ]
}
```

`cache_age_s` is 0 at write time. `probed_at` is the cache timestamp.

### 4.2 `dispatch.start`

Emitted by `dispatch.sh` after argument validation and before the child process. `thread_id` is a UUID4 string, kept in a shell variable for the matching finish.

```json
{
  "v": 1,
  "kind": "dispatch.start",
  "ts": "2026-09-02T23:01:00-04:00",
  "thread_id": "550e8400-e29b-41d4-a716-446655440000",
  "lane": "flash-high@agy",
  "class": "verify",
  "effort": "medium",
  "timeout_s": 600,
  "cwd": "/abs/dir",
  "brief": "/abs/brief.md",
  "out": "/abs/out.json",
  "write": null
}
```

`class` is the `--class` value, or `null` if omitted. `timeout_s` is 360 / 600 / 1500 for low / medium / high (same as agy `--print-timeout`). Codex and grok have no matching print-timeout; the store still uses these numbers for stale detection.

### 4.3 `dispatch.finish`

Emitted once, including on signals, via an EXIT trap after `thread_id` exists. Do not emit finish if start never ran.

```json
{
  "v": 1,
  "kind": "dispatch.finish",
  "ts": "2026-09-02T23:02:44-04:00",
  "thread_id": "550e8400-e29b-41d4-a716-446655440000",
  "lane": "flash-high@agy",
  "class": "verify",
  "secs": 104,
  "rc": 0,
  "status": "done",
  "child_session": "ffecc85b-084d-47f9-ad14-2e0d44307989",
  "out": "/abs/out.json"
}
```

`status` is `done` | `partial` | `blocked` from the extracted object. If extract produced no object or the file is missing: `blocked`.

### 4.4 Encoder

New `events.py` next to `dispatch.sh`. Ledger path is `$DELEGATE_LEDGER` else `~/.cache/delegate/ledger.jsonl`. Functions: `append(obj)`, `meter_event(doc)`, `start_event(...)`, `finish_event(...)`. One-line JSON, trailing newline, append mode. CLI:

```
python3 "$HERE/events.py" meter <usage.json>
python3 "$HERE/events.py" start <thread_id> <lane> <class-or-null> <effort> <timeout_s> <cwd> <brief> <out> <write-or-null>
python3 "$HERE/events.py" finish <thread_id> <lane> <class-or-null> <secs> <rc> <status> <child_session-or-null> <out>
```

Empty or `-` for class / write / child_session becomes JSON `null`. Finish `status` is passed in by `dispatch.sh` (a Python one-liner reads `$out`; default `blocked`). `usage.py` imports `append` / `meter_event` rather than shelling out.

### 4.5 `dispatch.sh` flag

```
dispatch.sh <lane> <brief.md> <out.json> [--cwd DIR] [--write DIR] [--effort low|medium|high] [--class CLASS]
```

`--class` is optional. Smoke tests stay valid without it. SKILL.md dispatch line and `courier.md` command gain `--class <class>`. The parent already classified before rank; it must pass that class through.

## 5. Architecture

```
usage.py --refresh ──► usage.json ──► meter line ──► ledger.jsonl
dispatch.sh start/finish ──────────────────────────► ledger.jsonl
delegate-ledger.py (legacy hook r) ────────────────► ledger.jsonl

delegate-mon
  store  tail JSONL + read usage.json → Snapshot
  tui    Model/Message/update/view
  workers  keys | 250ms file tick | usage.py --refresh | rank.py <class>
```

Crate layout:

```
agents/skills/delegate/monitor/
  CLAUDE.md          # thin: what the crate is, points at the spec
  AGENTS.md          # symlink to CLAUDE.md
  Cargo.toml
  src/lib.rs         # store + event types
  src/store.rs
  src/event.rs
  src/tui.rs
  src/main.rs
  tests/fold.rs      # fixture-driven fold tests
```

`Snapshot`:

- `meters`: latest `usage.json` if present, else latest `meter` event, else empty.
- `threads`: `dispatch.start` with no `dispatch.finish` for that `thread_id`. State `run` until `now > start.ts + timeout_s`, then `stale`. Elapsed from `start.ts`.
- `series`: `remaining_weekly` per lane from `meter` events whose `ts` falls in the selected window. Missing weekly is a gap, not `r`.
- `cache_age_s`: `now - usage.json.probed_at` when that file exists.

Fold is a pure function of (events, usage_doc, now, window). Unit-tested with fixture JSONL. No terminal.

Messages: `Key`, `FileChanged`, `ProbeDone`, `RankDone`, `Tick`, `Quit`.

`usage.py --refresh` (~13 s) and `rank.py` run in a worker thread. The UI shows `refresh in flight` / `rank in flight` and does not block draw.

## 6. UI

Follow `tui-mockup.txt`. Density over chrome. Rounded `Block` borders.

**Meters (left).** One meter = two `LineGauge`s (5h, weekly) plus a metadata line: binding, reset of the binding window, pace, ahead/behind. Missing 5h (Grok) is `—`. `ratio` clamped to 0..=1 before the widget (Ratatui panics outside that range). Null pace renders `—`.

Color: remaining `r < 0.10` red (`GATE`), `< 0.40` yellow, else green. Pace `> 1.0` green (ahead), else dim.

**Open threads (right, ~36 columns).** `Table`: lane, class, elapsed `m:ss`, state `run`|`stale`. Empty state: `— none —` plus one line that finish events come from `dispatch.sh`.

**Burn (bottom).** `Chart` + Braille `Dataset`, one series per lane, y = remaining weekly % 0..=100. Title shows selected window `[1h] 24h 7d`. GATE drawn as a hint in the footer, not a fourth dataset.

**Rank overlay.** `Clear` + bordered `Table` from `rank.py <class>` stdout. Display only. `Tab` cycles `impl`, `verify`, `review`, `scout`, `hard-impl`, `mechanical`. `k` or `Esc` closes.

**Footer.** Cache age, in-flight flags, key help.

Paths: `DELEGATE_LEDGER`, `DELEGATE_CACHE` (same defaults as Python). `DELEGATE_SKILL` or `../` from the crate for `usage.py` / `rank.py` when running from source.

## 7. Tests

| Gate | When |
| --- | --- |
| `python3 tests/test_events.py` | after `events.py` |
| `python3 tests/test_extract.py` | after `extract.py` (unchanged unless finish-status wiring requires it) |
| `sh tests/smoke.sh` | after `dispatch.sh` / courier / SKILL.md |
| `python3 -c` fixture: start+finish round-trip, `--class` present, EXIT trap emits finish | slice 1 |
| `usage.py` unit: `claude_reset("Sep 8 at 3pm (America/New_York)")` is not None; cache write appends one `meter` line | slice 1 |
| `cargo test` in `monitor/` | slice 2+ (fold: unmatched start, stale after timeout, ignore legacy `r` in weekly series, clamp ratio) |
| Manual: `cargo run` shows meters from live `usage.json`; threads empty until slice 1 is installed | slice 3 |

## 8. Alternatives (rejected)

- Single-process poll loop: refresh still needs a worker; store untested without a terminal.
- Ratatui component template: extra config/action maps for three panels.
- PID liveness for orphans: observation that looks like process control; print-timeout is enough for v1.
- TUI writing meter lines: violates “consumer of the contract.” `usage.py` already writes the cache.

## 9. Open questions

None that block v1. `--class` vs env was decided: `--class`. Burn chart is remaining weekly level, not %/hr.

## 10. PR plan

**PR 1 — Event contract.** `events.py`, `dispatch.sh` start/finish + `--class` + EXIT trap, `usage.py` meter append + `claude_reset` minutes-optional, SKILL.md + `courier.md` pass `--class`, `tests/test_events.py`, smoke still green.

Depends on: nothing.

**PR 2 — Store crate.** `monitor/` scaffold, `event.rs` / `store.rs`, fixture tests. No TUI yet. `CLAUDE.md` + `AGENTS.md` symlink.

Depends on: PR 1 (fixture events match the encoder).

**PR 3 — TUI.** `tui.rs` + `main.rs`, widgets per §6, workers for refresh/rank/tick. `cargo run` is the gate.

Depends on: PR 2.
