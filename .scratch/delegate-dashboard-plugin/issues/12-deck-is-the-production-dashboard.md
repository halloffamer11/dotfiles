# 12 — `deck` is the production dashboard

**What to build:** Orin, 2026-09-20: "lock in the deck layout as the production version."
The dashboard stops being a prototype with layout variants. `deck` is the one view.

**Blocked by:** None — can start immediately.

## Scope

Paths are relative to `tools/delegate-dashboard/` on branch
`worktree/delegate-dashboard-plugin` (based on `worktree/delegate-monitor-herdr-layouts`
with main merged).

- The view module: `proto_layout_deck.py` becomes `deck.py`. `dashboard.py` imports it
  directly. Remove the variant host: `--layout`, the `v` key, `LAYOUT_ORDER`, the
  `proto_layout_*` discovery and its import-failure message.
- Delete `proto_layout_current.py`, `proto_layout_panel.py`, `proto_layout_strip.py`,
  `proto_strip_dump.py`. Keep a frame dumper only if a test uses it; then name it
  `dump_frames.py`.
- Keep the host and view split that exists: the host owns the model, selection and the
  editors; the view draws and handles its own keys.
- Wording: no "prototype", "throwaway" or "PROTOTYPE" is left in the code, the context
  file, `herdr-plugin.toml` or the footer. `CLAUDE.md` in this directory describes the
  production dashboard: what it is, the keys, the model boundary, the save rules, how to
  open it, the tests. It says `../delegate-mon/` is the separate Rust monitor.
- The branch's own project policy does not reach main: remove `.delegate/` from this
  branch's tree (it was test data of the prototype branches).
- The root `Makefile` keeps the `delegate-dashboard` target.
- The root `CLAUDE.md` and the spec
  `docs/superpowers/specs/2026-09-13-delegate-dashboard-plugin.md` say the UI now ships
  from main; the older "UI stays on the branch" rule is recorded as superseded by Orin's
  word of 2026-09-20.

## Acceptance

**Status:** implemented 2026-09-20 (`a067fd5`) on `worktree/delegate-dashboard-plugin`. The root `CLAUDE.md` and spec wording landed as `972face` after Orin's word. Open: Orin's drive and merge.

- [ ] `python3 tools/delegate-dashboard/dashboard.py --cwd "$PWD"` opens `deck`; `--layout`
      is rejected as an unknown argument; `v` does nothing.
- [x] `grep -rni -E 'prototype|throwaway|proto_' tools/delegate-dashboard` prints nothing.
- [x] `python3 tools/delegate-dashboard/test_dashboard.py` passes, and `--json` exits 0.
- [x] No `.delegate/` directory is tracked on the branch.
- [x] Every suite under `agents/skills/delegate/tests/` still exits 0.
- [ ] Orin drives the production dashboard once in a Herdr pane and merges the branch.

## Landed, 2026-09-20

`a067fd5`. Named dispatch to `opus-high@claude` (the settled rule sends TUI work to a Claude
Opus agent; grok was at 0% and codex at 1%), run
`20260921T010032Z-opus-high@claude-b1f939a8`, about 780 s, verdict partial.

Done: `proto_layout_deck.py` is `deck.py` and `dashboard.py` imports it; `--layout`, `v`,
the layout discovery, the three other layouts and both dumpers are gone (no test used a
dumper, so no `dump_frames.py`); the `prototype` state key and the wording are removed;
`.delegate/routing.json` left the tree; this directory's `CLAUDE.md` describes the
production dashboard. The worker dumped 21 `deck` frames (100, 132 and 170 cells) before and
after: two lines differ, both forced by removing `v` (the footer tail `layout: deck (v
next)` and the help line's `v next layout`).

Checked by the session: `test_dashboard.py` ends `OK`; `--json` exits 0; `--layout deck` is
rejected as an unknown argument; the wording grep and `git ls-files .delegate` print
nothing; all 13 suites under `agents/skills/delegate/tests/` exit 0. Box 1 stays open: no
one pressed `v` in a TTY.

Not done: the root `CLAUDE.md` and the spec still say the UI stays on the branch. The
worker's permission check refused both edits, so the session did not apply the worker's
text either. Orin said yes on 2026-09-20 and the session wrote both in its own words (`972face`).
