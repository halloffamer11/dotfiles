# 07b — Setup wizard as a selectable TUI

**What to build:** Orin's rework of ticket 07 (2026-09-09): the wizard becomes a curses TUI; tiers are assigned from tier 4 down; the benchmark numbers sit beside every row; lanes already placed in a higher tier are shown de-emphasized on the lower screens; the plain prompt flow stays for pipes and `--plain`.

**Blocked by:** 07 (landed).

**Status:** in flight 2026-09-09 on sol-high@codex through `delegate.py run hard-impl`; run directory `~/.cache/delegate/runs/20260909T180000Z-sol-high@codex-11e45c28/` (read `return.json` there); worktree `~/.cache/delegate/wt-ticket-07b` (diff against `HEAD` for the five files named below). Next session: review the diff, run the six gate commands, copy the files into `agents/skills/delegate/`, rerun every test file, commit, then Orin runs `python3 ~/.claude/skills/delegate/setup.py` on this machine.

- [ ] Worker result reviewed and landed
- [ ] Orin runs the TUI wizard once and confirms the catalog (closes ticket 07)

## Brief as dispatched

# Objective

Rebuild the delegate setup wizard as a selectable terminal UI. The human assigns lanes to tiers from the best tier down, sees the relevant benchmark numbers next to every row while deciding, and lanes already placed in a higher tier are shown de-emphasized on the lower-tier screens. Python 3.14 standard library only (`curses` for the screen). No network in tests.

Working directory is a git worktree of the dotfiles repo. Every path below is relative to `agents/skills/delegate/` inside it. Read first: `CLAUDE.md`, `setup.py` (the current prompt-driven wizard; it stays as the plain mode), `tests/test_setup.py` (must keep passing unchanged), `bench.py` (you refactor its data collection into a reusable function; `tests/test_bench.py` must keep passing unchanged), `catalog.py` (`validate_lanes`, `validate_routing`, `write_json`, `CLASSES`), `samples/lanes.json`, `tests/test_catalog.py` (test style: `PASS`/`FAIL` lines, exit 1 on failure, no pytest).

Files you may change or create: `bench.py` (refactor), `setup.py` (entry and plain mode), new `setup_tui.py`, new `tests/test_setup_tui.py`, `tests/fixture/bench-epoch.csv` (a small Epoch-format fixture, may reuse the one `tests/test_bench.py` builds inline; write it as a file). Nothing else. Do not commit.

## 1. `bench.py`: expose the data

Add `collect(lanes_doc, epoch_csv=None, aa_json=None, key_file=None)` returning a plain dict:

```
{"models": {<model>: {"lanes": [...], "lane_effort": "high",
                      "epoch": {"cells": {<bench>: {"performance": 0.72, "effort": "max"}}, "mean": 2.3 or None, "mean_s": "2.3 (n=3)"},
                      "aa": {"cols": {"Coding Index": 67.0, ...}, "mean": ..., "mean_s": ...} or None}},
 "epoch_benchmarks": [...EPOCH_BENCHMARKS], "aa_columns": [names...],
 "aa_skipped": None or "<reason>", "notes": [...]}
```

`run()` must build its report from `collect()` so the written report is byte-identical to today (the existing tests prove it). Without an Epoch source (`epoch_csv` missing and the fetch failing) `collect` raises `BenchError` as `run` does today; the wizard catches it and shows empty benchmark columns with the reason in the footer.

## 2. `setup_tui.py`: a state machine and a curses renderer, separated

`class Wizard`: pure state, no curses import at module top level for this class. Constructor takes `lanes_doc`, `routing_doc`, `bench` (the `collect()` dict or `None`), `discovered` (set of harness names), `lanes_path`, `routing_path`. Methods:

- `handle(key)` where `key` is one of the names `up`, `down`, `space`, `enter`, `b`, `q`, `y`, `n`, `plus`, `minus`, `1`..`5`, `other`. Returns nothing; mutates state.
- `view()` returns a dict the renderer draws: `screen` (`discovery`, `tier`, `routing`, `confirm`, `done`, `quit`), `title`, `tier` (4..1 on tier screens), `columns` (header names), `rows` (list of dicts with `cells` list of strings, `marked` bool, `dimmed` bool, `cursor` bool, `tag` such as `tier 4`), `footer` (key help), `message` (one line, empty when nothing to say).
- `result()` returns `(lanes_doc, routing_doc)` after the confirm screen answered `y`, else `None`.

Flow and rules:

1. `discovery`: one row per harness in `claude, codex, agy, grok`: found or missing. Any key continues.
2. `tier` screens for tier 4, then 3, then 2, then 1. Active rows are the lanes not yet assigned to a higher tier, sorted by Epoch mean rank ascending with unknown means last, then by lane name. Below them, dimmed and unselectable, the lanes already assigned to a higher tier, each tagged `tier N`. Columns: mark, lane, model, effort, trust, then the five Epoch benchmarks as percents with one decimal (or `—`), Epoch mean rank, and, when the AA source is present, its four columns and mean rank. Preselection: a lane whose current `tier` in the incoming catalog equals this screen's tier is marked. `space` toggles the mark on the cursor row (active rows only). `1`..`5` set trust on the cursor row. `enter` records every marked active lane as assigned to this tier and moves to the next lower tier. On the tier 1 screen every still-unassigned active lane starts marked; if the human unmarks one and presses `enter`, the message says `every lane needs a tier` and the screen stays. `b` returns to the previous tier screen with its marks and trusts intact (assignments made on the screen being left are undone).
3. `routing`: rows for `classTier.<class>` for each of `CLASSES`, then `margin`, then `gate`. `plus` and `minus` adjust the cursor row: class tiers by 1 within 1..4, margin and gate by 0.05 within 0..1 (rounded to 2 decimals). `enter` continues, `b` goes back to the tier 1 screen.
4. `confirm`: rows listing every lane with its final tier and trust, then the routing values, then the two file paths. `y` sets the result and moves to `done`; `n` or `q` moves to `quit` with no result; `b` returns to routing.
5. `q` on any screen before `confirm` moves to `quit` with no result.

