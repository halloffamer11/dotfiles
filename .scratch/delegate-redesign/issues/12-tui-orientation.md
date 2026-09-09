# 12 — Orientation and legends in the setup TUI

**What to build:** Orin ran the TUI wizard for the first time on 2026-09-09 and it worked — six lanes reassigned, `classTier.review` raised, both files valid. What it lacks is anything that explains the decision it is asking for. Every screen shows values and expects the human to already hold the definitions in their head. Four additions, all explanatory, none changing what the wizard writes.

**A start screen.** The wizard currently opens on harness discovery, which answers a question nobody asked. Before it, a screen that says in a few lines what this tool does: you are assigning each lane a tier and a trust, from the best tier down, with benchmark numbers beside each row to inform the tier; nothing is written until the confirm screen; `q` leaves without writing. Name the two files it will touch. Any key continues.

**Tier and trust definitions where the decision is made.** Put them on the start screen and keep a one-line form in the footer of every tier screen. Tier is capability, 1 to 4, and it is a ceiling: a class needing tier 3 can use a tier 3 or 4 lane and nothing lower. Trust is the human's ordering inside a tier, 1 to 5, from experience rather than benchmarks — it breaks ties that the numbers cannot. Neither is computed; both are the human's judgement, which is the whole reason this screen exists.

**A tier reference table on the routing screen.** When the human sets `classTier.review` to 3, nothing on screen says which lanes that admits. Show a compact map of tier to the lanes assigned to it in this session, so the routing numbers are read against real models rather than in the abstract. It must reflect the assignments just made, not the incoming catalog.

**A legend for margin and gate.** Both are bare decimals on the routing screen today. Margin is the pace advantage a lower-ranked lane needs before it steals the job from the pick — 0.2 means it must be beating the pick's pace by 0.2 to take over. Gate is the floor on meter remaining below which a lane is not eligible at all — 0.1 means a meter under 10% is skipped. Two lines, next to the values.

**Blocked by:** nothing. 07b landed.

**Status:** open, raised by Orin 2026-09-09 from the first live run of the wizard.

- [ ] A start screen states the task, names both files, and says nothing is written before confirm
- [ ] Tier and trust are defined on the start screen and recalled in the tier screens' footer
- [ ] The routing screen shows a tier-to-lanes map built from this session's assignments
- [ ] Margin and gate carry a one-line explanation each on the routing screen
- [ ] `tests/test_setup_tui.py` covers the start screen in the key sequence and asserts the routing view carries the tier map
- [ ] The written `lanes.json` and `routing.json` are byte-identical to what the same key sequence produced before this ticket
