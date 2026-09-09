# 11 — Entry points: typed harness wrappers, prose harness routing, and setup

**What to build:** Two entry problems, one surface.

**The wrappers ask Orin to type flags he will never type.** `/delegate-codex` today heads its body with `(--lane <name> | --model <slug>) </abs/brief.md> [--write </abs/worktree>] [--effort low|medium|high|xhigh]`. The intent was never that Orin resolves a lane by hand. Typing the skill name means *use this harness*; which lane inside that harness, at what effort, is the orchestrating agent's judgement, constrained by whatever Orin says in plain words alongside it. For example:

    /delegate-codex dont use astra, but any other lower model is ok. maximum effort medium

The wrapper reads `$ARGUMENTS` as prose constraints, not flags. It resolves the lane with the machinery that already exists — `rank.py <class> --harnesses codex --json` returns the ranked codex lanes as parseable data — then applies the stated exclusions and the effort cap to that list and dispatches the survivor through `delegate.py dispatch`. It states the pick and the reason in one line before it runs. When the constraints eliminate every lane it stops and names the constraint that did it; falling back silently to a lane Orin excluded is worse than not dispatching.

`disable-model-invocation: true` **stays** on all four wrappers. They are Orin's manual path. The model never fires them.

**The agent needs the same routing without the wrapper.** `/delegate` is model-invocable and gains the same prose constraint reading: a harness to prefer or avoid, models to exclude, a ceiling on effort, taken from the user's own words in the surrounding request. Ranking is otherwise unchanged — the tier ceiling, trust order, and pace margin still decide. Both paths reach `delegate.py`; neither is a special case of the other.

**Setup has no working entry point.** `SKILL.md` claims "`/delegate setup` is the wizard that builds or revises it". That command does not exist. Typing it passes the word `setup` as `$ARGUMENTS` to `/delegate`, and the body has no instruction that does anything with it, so it silently does nothing. Fix both halves: document the direct command `python3 ~/.claude/skills/delegate/scripts/setup.py`, and teach the `/delegate` body to run the wizard when the arguments ask for setup, so the documented command becomes true rather than deleted.

**Blocked by:** 10 (the script paths move; writing them twice is waste). 07b for `setup_tui.py` to exist behind the setup entry.

**Status:** open, raised by Orin 2026-09-09.

- [ ] The four wrappers keep `disable-model-invocation: true` and gain an `argument-hint` naming plain-language constraints
- [ ] No wrapper body documents a flag grammar; each reads `$ARGUMENTS` as prose
- [ ] A wrapper resolves its lane through `rank.py --harnesses <harness> --json` and prints the pick with its reason before dispatch
- [ ] Constraints that eliminate every lane stop the run and name the constraint; no silent fallback
- [ ] `/delegate` applies the same prose constraints when the agent routes on its own judgement
- [ ] `/delegate` run with setup arguments starts the wizard
- [ ] `SKILL.md` names the direct `setup.py` path and no longer claims anything untrue about `/delegate setup`
- [ ] Orin types each of the four wrappers once with a plain-language constraint and gets the lane he expected
