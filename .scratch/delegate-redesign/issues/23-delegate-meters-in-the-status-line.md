# 23 — Delegate meters in the Claude Code status line

**What to build:** Rows under the Claude Code status line that show, for every
meter in the effective catalog, how much of the 5-hour and weekly windows is
left and when each resets; which tier each harness is winning right now; and
how many agents are running on it, by tier. A `report.py statusline`
subcommand renders the rows from the cached meters, the catalog, the ledger
and the ranker; `statusline.sh` appends its output. Nothing here probes a
harness, and nothing here dispatches.

**Blocked by:** None — can start immediately. Ticket 22 landed the floor and
ceiling routing this reads.

**Category:** enhancement

**Status:** implemented 2026-09-11 on branch `worktree/quiet-forest-811d`; the
last box is Orin's and needs `main` to carry the branch first (the installed
skill is `main`'s), then one `usage.py --refresh` so the cache gains
`remaining_weekly_model`. Raised by Orin 2026-09-11 ("some sort of TUI thing
in Claude that will give me some indication of how many agents are running on
which harness and then some of the harness usage levels ... ideally it's
something collapsible"). Prototyped the same day; Orin chose variant H. Branch
`prototype/delegate-statusline` holds the prototype.

- [x] `python3 scripts/report.py statusline` prints one row per catalog meter in the form below, and prints nothing (exit 0) when the usage cache is missing or unreadable, so the status line never breaks
- [x] Every gauge is **remaining**, fuel-gauge style: 100% is a full window
- [x] A meter with no 5h window (grok) shows `—` in the 5h cell; a model meter that shares its harness's 5h window (fable) leaves the 5h cell blank
- [x] The badge column shows the tier of every lane `rank.py` currently picks on that meter, one circled digit per tier, deduplicated; rows with a badge sort first by lowest tier, the rest keep catalog order
- [x] A meter at or below `gate` carries a red `✗` after its weekly cell
- [x] The trailing column shows one circled digit per running agent on that meter, in the agent's lane tier; a run is a `dispatch.start` with no `dispatch.finish` whose `ts + timeout_s` is still in the future
- [x] `usage.py` writes `remaining_weekly_model` on a model meter (claude-fable): the model's own weekly figure, while `remaining_weekly` stays `min(all-models, model)` for ranking. The fable row shows `remaining_weekly_model`
- [x] `stow/claude/.claude/statusline.sh` appends the rows after its second line and drops its own `🕔` segment, which duplicated the claude 5h cell; bash 3.2 and BSD userland still work; a missing `python3` or `report.py` adds no rows and no error
- [x] `tests/test_report.py` covers the rows from fixture usage, ledger and the sample catalog through `--config-dir`, `DELEGATE_CACHE` and `DELEGATE_LEDGER`; `tests/test_usage_reset.py` (or `test_events.py`) covers the new field. Full suite green
- [x] Orin sees the rows in a live session (his): seen 2026-09-11 23:14, which showed the unbadged rows pulled to column 0
- [x] Every row starts with a non-space glyph, so Claude Code's per-row trim cannot shift the columns: an unbadged row carries a dim `·` in the badge column
- [x] `report.py statusline off|on|toggle|status` switches the rows through the flag file `~/.cache/delegate/statusline.off` (`DELEGATE_STATUSLINE_SWITCH` in tests); while it exists `statusline` prints nothing and exits 0. Covered in `test_report.py`
- [x] A keyboard shortcut runs the toggle from any terminal: ⌥⌘D in `stow/hammerspoon/.hammerspoon/init.lua`, next to the ⌥⌘R recorder
- [ ] Orin presses ⌥⌘D once in each direction (his; Hammerspoon is running since 2026-09-11 21:04 and `~/.hammerspoon` is the Makefile's whole-directory symlink into the repo, so the binding is live after the merge, and stow must never touch that package)

## The row

Live 2026-09-11 after the tweaks below, no running agents:

```
②  agy    5h █████ 100%·4h wk ███▎░  66%·5d
③  grok   5h ·····    —    wk ▉░░░░  17%·4d
·  fable                   wk ██▊░░  54%·3d
·  claude 5h ████▋  92%·4h wk ██░░░  41%·3d
·  codex  5h █████ 100%·4h wk ▍░░░░   8%·3d✗
```

With running agents the trailing column carries one circled digit per agent
in its lane's tier, for example `②②` after agy's weekly cell.

- Label: the harness name, unless the harness has several catalog meters, then
  the meter suffix with `general` meaning the harness (`claude-general` →
  `claude`, `claude-fable` → `fable`, `agy-gemini` → `agy`).
- Colour: label and badge in the tier colour (① green, ② cyan, ③ yellow,
  ④ magenta — the `statusline.sh` fallback hex values); `✗` red; everything
  else foreground or dim. No red/yellow/green on percentages: Orin rejected
  load colouring in round 2.
- Bar: five cells, eighth-block fractions, remaining from the left; `·····`
  when the window does not exist.
- Reset: the largest whole unit, floored (`4d`, `2h`, `46m`).
- Circled digits ①–④ are East Asian "ambiguous" width; WezTerm draws them one
  cell wide by default. If another terminal draws them wide the columns shift;
  that is accepted for now.

## Decisions 2026-09-11

**Where it lives.** Claude Code has no custom collapsible panel. The status
line is the only surface that can show custom rows, and it re-runs on a 30 s
timer and on each assistant message. The `⇄` running column is the
"collapsible" part: it is blank when nothing runs. The `delegate-mon` crate
stays the full cockpit for a herdr pane; this ticket does not touch it.

**Remaining, not used.** Rounds 1–2 showed percent used; Orin: "I'd like it to
be percent remaining. So 100% is full capacity. It's like a fuel gauge."

**Colour means tier, not load.** Orin: "what I want is to know which harness is
getting which tier currently." The badge is the tier of the lane `rank.py`
picks for each class, evaluated live with the effective routing. The first
prototype run showed fable winning ③ by stealing from grok; ticket 22's ceiling
fixed that the same afternoon, and the badges now read ② agy, ③ grok. No class
routes to tier 4, by design (ticket 01 q1b), so ④ appears only in the running
column.

**Fable is its own row** (Orin), sharing claude's 5h window. `usage.py` today
folds the model figure into `remaining_weekly` as a min, and the model's own
number survives only in the `note` text; the prototype regex-parsed the note,
which the real build must not.

**Known gap.** A native Claude lane (ticket 22) writes no `dispatch.start`, so a
native run never appears in the running column. It is counted only after the
lead logs it with `report.py log`.

## Prototype

`git show prototype/delegate-statusline:.scratch/delegate-redesign/prototype/statusline_variants.py`
— four round-3 variants over live data; `tier_winners()` there still reads the
pre-22 `classTier` key. Round 1–2 variants (A–E) were dropped for showing
percent used with load colours.

## Landed, 2026-09-11

Commit `071a390` on `worktree/quiet-forest-811d`: `report.py statusline`,
`remaining_weekly_model` in `usage.py`, the two test files, and
`stow/claude/.claude/statusline.sh`. Ticket text: `7b6a8e6`.

Built by `flash-high@agy` (run `20260911T190256Z-flash-high@agy-bfce862a`,
550 s, status `done`). Lead review found one defect: the worker made
`statusline.sh` prefer a `report.py` found under the current project's
`agents/skills/delegate/scripts/`, which would run code from whatever repo is
open on every refresh. Removed; the installed skill is the only source.

Verified by the lead, not the worker's claim: the six test files pass in
place (test_report 79, test_usage_reset 1, test_events 1, test_rank 28,
test_catalog 76, test_dispatch 38; 0 fail); `report.py statusline` renders the
live cache in 0.05 s; the stowed script, run with a fake `$HOME` whose skill
symlink points at this worktree and whose caches link to the real ones,
prints the two original lines without `🕔` and then the five rows in both
styles; with no skill installed it prints two lines and no error.

Row order among unbadged meters is the catalog's `meters` order, so fable
sits above claude in the live file. Reorder `lanes.json` to change it.

## Tweaks, 2026-09-11

Orin's first live screenshot (23:14) showed fable, claude and codex starting
at column 0 while agy and grok started after their badge. `report.py` emitted
three leading spaces on those rows; Claude Code trims leading whitespace from
each status line row before drawing it (not documented on the statusline page,
established from the screenshot against the script's bytes). Fix: the badge
column is never blank; an unbadged row shows a dim `·`. Trailing whitespace
was already stripped by the script.

Orin also asked for an on/off switch, "best-case a keyboard shortcut". Claude
Code's `keybindings.json` binds built-in actions only (checked against the
keybindings reference the same day: no action runs a command, a skill, or
touches the status line), so the switch is a flag file that the next refresh
follows within 30 s:

```
python3 ~/.claude/skills/delegate/scripts/report.py statusline off|on|toggle|status
```

Typed at the Claude prompt as `! python3 … statusline toggle` it costs no
model turn. Orin is moving from WezTerm to Ghostty, and Ghostty keybinds send
text or escape sequences only (checked against the Ghostty keybind reference
the same day: `text:`, `csi:`, `esc:`, no action runs a program), so the
shortcut lives in Hammerspoon, which already runs a shell task on ⌥⌘R:
⌥⌘D runs `report.py statusline toggle` and shows the result as an alert.
`wezterm.lua` is untouched.

Verified: `test_report.py` 87 PASS (was 79), the other five files unchanged
and green; live render shows every row starting with a glyph; `off` printed
zero rows and `toggle` restored five against a scratch flag path, and
`~/.cache/delegate/statusline.off` does not exist afterwards.