The result `lanes_doc` is the incoming document with only `tier` and `trust` changed per lane, in the original key order; `routing_doc` likewise with only the edited values changed.

`run_curses(wizard)`: the renderer. Uses `curses.wrapper`. Maps arrow keys and `j`/`k` to `up`/`down`, space, Enter, `b`, `q`, `y`, `n`, `+`/`=` to `plus`, `-` to `minus`, digits, everything else to `other`. Draws title, a header row, the rows (cursor row bold or reverse, dimmed rows with `A_DIM`, marked rows prefixed `[x]`, unmarked `[ ]`), the footer, and the message line. Truncates cells to fit the terminal width, keeping the mark, lane, trust, and Epoch mean rank columns visible first. When the terminal is under 80 columns or 16 rows it draws one line asking the human to enlarge the window and redraws on resize. Returns when the wizard reaches `done` or `quit`.

## 3. `setup.py`: entry

Keep every existing function and the plain flow. Add `--plain`. Decide the mode after discovery and proposal: plain when `--plain` is given or when `sys.stdin` or `sys.stdout` is not a TTY; otherwise the TUI. In TUI mode: build the bench data with `bench.collect(lanes_doc, epoch_csv=args.epoch_csv, aa_json=args.aa_json, key_file=<config-dir>/aa-key)` unless `--no-bench` (then `None`); catch `BenchError` and pass `None` with the reason as the wizard's initial message; construct the `Wizard`; call `run_curses`; on a result, validate both documents and write them through `write_json` and print the two `wrote` lines; otherwise print `nothing written`. `--bench-report` stays a plain-mode option; in TUI mode it is ignored with a one-line note. Exit codes as today.

## 4. Tests

`tests/test_setup_tui.py` drives `Wizard` directly with key lists; no terminal needed. Build the sample catalog and a `collect()` result from `tests/fixture/bench-epoch.csv` (write that fixture so that the mean ranks put `claude-fable-5-1` first, then `gpt-5.6-sol`, and leave `gemini-3.8-flash-high` unknown). Cover at least:

1. First tier screen is tier 4; `fable-xhigh@claude` is marked; active rows are ordered by Epoch mean rank with the unknown model last; the Epoch columns show the fixture percents.
2. `enter` through all four tiers, `enter` on routing, `y` on confirm: the result equals the incoming documents exactly.
3. On tier 4 move the cursor to `sol-high@codex` and `space`, then `enter`: the tier 3 screen shows sol dimmed with tag `tier 4`; the final result has sol tier 4 and terra still 2.
4. On tier 2 highlight `grok46-high@grok` and press `4`: result trust 4; nothing else changed.
5. On tier 1 unmark `luna-low@codex` and press `enter`: message `every lane needs a tier`, screen still tier 1; mark it again and `enter` proceeds.
6. Routing: `down` to `classTier.review`, `plus` → 3; to `margin`, `plus` → 0.25; result reflects both; every other value unchanged.
7. `n` on confirm → `result()` is None and the screen is `quit`. `q` on a tier screen → same.
8. `b` from tier 3 returns to tier 4 with sol's mark from case 3 intact.
9. `bench=None`: the tier screens render with `—` in every benchmark column and the initial message is shown.
10. A pty smoke: with `pty.openpty()`, spawn `python3 setup.py --config-dir <tmp> --discover-json <fixture> --epoch-csv tests/fixture/bench-epoch.csv` with `TERM=xterm-256color`, `LINES=40`, `COLUMNS=140` in the environment, send Enter for discovery, Enter four times for the tiers, Enter for routing, `y` for confirm (with 0.3 s pauses), wait for exit within 30 s, then assert both files exist and pass `catalog.check_file`. Print `SKIP pty smoke: <reason>` instead of failing when the pty cannot be opened.

Also append to `tests/test_bench.py` nothing; instead verify in `tests/test_setup_tui.py` that `bench.collect` on the fixture returns the documented keys.

# Definition of done

All of these run clean from `agents/skills/delegate/` inside the worktree:

    python3 tests/test_setup_tui.py
    python3 tests/test_setup.py
    python3 tests/test_bench.py
    python3 tests/test_catalog.py
    python3 setup.py --help
    python3 -c "import setup_tui; print('ok')"

Run `git status --short` before you start and at the end: the only new differences are `bench.py`, `setup.py`, `setup_tui.py`, `tests/test_setup_tui.py`, and `tests/fixture/bench-epoch.csv`; files already modified or untracked when you started are the baseline. In the deliverable, list the files and paste the last 20 lines of the `test_setup_tui.py` output.
