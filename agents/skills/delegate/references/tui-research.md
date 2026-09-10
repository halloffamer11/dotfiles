# Delegate monitoring TUI — research

Status: research complete, design approved 2026-09-02. Spec: `docs/superpowers/specs/2026-09-02-delegate-monitor-design.md`. Plan: `docs/superpowers/plans/2026-09-02-delegate-monitor.md`. No implementation yet.

Verified against: Ratatui site 0.30.2 (`https://ratatui.rs/`), docs.rs widget pages, macmon `src_app/{main,tui}.rs` on GitHub, btop README/screenshots, current `usage.py` / `dispatch.sh` / `~/.cache/delegate/ledger.jsonl` / `delegate-ledger.py`.

## What exists today

- `usage.py` writes `~/.cache/delegate/usage.json`. One document of meters: remaining 5h, remaining weekly, `r`, binding window, reset times, pace, cache `probed_at`. Refresh takes about 13 seconds.
- `rank.py <class>` reads that cache and prints a ranked table. It does not write events.
- `dispatch.sh` prints one stdout line after the child exits (`lane`, `rc`, `secs`, `out`, `session`). It does not write JSONL.
- `~/.claude/hooks/delegate-ledger.py` appends to `~/.cache/delegate/ledger.jsonl` on Claude `PostToolUse` (Agent|Workflow) and `SubagentStop`. Each row is a meter snapshot (`lanes: {name: r}`) plus hook fields. It is not a dispatch lifecycle.
- Inspected ledger (66 rows, 2026-09-02): events are only `PostToolUse` (23) and `SubagentStop` (43). No lane, class, duration, result, or child session.

Open threads cannot be reconstructed from the current ledger. Burn rate can be approximated from successive `r` snapshots, but those snapshots fire only when Claude spawns or stops a subagent, and they store only `r`, not 5h/weekly/pace.

## Visual references

btop (C++, not Ratatui): boxed panels, braille graphs, exact percentages in titles, color thresholds, process table as the live list. Dense alignment matters more than decoration.

macmon (Rust + Ratatui): the closest implemented analogue.

- Library (`src_lib`) is separate from the TUI (`src_app`). The TUI consumes `Metrics`; it does not own sampling.
- Channel split: input thread, sampler thread, UI thread. `Event` enum (`Update`, `Tick`, `Quit`, view toggles).
- Each metric is a title with exact value plus either `Gauge` (current %) or `Sparkline` (history), toggled with `v`.
- Labels sit in the `Block` title, not only inside the bar: `CPU 12% @ 1800 MHz`, `RAM 4.2 / 16.0 GB (26%)`.
- Rounded borders, one-line help in the bottom title.

Take from both: exact numbers next to bars, history as a second encoding, thresholds as color, no modal chrome.

## Ratatui (0.30.2)

Immediate-mode. `Terminal::draw` diffs two buffers and writes only the changes.

Widgets that map to the requirements:

| Need | Widget | Notes |
| --- | --- | --- |
| Remaining % | `LineGauge` (one row) or `Gauge` (taller) | `ratio(0.0..=1.0)`, custom `label` for exact percent. `LineGauge` is denser for 6 meters × 2 windows. Color via `filled_style`. Panics if ratio is outside 0..=1. |
| Compact history | `Sparkline` | `data(&[u64])`, `max`, `absent_value_*` for gaps. macmon stores newest-first and renders `RightToLeft`. |
| Windowed burn | `Chart` + `Dataset` | `GraphType::Line`, `Marker::Braille`. One dataset per meter. `Axis` bounds and labels. Better than Sparkline when comparing lanes. |
| Open threads | `Table` + `TableState` | Selectable rows. Columns: lane, class, elapsed, state. |
| Rank overlay | `Table` or `List` in a centered `Clear`+`Block` | Triggered by a key; not a second screen. |

Layout: nested `Layout::{vertical,horizontal}` with `Constraint::{Length,Min,Fill,Percentage}`. `frame.area().layout(&layout)` → `[a, b] = ...` is the 0.30 pattern.

Application patterns from official docs:

- **App struct + loop** — default tutorial. Fine for a small UI.
- **Elm-style Model / Message / update / view** — official page. Map keys and IO to `Message`, fold into `Model`, render from `Model`. Docs note view immutability is often dropped because `StatefulWidget` needs `&mut state`.
- **Component architecture** — official template for large apps. Too much for three panels.

Event sources: Ratatui does not read input. Crossterm `event::poll` + `event::read`. For a second source (file watch, probe), do not block `event::read()`. macmon’s `mpsc` + dedicated threads is the documented-adjacent pattern. Tokio `EventStream` is optional; this app does not need an async runtime if probes run on a worker thread.

File watching: `notify` 8 (`recommended_watcher`, FSEvents on macOS). JSONL append can fire before the write is durable, so the store should treat a notify as “re-stat and read from last offset”, not as “the new line is complete”. A 250 ms tick that checks file size is enough for v1; add `notify` if tick-only feels laggy.

`usage.py --refresh` must not run on the UI thread.

## Event contract (draft, required before UI polish)

Versioned JSONL. One object per line. Unknown `kind` is ignored. The TUI is a reader.

