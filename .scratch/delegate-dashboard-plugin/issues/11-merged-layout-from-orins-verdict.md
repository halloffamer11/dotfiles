# 11 — Merged layout from Orin's layout verdict

**What to build:** one new throwaway layout variant, `deck`, that joins the parts of
`panel` and `strip` Orin kept, plus his six general changes. It sits beside the three
existing variants on `worktree/delegate-monitor-herdr-layouts` and `v` reaches it.

**Blocked by:** None — can start immediately.

**Status:** implemented 2026-09-18 (`c04a75d`) on `worktree/delegate-monitor-herdr-layouts` — Orin's live review of `deck` is open

## Verdict, Orin, 2026-09-18

The question was "what should the dashboard look like?" (prototype skill, UI branch).
Three variants were compared live: `current`, `panel`, `strip` (`1550823`).

1. `panel` and `strip` are both better than `current`. `current` is dropped.
2. Keep from `panel`: (a) the vertical coloured line per Tier on the left edge; (b) the
   terminal's default background; (c) progress bars drawn as solid rectangles.
3. Keep from `strip`: the quieter font colours, with gold for the selected Lane; the
   icons in column 1; the top row that names the leading model per Tier; the fixed
   top-right block for Gate, Margin, Meters and usage.
4. General changes:
   - (a) `luna-high@codex` followed by a `codex` column repeats itself, and `panel`
     repeats it across three columns. Show three columns instead: model, effort,
     Harness. Example: `Luna 5.6 | H | Codex`.
   - (b) Remaining, Pace, Gate, Margin and Meter each get a description the user can
     turn on and off.
   - (c) Replace the free-text note with a reason code. Keep the colour scale.
   - (d) Add a Harness view: Lanes grouped by Harness, by Tier inside each Harness.
   - (e) Folding a Tier moves the selection up to the Tier line. `j` and `k` then step
     over the folded Tier in one press and never walk hidden rows.
   - (f) `make delegate-dashboard` is acceptable for the prototype. The product needs
     a Herdr shortcut.

## Session decisions Orin may overrule

- The work is a fourth variant, not an edit of `panel` or `strip`, so the three stay
  comparable.
- Effort letters: `L`, `M`, `H`, `XH`, `Max`, `U` (ultra).
- The model display name comes from the Lane's `published_as` when present, else from
  the model slug by one rule in the variant. The catalog is not edited.
- (f) is a written proposal in this ticket's Landed note, not a change to Orin's Herdr
  configuration.

## Acceptance

- [ ] `--layout deck` opens and `v` cycles to it; the host keys are unchanged.
- [ ] 2a–2c and the four kept parts of `strip` are present.
- [ ] 4a: three columns, no `name@harness` string in a row; columns line up at 100,
      132 and 170 cells, and every painted line fits the width.
- [ ] 4b: one key toggles the descriptions; off is the default.
- [ ] 4c: a closed set of reason codes with a legend in the help view; no free-text
      note in a row.
- [ ] 4d: one key switches between the Tier view and the Harness view; selection and
      `J`/`K` behave the same in both, and `J`/`K` still move a Lane only inside its Tier.
- [ ] 4e: with a Tier folded, one `j` or `k` leaves it.
- [ ] 4f: the Landed note says how a Herdr shortcut can open the plugin pane, from the
      installed `herdr` help output, with the exact lines Orin would add.
- [ ] `python3 tools/delegate-dashboard/test_dashboard.py` passes; `proto_dump.py`
      frames for `deck` are saved under the effort's `_work/`.

## Landed, 2026-09-18

`c04a75d`, by `opus-high@claude` (named dispatch: TUI work goes to an Opus agent under
`/frontend-design:frontend-design`), run `20260919T014109Z-opus-high@claude-6f587bc0`,
1030 s, verdict clean. The boxes stay open until Orin drives `deck` in a pane: no one
pressed a key in a TTY.

Checked by the session: `test_dashboard.py` passes (42); `--layout deck --json` exits 0;
the 18 frames in the branch's `_work/deck/` (Tier and Harness view, folded, descriptions
on; 100, 132, 170 cells) are 34 lines each and none is over width by a cell-width count.

