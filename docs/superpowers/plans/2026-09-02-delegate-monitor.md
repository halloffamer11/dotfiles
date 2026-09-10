# Delegate monitoring TUI — Implementation Plan

> Implement task-by-task. Checkboxes are the progress record. Do not start a later task until that task’s gate commands pass.

**Goal:** Land the approved event contract, then a testable store crate, then the Ratatui cockpit. Spec: `docs/superpowers/specs/2026-09-02-delegate-monitor-design.md`.

**Architecture:** JSONL v1 (`meter`, `dispatch.start`, `dispatch.finish`) written by `usage.py` and `dispatch.sh`. Rust crate `agents/skills/delegate/monitor/` (binary `delegate-mon`) folds the ledger into a snapshot and draws meters / open threads / burn. TUI does not dispatch.

**Tech stack:** POSIX `sh`, Python 3 (existing skill scripts), Rust 2021, Ratatui 0.30, crossterm, serde_json. No tokio. Tests: `python3 tests/test_*.py`, `sh tests/smoke.sh`, `cargo test`.

**Working dir:** `/Users/dreiss/dotfiles`. Skill files live in `agents/skills/delegate/`. Do not commit unrelated dirty files. Tasks 1–3 landed 2026-09-03.

---

## Task 1: Event contract

**Files:**
- Create: `agents/skills/delegate/events.py`
- Create: `agents/skills/delegate/tests/test_events.py`
- Create: `agents/skills/delegate/tests/test_usage_reset.py`
- Edit: `agents/skills/delegate/dispatch.sh`
- Edit: `agents/skills/delegate/usage.py`
- Edit: `agents/skills/delegate/SKILL.md`
- Edit: `agents/agents/courier.md` (source; stow target is `~/.claude/agents/courier.md`)
- Edit: `agents/skills/delegate/tests/smoke.sh` only if a flag parse breaks (should not)

- [x] **Step 1: `events.py`**

Encoder with: `LEDGER` from `$DELEGATE_LEDGER` else `~/.cache/delegate/ledger.jsonl`. `append(obj)` writes one JSON line. CLI:

```
python3 events.py meter <usage.json>
python3 events.py start <thread_id> <lane> <class-or-null> <effort> <timeout_s> <cwd> <brief> <out> <write-or-null>
python3 events.py finish <thread_id> <lane> <class-or-null> <secs> <rc> <status> <child_session-or-null> <out>
```

`class`, `write`, `child_session` of `-` or empty become JSON `null`. Finish JSON field is `child_session` (not `session`). `ts` is local ISO with offset, seconds precision.

- [x] **Step 2: `tests/test_events.py`**

Temp `DELEGATE_LEDGER`. Assert: meter copies lane objects from a fixture usage doc; start/finish share `thread_id`; omitted class is `null`; each call appends exactly one line; `v==1`. Exit 1 on failure. Run: `python3 tests/test_events.py`.

- [x] **Step 3: `dispatch.sh`**

Initialize `class=""`, `thread_id=""`, `rc=1`, `secs=0`, `status=blocked`, `session=""` before any `trap` (`set -u` is on). Parse `--class` in the existing flag loop. After lane lookup, cwd, and brief checks succeed, generate `thread_id` (`python3 -c "import uuid; print(uuid.uuid4())"`). Map effort → `timeout_s`: low 360, medium 600, high 1500. Emit `start`. `trap` EXIT so `finish` runs only when `thread_id` is non-empty. After `extract.py`, set `status` with a Python one-liner on `$out` (default `blocked` if missing/invalid). Pass `session` as the finish CLI `child_session` argument. Keep the existing stdout `delegate:` line.

- [x] **Step 4: `usage.py`**

(1) `claude_reset`: minutes optional. Match `H:MM` or `H` before `am|pm`. Missing minutes → `:00`. Both `Sep 8 at 2:59pm (...)` and `Sep 8 at 3pm (...)` must parse. (2) After a successful cache write, `append(meter_event(d))`. Do not append when serving a still-fresh cache.

