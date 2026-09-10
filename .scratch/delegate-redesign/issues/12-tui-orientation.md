# 12 — Orientation and legends in the setup TUI

**What to build:** Orin ran the TUI wizard for the first time on 2026-09-09 and it worked — six lanes reassigned, `classTier.review` raised, both files valid. What it lacks is anything that explains the decision it is asking for. Every screen shows values and expects the human to already hold the definitions in their head. Four additions, all explanatory, none changing what the wizard writes.

**A start screen.** The wizard currently opens on harness discovery, which answers a question nobody asked. Before it, a screen that says in a few lines what this tool does: you are assigning each lane a tier, from the best tier down, with benchmark numbers beside each row to inform the tier; nothing is written until the confirm screen; `q` leaves without writing. Name the two files it will touch. Any key continues.

**The tier definition where the decision is made.** Put it on the start screen and keep a one-line form in the footer of every tier screen. Tier is capability, 1 to 4, and it is a ceiling: a class needing tier 3 can use a tier 3 or 4 lane and nothing lower. It is not computed; it is the human's judgement, which is the whole reason this screen exists. Lanes alike on tier are equivalent, and ranking separates them by pace.

**A tier reference table on the routing screen.** When the human sets `classTier.review` to 3, nothing on screen says which lanes that admits. Show a compact map of tier to the lanes assigned to it in this session, so the routing numbers are read against real models rather than in the abstract. It must reflect the assignments just made, not the incoming catalog.

**A legend for margin and gate.** Both are bare decimals on the routing screen today. Margin is the pace advantage a lower-ranked lane needs before it steals the job from the pick — 0.2 means it must be beating the pick's pace by 0.2 to take over. Gate is the floor on meter remaining below which a lane is not eligible at all — 0.1 means a meter under 10% is skipped. Two lines, next to the values.

## Decisions 2026-09-10

**A side-by-side benchmark data view.** Orin ran the wizard on 2026-09-10 and
the benchmark evidence was not in front of him while he assigned tiers. The
curses table cannot carry per-effort score-and-cost for ~30 lanes legibly, so
the wizard renders the collected data as a **local HTML page, read side by side
with the tier screens**. It is a read-only view of data already gathered — the
`bench.py` report plus whatever `effort.py` has extracted per effort — not a
second place to make the decision. Nothing is entered there; tiers are still set
in the TUI. This is what "the html popup" meant in earlier sessions; it had
never been written down.

**The legend gap is on the confirm screen, not only the routing screen.** The
four additions above put the margin and gate legend on the *routing* screen.
Orin hit the missing context on the **final/confirm screen**, which repeats
`classTier`, `margin` and `gate` as bare values before writing. Carry the same
one-line explanations onto the confirm screen. Acceptance below is extended.

**Blocked by:** nothing. 07b landed.

**Status:** open, raised by Orin 2026-09-09 from the first live run of the wizard.

- [x] A start screen states the task, names both files, and says nothing is written before confirm
- [x] Tier is defined on the start screen and recalled in the tier screens' footer
- [x] The routing screen shows a tier-to-lanes map built from this session's assignments
- [x] Margin and gate carry a one-line explanation each on the routing screen
- [x] The confirm screen carries the same one-line explanations for `classTier`, `margin` and `gate`, so the values are not bare at the moment of writing
- [x] The wizard renders the gathered benchmark data as a local HTML page for side-by-side reading, read-only, with no decision entered there
- [x] `tests/test_setup_tui.py` covers the start screen in the key sequence and asserts the routing view carries the tier map
- [x] The written `lanes.json` and `routing.json` are byte-identical to what the same key sequence produced before this ticket

## Landed 2026-09-10

`view()` gained two keys, `body` (prose lines, for a screen that is not a table)
and `legend` (lines rendered between the table and the footer). `run_curses`
renders both. Everything else about the render contract is unchanged, so
`_fit_table` was not touched.

Two deviations from the wording above, both to keep the screens legible at the
80x16 minimum the wizard already enforces:

- The tier definition is the **last legend line**, not inside the footer string.
  The definition and the key hints together run to about 165 characters; in an
  80-column footer that truncation would have eaten the key hints. The legend's
  last line renders directly above the footer, so it reads as a second footer
  line. Every legend sentence is now under 80 characters for the same reason — a
  legend cut mid-sentence explains nothing.
- The table region scrolls to keep the cursor row visible. The routing screen
  carries six legend lines, which at 16 rows left too little room for its seven
  settings, so the cursor could have sat on a row that was not on screen.

An empty tier reads `tier 4: (none)` rather than a label with nothing after it.

The HTML page is `scripts/bench_page.py`, self-contained: no script tag, no
remote stylesheet, no web font, verified by a test. `setup.py` writes it to a
temp file before curses starts and `--effort-rows` feeds it an `effort.py check`
`accepted.json`; all 26 rows of the real swerb output render, grouped by model
then by effort in capability order. `o` opens it as a `file://` URI, wrapped so a
headless machine cannot take the TUI down.

Verified by driving the real curses renderer in an 80x16 pty: the tier map, both
legends and the cursor row on the last setting are all on screen.
