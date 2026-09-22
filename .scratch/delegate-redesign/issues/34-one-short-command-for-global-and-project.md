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

- [x] `delegate global` runs the wizard target in the command's own checkout, from any
  directory.
- [x] `delegate project` opens the dashboard for the current directory's project, and
  outside a Git project it prints one line and exits 1.
- [x] `delegate`, `-h` and an unknown word behave as the Rule says.
- [x] Through a symlink, as stow links it, the command resolves the real checkout.
- [x] `make configs` links it; a dry run (`stow -n -v -d stow -t "$HOME" delegate`)
  shows the one new link and no conflict.
- [x] All delegate test suites pass.

## Landed

`stow/delegate/.local/bin/delegate`, 80 lines of Python 3 and stdlib only, with
`tests/test_delegate_command.py` beside the delegate tests: seven cases against a
temp checkout holding the layout the command walks up through, with `make` and the
dashboard stubbed, so no wizard, no dashboard and no terminal is ever started.
Docs: the Makefile header, the `SKILL.md` setup line and the dashboard's "How to
open it". The root `CLAUDE.md` is the session's.

The `make configs` dry run from this worktree:

    $ stow -n -v -d "$PWD/stow" -t "$HOME" delegate
    LINK: .local/bin/delegate => ../../.herdr/worktrees/dotfiles/worktree-delegate-redesign/stow/delegate/.local/bin/delegate
    WARNING! stowing delegate would cause conflicts:
      * existing target is not owned by stow: .config/delegate/lanes.json
      * existing target is not owned by stow: .config/delegate/routing.json
    All operations aborted.

The one new link is the command, and `~/.local/bin/delegate` does not exist yet, so
nothing conflicts with it. The two warnings are `~/.config/delegate/{lanes,routing}.json`,
which are stow links into `~/dotfiles` and so are not this worktree's to own; they say
the same thing on `main` today and have nothing to do with this ticket. The real
`make configs` runs from `~/dotfiles`, where stow owns them.

Session decisions, Orin's to overrule:

- The command spells out the Git-project walk rather than importing
  `catalog.find_git_root`. A command on PATH that has to load the skill to say it
  cannot find a project breaks whenever the skill does, and it lets the test stub
  the dashboard and still exercise the no-project path. The comment names
  `catalog.find_git_root` as the rule it mirrors.
- `global` passes the rest as one `WIZARD_ARGS=` make variable with each argument
  shell-quoted, so the recipe's shell re-splits them and a path with a space
  survives.
- An unknown word prints the two lines on stderr, not stdout: it is an error.
- `project` runs the dashboard with `sys.executable`, the same interpreter the
  command itself is running under, rather than whatever `python3` PATH gives.
