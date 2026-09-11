# 20 — CONTEXT.md holds the glossary and the start page states only facts

**What to build:** A root `CONTEXT.md` defines the words the skill uses, once,
in the domain-docs convention adopted on 2026-09-10 (`docs/agents/domain.md`).
The wizard's start page stops teaching those words and shows only what the run
will do: the two files it will write, the benchmark page path, and the discovery
notices.

**Why.** Orin's first run of the wizard (2026-09-11): "People know what class,
tier, lane, model, harness, and so forth are." Today the start page spends four of
its lines on what a tier is and how to assign one, and the tier legend repeats
one of them on every tier page. The definitions are not wrong; they are in the
wrong place. A glossary the skills can read is the convention the repo just
adopted, and `CONTEXT.md` does not exist yet.

Terms the glossary must carry, each as the code uses it: harness, model, effort,
lane, class, tier (a ceiling), meter, meter weight, pace, margin, gate, carry
(the pre-screen's `enabled`), dominated, published name, relay, brief, run.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `CONTEXT.md` exists at the repo root, one definition per term, in the vocabulary `catalog.py`, `rank.py` and the wizard already use; `CLAUDE.md`'s domain-docs line points at it
- [ ] The start page shows the two output paths, the benchmark page path and the discovery notices, and no definition of a term; it fits an 80 by 24 window with room to spare
- [ ] The tier pages keep the one-line tier reminder only if a test shows a page without it is ambiguous; otherwise it goes too
- [ ] Ticket 12's orientation tests and ticket 07b's snapshot tests pass against the new page
- [ ] `--plain` prints the same facts as the TUI's start page
