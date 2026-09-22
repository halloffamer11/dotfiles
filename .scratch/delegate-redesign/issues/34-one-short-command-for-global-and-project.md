# 34 — One short command for global and project settings

**What to build:** a `delegate` command on PATH with two subcommands, so Orin never
types a checkout path. Orin, 2026-09-22: "I also want to make sure there is clear
commands for global settings and a project specific setting that is a compact command
not a long directory".

**Blocked by:** 33 The wizard refreshes to the current generation, then screens it
(same worktree; both touch the Makefile and the skill docs).

## Rule

The session decisions below are Orin's to overrule.

- `delegate global` runs the global wizard: `make -C <checkout> delegate-wizard`,
  passing any further arguments through as `WIZARD_ARGS`. The Makefile stays the only
  place that lists the wizard's arguments.
- `delegate project` opens the dashboard for the Git project of the current directory,
  in the current terminal: `python3 <checkout>/tools/delegate-dashboard/dashboard.py
  --cwd "$PWD"`. Any further arguments pass through. It needs no Herdr. Outside a Git
  project it says so and exits 1.
- `delegate` with no argument, `-h` or `--help` prints the two lines and exits 0. Any
  other word prints them and exits 2.
- The command finds `<checkout>` from its own resolved path, never from a fixed
  `~/dotfiles`. It works from the Mac checkout, a Herdr worktree, and omarchy.
- It ships in the `delegate` stow package as `stow/delegate/.local/bin/delegate`, so
  `make configs` links it per file into `~/.local/bin`. Python 3, the same as the
  scripts it calls.
- The docs lead with the two short commands, and the long forms stay:
  `make -C … delegate-wizard`, `make delegate-dashboard` for a Herdr split, and the
  Herdr plugin key.

## Scope

- `stow/delegate/.local/bin/delegate` (new);
- a test beside the delegate tests that runs it against a temp checkout layout with
  the called programs stubbed;
- the Makefile header comment;
- root `CLAUDE.md` is the session's;
- `agents/skills/delegate/SKILL.md` (the setup line);
- `tools/delegate-dashboard/CLAUDE.md` ("How to open it").

## Acceptance

**Status:** ready-for-agent

- [ ] `delegate global` runs the wizard target in the command's own checkout, from any
  directory.
- [ ] `delegate project` opens the dashboard for the current directory's project, and
  outside a Git project it prints one line and exits 1.
- [ ] `delegate`, `-h` and an unknown word behave as the Rule says.
- [ ] Through a symlink, as stow links it, the command resolves the real checkout.
- [ ] `make configs` links it; a dry run (`stow -n -v -d stow -t "$HOME" delegate`)
  shows the one new link and no conflict.
- [ ] All delegate test suites pass.
