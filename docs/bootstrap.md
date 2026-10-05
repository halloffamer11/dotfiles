# Bootstrap and maintenance

One clone, one command. `make` picks a profile from the machine: `macos` on Darwin,
`omarchy` where `/usr/share/omarchy` or `~/.local/share/omarchy` exists, otherwise
`linux`. To choose a profile yourself, pass `make PROFILE=linux <target>` or put
`PROFILE = linux` in `local.mk`. A `CONFIG_PACKAGES` line in `local.mk` still
overrides the profile's package list.

Before any change, `make configs-plan` shows the profile, the links it would make and
the files in their way. It writes nothing.

## Site and machine deployments

Each machine that runs this repo is a machine deployment; a group of machines that
share settings is a site deployment. The repo holds only the generic layer: profiles
and packages. Anything specific to one site or one machine (identity, hosts, paths,
package choices, credentials) goes in machine-local files that git ignores or that
live outside the repo: `local.mk`, `~/.gitconfig.local` and `~/.zshrc.local`. Never
commit them, and never name the site or machine in a commit, ticket or doc.

`~/.gitconfig.local` is read last, so what it sets (the machine's git identity first)
wins over the repo's defaults. `~/.zshrc.local` is sourced at the end of `.zshrc`, and
`local.mk` is read before the Makefile sets its defaults.

## macOS

Run these from your home directory on a new Mac:

1. `xcode-select --install`
2. Install Homebrew from https://brew.sh
3. `git clone https://github.com/halloffamer11/dotfiles.git ~/dotfiles`
4. `make -C ~/dotfiles bootstrap`

Bootstrap stops before it changes anything if Homebrew is missing. After `brew bundle`,
it stops if a real file sits where a link belongs. Compare that file with the repo's
copy, move it aside (`mv ~/.zshrc ~/.zshrc.pre-dotfiles`), and run bootstrap again.

You still do these by hand, because no command can:

- Remap Caps Lock to Control (System Settings, Keyboard, Modifier Keys).
- Create `~/.gitconfig.local` with this machine's git identity, and `~/.zshrc.local`
  for anything that belongs to this machine only.
- Run `codex login`, then `make -C ~/projects/delegate delegate-codex-home`. Bootstrap
  reminds you if you skip it.
- Run `gh auth login`.
- For the meeting recorder, grant Screen & System Audio Recording and Microphone to
  both the terminal and Hammerspoon (Privacy & Security). Without the grant, macOS
  records silence and reports no error.
- Delegate's catalog: `make -C ~/projects/delegate delegate-wizard`.

`make -C ~/dotfiles doctor` then lists whatever is still missing.

## Omarchy

Bootstrap installs no system packages. Install git, make, stow, node and npm with
pacman first; bootstrap names any that are missing. Install gitleaks too (see
Secret scanning).

1. `git clone https://github.com/halloffamer11/dotfiles.git ~/dotfiles`
2. `make -C ~/dotfiles bootstrap`

This links the common configuration plus Bash, Ghostty, Herdr, Hyprland and Voxtype,
installs the declared skills and the Claude agents, and installs delegate. The by-hand
list is the macOS one, minus Homebrew, Hammerspoon and the recording grants.

## Generic Linux

The steps are the Omarchy ones. Only the portable layer is linked (claude, git, nvim,
starship, yazi), and the result names the packages it left out. The tools those
configs call (neovim, starship, yazi and the rest) come from your distribution.

## Secret scanning

The git package sets `core.hooksPath` to `~/.config/git/hooks`. Before each commit, in
every repository, the pre-commit hook runs gitleaks on the staged changes and stops the
commit if it finds a secret. Then each hook runs the repository's own copy from
`.git/hooks`, if it has one.

- The Brewfile installs gitleaks on macOS. On Linux, install it with your distribution's
  package manager. Without it, the hook warns and the commit goes through unscanned.
- To skip the scan for one commit, run `SKIP_GITLEAKS=1 git commit ...`. For a false
  positive, add the fingerprint that the report prints to the repository's
  `.gitleaksignore`.
- A repository that sets its own `core.hooksPath` (for example, with Husky) does not use
  these hooks. The `pre-commit` framework refuses to install while a global
  `core.hooksPath` is set.

## Bring an existing machine up to date

`dots` does it all: it pulls `~/dotfiles`, and `make apply` then pulls delegate
(`make delegate` fast-forwards `~/projects/delegate` when it is on `main` with no local
changes), reinstalls it, and fetches its relays at the pinned commit.

1. `dots`
2. `make -C ~/dotfiles doctor`, and fix each `ACTION` line it prints. A delegate
   checkout on another branch or with local edits is not pulled; doctor reports it as
   behind, and you pull it yourself.

## Maintenance

Run these from any directory, the same on every profile:

- `dots`, a shell alias in zsh and bash. It pulls `~/dotfiles`, then runs `make apply`,
  which relinks the configuration, refreshes the declared skills from upstream, and
  pulls and reinstalls delegate.
- `make -C ~/dotfiles update`. On macOS it reconciles the Brewfile and updates the
  declared skills. On Linux it updates the skills only.
- `make -C ~/dotfiles doctor`. It is read only and reports the profile, missing
  prerequisites, files in the way, links not in place yet, broken links into the repo,
  declared skills that are missing, gitleaks, the delegate checkout, relays and catalog,
  and a dotfiles or delegate checkout that is behind its upstream `main` (it asks the
  remote; `make doctor DOCTOR_UPSTREAM=` skips that). It exits non-zero when a line
  says `ACTION`.
- `make -C ~/dotfiles test-bootstrap` runs the isolated-home checks for every profile.
  It needs GNU Stow and never touches your own home.
