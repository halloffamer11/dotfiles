# Delegate

External worker routing lives in this directory. Read `SKILL.md` first.

## Where detail lives

- `references/architecture.md`: what each script and asset owns, the project routing
  path, read-only and browser use per harness, and the benchmark sources. Read it before
  you change a script.
- Settled decisions: `docs/adr/0001-settled-delegate-decisions.md` at the repo root. Do not
  reopen one.
- Open work: `.scratch/delegate-redesign/issues/` and, for browser dispatch,
  `.scratch/delegate-browser/issues/`. The design is
  `docs/superpowers/specs/2026-09-08-delegate-redesign.md`.

## Rules

- Run the wizard with `--config-dir` at the repo's `stow/delegate/.config/delegate`, or
  through `make delegate-wizard`: a write to the stowed `~/.config/delegate/lanes.json`
  replaces the link with a plain file.
- Before you change browser dispatch, read the browser section of
  `references/architecture.md` and
  `.scratch/delegate-browser/research/2026-09-10-browser-routes.md`.
- Do not pass `--write` to get agy's tools working; read-only is sandboxed per harness.
- `tests/` holds one test file per script, stdlib only, no network.
- Constraints for workers: the lane comes from `rank.py`; a lower lane needs a one-line
  reason. Unrelated working-tree files stay untouched.