Add a tiny test in `tests/test_events.py` or a new `tests/test_usage_reset.py` that calls `claude_reset` (import or subprocess). Prefer import if you extract the function; otherwise a 10-line script is enough.

- [x] **Step 5: Callers**

`SKILL.md` dispatch lines include `--class <class>`. `agents/agents/courier.md` command includes `--class <class>` and says the caller names the class. Courier still runs exactly one command.

- [x] **Step 6: Gate**

```
python3 tests/test_events.py
python3 tests/test_extract.py
python3 tests/test_usage_reset.py
sh tests/smoke.sh
```

`test_usage_reset.py` covers `claude_reset("Sep 8 at 3pm (America/New_York)")` is not None, and a cache write with `DELEGATE_LEDGER` + `DELEGATE_CACHE` in a temp dir appends one `meter` line.

Fixture check: `DELEGATE_LEDGER=/tmp/t.jsonl` around `dispatch.sh` against `tests/fixture/brief.md` (no `--class`) must produce one start and one finish with the same `thread_id` and `class: null`. A second run with `--class scout` must store `"class":"scout"`.

---

## Task 2: Store crate

**Files:**
- Create: `agents/skills/delegate/monitor/CLAUDE.md`
- Create: `agents/skills/delegate/monitor/AGENTS.md` (symlink to `CLAUDE.md`)
- Create: `agents/skills/delegate/monitor/Cargo.toml`
- Create: `agents/skills/delegate/monitor/src/{lib,event,store}.rs`
- Create: `agents/skills/delegate/monitor/tests/fold.rs`
- Create: `agents/skills/delegate/monitor/tests/fixtures/*.jsonl`

- [x] **Step 1: Scaffold**

`Cargo.toml` package `delegate-mon`, edition 2021, deps: `serde`, `serde_json`, `thiserror`. No ratatui yet. `CLAUDE.md` thin: crate purpose, points at the spec and `../`. `ln -s CLAUDE.md AGENTS.md`.

- [x] **Step 2: Event types + fold**

Parse v1 `meter` / `dispatch.start` / `dispatch.finish`. Rows without `v`/`kind` → ignore for threads and weekly series. `fold(events, usage_doc, now, window) -> Snapshot` per spec §5. Clamp remaining fractions to 0..=1. Unmatched start: `run` until `now > ts + timeout_s`, then `stale`.

- [x] **Step 3: Tests**

Fixtures: (a) two meters, series has weekly not `r`; (b) start without finish → one thread; (c) start+finish → zero threads; (d) start with `timeout_s=1` and `now` past that → `stale`; (e) legacy hook row does not create a thread and does not enter weekly series. `cargo test`.

- [x] **Step 4: Gate**

```
cd agents/skills/delegate/monitor && cargo test
```

---

## Task 3: TUI

**Files:**
- Edit: `agents/skills/delegate/monitor/Cargo.toml` (add `ratatui` 0.30, `crossterm`)
- Create: `agents/skills/delegate/monitor/src/tui.rs`
- Create: `agents/skills/delegate/monitor/src/main.rs`
- Edit: `agents/skills/delegate/monitor/src/lib.rs` as needed

- [x] **Step 1: Event loop**

`mpsc` of `Message`. Input thread: crossterm keys. Tick thread: 250 ms, stat ledger + `usage.json`, send `FileChanged` on size/mtime change then re-tail from last offset. Probe/rank: spawn `python3` of `usage.py --refresh` / `rank.py <class>` on `r` / `k`, never on the draw thread.

- [x] **Step 2: View**

Layout and widgets per spec §6 and `tui-mockup.txt`. `LineGauge` labels are exact percents. Null 5h / null pace → `—`. Rank overlay is display-only.

- [x] **Step 3: Gate**

```
cd agents/skills/delegate/monitor && cargo test && cargo build
```

Manual: `cargo run` in a real terminal. Confirm meters from live `usage.json`, empty threads if no unmatched starts, `q` restores the terminal.

---

## Done when

- Spec §7 gates for all three tasks pass.
- SKILL.md / courier pass `--class`.
- No dispatch/resume/stop/Herdr controls in the TUI.
- Unrelated working-tree files remain untouched.