- Keys `deck` adds: `d` descriptions, `h` Tier or Harness view, `z` fold, `?` help.
- Reason codes: `PICK STEAL ELIG NOMTR GATE CLI FLOOR CEIL VETO`; `VETO` is the catch-all.
- 4e host change: a variant may define `selectable(state, view)`; `j`/`k` walk that list,
  and a folded Tier gives one name. Variants without the hook behave as before. The
  layout order is now fixed: `current, panel, strip, deck`.
- 4f: the installed Herdr can bind it. Proposed lines for `~/.config/herdr/config.toml`:

      [[keys.command]]
      key = "prefix+d"
      type = "shell"
      command = "herdr plugin pane open --plugin delegate.project-dashboard --entrypoint dashboard --placement split --focus"

  The session confirmed the `herdr plugin pane open` flags from its help and that
  `prefix+d` is not used in Orin's config. `type = "shell"` is the worker's claim and is
  not confirmed; `herdr config check` validates it. The plugin is linked to the layouts
  worktree, so the key opens the branch copy.

## Round 2, Orin, 2026-09-18 (after driving `deck` at `c04a75d`)

1. The Harness view becomes a table: one row per Harness, one column per Tier, the
   Lanes of that Harness and Tier in the cell. An empty cell is obvious. Clean, neat,
   focused.
2. The descriptions move to the bottom and favour readable text.
3. The reason codes (`STEAL`, `ELIG`, `GATE`, `NOMTR` and the rest) need definitions
   in the same place.
4. A visual aid shows how Gate and Margin act. Orin wrote "at the harness level". The
   rule acts per Meter: Gate compares a Meter's Remaining, and Margin compares the Pace
   of two Lanes' Meters; one Harness can own two Meters (`claude-general`,
   `claude-fable`). Session decision: draw the aid per Meter, grouped under its Harness.

- [ ] Harness table with obvious empty cells; selection, `J`/`K` and fold still work.
- [ ] Descriptions and code definitions sit at the bottom, off by default.
- [ ] Gate and Margin aid: per Meter, Remaining against the Gate mark, and Pace against
      the Pick's Pace plus Margin.

**Round 2 landed** as `47b2142`, same worker (about 960 s, verdict clean). Checked by the
session: 42 tests pass; `--layout deck --json` exits 0; 21 frames at 100, 132 and 170 cells
are 40 lines each and fit their width; the steal rule the aid draws matches
`rank.py:181` (`r["pace"] >= pick_row["pace"] + margin`, the Pick reassigned in the loop).
New key `a` opens the Gate and Margin aid; `h` opens the Harness table, where `j`/`k` walk
down each Tier column; `d` writes the five terms and the nine codes at the bottom. The
boxes stay open until Orin drives it.

## Round 3, Orin, 2026-09-18

1. In the Harness table `h` `j` `k` `l` move the selection and `H` `J` `K` `L` move the
   model; the view key leaves `h`.
2. "fix the agy meter, gate, and usage monitor": a backend change, ticket 31 of
   `.scratch/delegate-redesign/`.
3. `H`/`L` change a Tier. Orin: "allow projects to have a lanes customization", so the save
   is project scope: ticket 32 of `.scratch/delegate-redesign/`.

**Round 3 landed** as `3cb85fb` and `30e1785`, same worker (about 1440 s, verdict
findings: the first commit wrote the global catalog behind a `y` confirm because the scope
change reached the worker late; the second removes that path). `Tab`/`Shift+Tab` cycle the
views; `h`/`l` cross Tier columns in the table and fold or open a Tier in the list;
`model.move_lane_tier` saves `set lanes.<lane>.tier` at project scope and, until ticket 32
is merged into the branch, reports `Tier move needs the project Lanes backend (ticket 32)`
and writes nothing. The host now passes `model` to a variant that asks for it, and parses
the Left, Right and Shift+Tab sequences as one key for every layout. Checked by the
session: 42 tests pass; `--layout deck --json` exits 0; no `global` or `confirm` is left
in the variant; `panel`, `strip` and `current` are unchanged since `47b2142`.

**Backend merged into the layouts branch** (`ad0cdd1`, then `4580ae0`, then the probe fix
merge): tickets 29-32 of `.scratch/delegate-redesign/`. `H`/`L` now save
`<project>/.delegate/lanes.json`; the worker proved it on a scratch project with file
hashes of the global and live catalogs unchanged. agy shows Remaining and Pace. A Lane
whose Tier comes from the project carries a mark. Checked by the session: 44 tests pass;
the aid on live Meters shows figures for agy and both Claude Meters.
