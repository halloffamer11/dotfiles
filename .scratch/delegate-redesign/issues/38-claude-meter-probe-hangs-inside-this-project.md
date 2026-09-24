# 38 — The Claude Meter probe hangs inside this project

**Blocked by:** None — can start immediately.

**What to find:** moved verbatim from the root `CLAUDE.md` on 2026-09-23.

- **The Claude Meter probe hangs inside this project.** `claude -p ... /usage` did not
  return within 45 s from a dotfiles checkout, and takes about 3 s from `~`. The probe
  runs from `~` (`fb845e3`), and the cause is not known.

**Status:** needs-triage

- [ ] The cause inside the project is known, or Orin closes this ticket.
