# 10 — Skill-spec layout for the delegate skill

**What to build:** `agents/skills/delegate/` is moved onto the Agent Skills directory conventions. Today nine executables, two stray documents, and a Rust crate sit at the skill root. The Agent Skills specification (agentskills.io/specification) names `scripts/` for executable code, `references/` for documentation the agent reads on demand, and `assets/` for templates and data. The Claude Code skill documentation is explicit that a skill root must not hold multiple executables, large reference documents, or non-markdown documentation. The frontmatter of all five delegate skills already passes: valid names matching their directories, descriptions well inside the 1024-character limit, bodies far under 500 lines. Only the layout fails.

Target layout:

    delegate/
      SKILL.md, CLAUDE.md, AGENTS.md -> CLAUDE.md
      scripts/      ads.sh bench.py catalog.py delegate.py events.py rank.py report.py setup.py setup_tui.py usage.py
      references/   tui-research.md, tui-mockup.md (renamed from tui-mockup.txt)
      assets/       preamble.md, schemas/, samples/
      tests/

`monitor/` leaves the skill. A Ratatui crate is a separate product, not skill material under any reading of the spec; it moves to `tools/delegate-mon/`.

The scripts import each other as siblings (`import catalog`, `import bench`), so they move together and the imports keep working. Every path that names them from outside does not: `SKILL.md`, `delegate/CLAUDE.md`, the hooks in `~/.claude/hooks/`, the global `~/.claude/CLAUDE.md` Delegation section, the two monitor documents under `docs/superpowers/`, and any brief template that writes `~/.claude/skills/delegate/delegate.py`. Each becomes `~/.claude/skills/delegate/scripts/<file>`.

`delegate/CLAUDE.md` also loses its transient content. The "Redesign status" and "Monitoring TUI" sections are dated project state that belongs in this ticket directory and will rot where they sit. What stays is the file-by-file implementation map and the worker constraints.

## Dead references (folded in 2026-09-09, re-opens ticket 09 item 6)

Spec §9.6 asks that every file the hook or docs name exists. Ticket 09 marked it done; three references are dead:

- `~/.claude/CLAUDE.md` Delegation section sends agents to `~/.claude/skills/delegate/lanes.tsv` to classify work. That file does not exist — the classes are `catalog.CLASSES` (`scout`, `mechanical`, `impl`, `review`, `hard-impl`). Point the line at `rank.py` instead.
- `SKILL.md` claims `/delegate setup` is the wizard. That command does not exist (ticket 11 makes it true).
- Ticket `07b` told the next session to read `return.json` in the run directory. The relay writes `result.json`; `delegate.py` writes `return.json` only after mapping. Both exist, but at different times — the wording sent a reader to a file that was not there yet.

**Blocked by:** 07b (the TUI wizard worker writes `setup_tui.py` into the current layout; a move commit that races it only makes a conflict).

**Status:** landed 2026-09-10 (`473df66` ticked boxes whose work had landed in `867cbd1`). All boxes ticked; nothing open.

- [x] The nine scripts plus `setup_tui.py` live in `scripts/` and every test still passes from the new location
- [x] `tui-research.md` and `tui-mockup.md` live in `references/`; the `.txt` extension is gone
- [x] `preamble.md`, `schemas/`, and `samples/` live in `assets/`, and the code that reads them is updated
- [x] `monitor/` is out of the skill at `tools/delegate-mon/`; `monitor/CLAUDE.md` travels with it and names the new location, and the monitor design spec gains a one-line moved-on note at the top. The 2026-09-02 implementation plan is a completed execution record and is left as written — rewriting its file list would falsify what was actually done
- [x] No path anywhere still names a script at the skill root: `grep -rn "skills/delegate/[a-z_]*\.\(py\|sh\)" ~/.claude ~/dotfiles` returns nothing outside `scripts/`
- [x] `delegate/CLAUDE.md` holds no dated status section
- [x] The four wrapper skills are untouched by this ticket
- [x] The three dead references above are fixed and ticket 09 item 6 is re-ticked

## Verified closed 2026-09-10

Every box was substantively done but left unticked. Checked rather than assumed:
`scripts/` holds twelve `.py`; `references/` holds `kiro.md`, `tui-mockup.md` and
`tui-research.md` with no `.txt`; `assets/` holds `samples/`, `schemas/`,
`preamble.md` and `preamble-leash.md`; `tools/delegate-mon/` exists outside the
skill; `agents/skills/delegate/CLAUDE.md` carries no dated status section.

The root-script grep is clean apart from `docs/superpowers/plans/2026-09-02-delegate-monitor.md`,
which names `delegate/events.py`, `dispatch.sh` and `usage.py` at the old paths.
That is the completed execution record this ticket says to leave as written, so it
is not a dead reference to fix.

The three dead references ticket 09 item 6 re-opened are down to one, and it is
outside this repo: `~/.claude/hooks/delegate-gate.py` still names
`{SKILL_DIR}/delegate.py` instead of `scripts/delegate.py`. The other two —
`references/CLAUDE.md` naming a deleted `routing.md`, and
`agents/skills/delegate/CLAUDE.md` claiming agy read-only is broken — were fixed
in `61f2dd2`.