```json
{"v":1,"kind":"meter","ts":"2026-09-02T23:00:00-04:00","source":"probe","cache_age_s":12,"lanes":[{"lane":"agy-gemini","remaining_5h":0.87,"remaining_weekly":0.90,"r":0.87,"binding":"5h","reset_5h":1788406804,"reset_weekly":1788616225,"pace":2.58,"status":"ok"}]}
{"v":1,"kind":"dispatch.start","ts":"...","thread_id":"...","lane":"flash-high@agy","class":"scout","cwd":"/abs","brief":"/abs/brief.md"}
{"v":1,"kind":"dispatch.finish","ts":"...","thread_id":"...","lane":"flash-high@agy","class":"scout","secs":41,"rc":0,"status":"done","child_session":"...","out":"/abs/out.json"}
```

- `meter` is the full `usage.py` lane object, not only `r`. Writer: `usage.py` appends one `meter` line whenever it writes the cache (not implemented yet). The Claude hook stays a compatibility source of `r`-only rows.
- `dispatch.start` / `dispatch.finish` share `thread_id`. Open threads = starts with no finish. Writer: `dispatch.sh` (append, never the TUI). `class` is an explicit argument (or env) to `dispatch.sh`; it cannot be inferred from lane (`flash-high@agy` is four classes). Finish `status` is the `status` field from the extracted `out.json`, not `rc` alone.
- Existing hook rows stay readable: no `v`/`kind` → treat as `legacy.hook` meter-only snapshots. Do not require a ledger rewrite. Do not use them for the weekly burn chart (`r` is min(5h, weekly)).
- TUI also reads live `usage.json` for the current meter panel so a refresh does not wait for a dispatch.
- Orphan starts (no finish): mark stale after the lane print-timeout (6/10/25 min by effort). No PID kill; observation only.

Derived views (not stored):

- Remaining bars from the latest `meter` or `usage.json`.
- Open threads from unmatched `dispatch.start`, stale after print-timeout.
- Burn series from `meter` `remaining_weekly` only. Sparse until `usage.py` appends on cache write.

## Agy verify (2026-09-02)

`delegate: verify → flash-high@agy` (inline dispatch, no courier). `status=done`, `changed_files=[]`, 104 s. Adjudicated against the named files:

- Keep architecture 1.
- Contract holes that hold: `dispatch.sh` has no class; finish does not read `out.json` status; weekly burn cannot use hook `r`; meter lines are proposed, not current (`usage.py` writes only `usage.json`).
- Rejected: research line 69 as a false current-behavior claim. It is a proposed writer.
- Extra defect in `usage.py` `claude_reset`: regex requires `H:MM`, so weekly `'Sep 8 at 3pm'` leaves `reset_weekly` and `pace` null (confirmed in `usage-sample.json`). Mockup Claude pace numbers are therefore not always available. Fix belongs in `usage.py`, not the TUI.

## Architecture options

### 1. Store crate + channel loop (recommended)

Cargo package at `agents/skills/delegate/monitor/` (binary `delegate-mon`). Two modules:

- `store`: parse JSONL, tail by offset, fold into `Snapshot { meters, threads, series }`. Unit-tested with fixture files. No Ratatui types.
- `tui`: Elm-style `Model` / `Message` / `update` / `view`. Worker threads: (a) crossterm keys, (b) file tick or `notify`, (c) on-demand `usage.py --refresh` / `rank.py`. UI thread only renders.

Matches the accepted rule: the TUI consumes a versioned contract. macmon’s proven split. Tests of burn/open-thread folding do not need a terminal.

Cost: two threads and a small crate layout. Not a framework.

### 2. Single-process poll loop

One `App` struct. `event::poll(250ms)` then re-read files on timeout. Spawn `usage.py --refresh` only on `r`.

Fewer moving parts. File tail and UI state mix. A 13 s refresh still needs a child thread or the UI freezes, so the “simple” loop is not actually single-threaded. Harder to test the store.

### 3. Ratatui component template

Each panel is a `Component` with its own action map and config file. Official large-app template.

Useful if this grows into a general cockpit. For three panels and two keys that spawn subprocesses, the template is ceremony.

## Widget and layout proposal (for option 1)

- Top: meters (left, fill) + open threads (right, ~36 columns). Each meter is two `LineGauge`s on one row (5h, weekly) plus a metadata line (binding, reset, pace, status). Missing 5h (Grok) renders as `—`.
- Color: remaining `r < 0.10` red (same as `GATE`), `< 0.40` yellow, else green. Pace `> 1.0` green (ahead), else dim.
- Bottom: `Chart` of remaining weekly (or binding `r` when weekly is absent) over the selected window. Keys `1`/`2`/`3` select 1h / 24h / 7d.
- Footer: cache age, refresh/rank in flight, key help.
- Keys: `q` quit, `r` refresh, `k` rank overlay, `1`/`2`/`3` window, `j`/`k` or arrows in the threads table. No dispatch/resume/stop.

## Out of scope (already accepted)

Dispatch, resume, stop, Herdr pane control, owning `rank.py` logic, rewriting the Claude hook as the source of truth.
