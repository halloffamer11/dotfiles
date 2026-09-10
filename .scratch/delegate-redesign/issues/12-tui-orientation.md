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

- [ ] A start screen states the task, names both files, and says nothing is written before confirm
- [ ] Tier is defined on the start screen and recalled in the tier screens' footer
- [ ] The routing screen shows a tier-to-lanes map built from this session's assignments
- [ ] Margin and gate carry a one-line explanation each on the routing screen
- [ ] The confirm screen carries the same one-line explanations for `classTier`, `margin` and `gate`, so the values are not bare at the moment of writing
- [ ] The wizard renders the gathered benchmark data as a local HTML page for side-by-side reading, read-only, with no decision entered there
- [ ] `tests/test_setup_tui.py` covers the start screen in the key sequence and asserts the routing view carries the tier map
- [ ] The written `lanes.json` and `routing.json` are byte-identical to what the same key sequence produced before this ticket
