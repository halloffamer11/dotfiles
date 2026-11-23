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

The Herdr desktop app installs and updates itself, outside Homebrew. The Herdr
TUI (the `herdr` command) is not part of this setup. Bootstrap copies the app's `keys.json` in
only when none is there, because the app does not reload a linked file; after you
change keys in the app, copy `~/.config/herdr-app/keys.json` back to
`stow/herdr-app/` to commit it.
Brew supplies the public Node/npm commands. Keep application-private runtimes
inside their application directories.

You still do these by hand, because no command can:

- Remap Caps Lock to Control (System Settings, Keyboard, Modifier Keys).
- Create `~/.gitconfig.local` with this machine's git identity, and `~/.zshrc.local`
  for anything that belongs to this machine only.
- Run `codex login`.
- Run `gh auth login`.
- For the meeting recorder, grant Screen & System Audio Recording and Microphone to
  both the terminal and Hammerspoon (Privacy & Security). Without the grant, macOS
  records silence and reports no error.

`make -C ~/dotfiles doctor` then lists whatever is still missing.

## Omarchy

Bootstrap installs no system packages. Install git, make, stow, node and npm with
pacman first; bootstrap names any that are missing. Install gitleaks too (see
Secret scanning).

1. `git clone https://github.com/halloffamer11/dotfiles.git ~/dotfiles`
2. `make -C ~/dotfiles bootstrap`

This links the common configuration plus Bash, Ghostty, Hyprland and Voxtype,
installs the declared skills and the Claude agents. The by-hand
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

`dots` does it all: it pulls `~/dotfiles`, and `make apply` then relinks the
configuration and refreshes the declared skills.

1. `dots`
2. `make -C ~/dotfiles doctor`, and fix each `ACTION` line it prints.

## Maintenance

Run these from any directory, the same on every profile:

- `dots`, a shell alias in zsh and bash. It pulls `~/dotfiles`, then runs `make apply`,
  which relinks the configuration and refreshes the declared skills from upstream.
- `make -C ~/dotfiles update`. On macOS it reconciles the Brewfile and updates the
  declared skills. On Linux it updates the skills only.
- `make -C ~/dotfiles doctor`. It is read only and reports the profile, missing
  prerequisites, files in the way, links not in place yet, broken links into the repo,
  declared skills that are missing, gitleaks, and a dotfiles checkout that is behind
  its upstream `main` (it asks the
  remote; `make doctor DOCTOR_UPSTREAM=` skips that). It exits non-zero when a line
  says `ACTION`.
- `make -C ~/dotfiles externals` and `make -C ~/dotfiles external-updates`
  install or refresh the declared skills from their source for Claude Code, Codex
  and Antigravity CLI. In `local.mk`, use `CORE_SKILLS` for names from
  `halloffamer11/skills` and `PERSONAL_PACK_SKILLS` for `facebook-marketplace` from
  `halloffamer11/skills-personal`. Existing `PERSONAL_SKILLS` overrides keep their combined selection. An empty list skips its Pack.
  Humanizer comes from `blader/humanizer`.
- `make -C ~/dotfiles test-bootstrap` runs the isolated-home checks for every profile.
  It needs GNU Stow and never touches your own home.

## Agentic Layer with chezmoi

The first chezmoi scope deploys the Belt on macOS and Omarchy. Its source is
`home/`. The Make targets above remain the Stow fallback. Give each deployed
path one owner. Use the conversion runbook before switching an occupied Machine.

On a new Machine, install Git and mise, make Python 3 available for the initial
hook edits, and put mise's shims on PATH in the login shell. With chezmoi
installed, run `chezmoi init --apply halloffamer11/dotfiles`. To bootstrap
chezmoi itself, use `mise exec chezmoi@latest -- chezmoi init --apply halloffamer11/dotfiles`.
Prepare any Site kit first. Init detects the Platform and asks which Packs to
install and which T3 Antigravity provider instance IDs to use. The default ID
is `antigravity`. The answers live in the Machine's chezmoi config.
Use `chezmoi init --prompt` to choose again. To take part of a Pack, set
`core = ["toolsmith", "council"]` under `[data.skillSelection]` in that config.
An omitted selection takes every enabled skill declared for the Pack.

On an occupied Machine, use `chezmoi init` first. Back up the current global
skills (contents, link targets and lock file), user MCP entries and replaced
rules locally. Move a provider's existing plain MCP config into that backup.
Release each path from its previous owner, inspect `chezmoi diff`, then use
`chezmoi apply`. The skills installer can replace a same-name directory.
Review and trust the Codex session hook in `/hooks`, including after it changes.

### Site kit

Place these optional files under `~/.config/fleet/site/`. Templates use this
absolute location. A site-owned checkout should have read-only upstream access.

| File | Contents |
| --- | --- |
| `rules.md` | Text appended to all three global rules files. The total must be under 24,000 bytes. |
| `mcp.toml` | Named MCP declarations, merged over `home/.chezmoidata/mcp.toml`. |
| `skills.toml` | Named Pack declarations, merged over `home/.chezmoidata/packs.toml`. |
| `mise.toml` | A mise config linked as `~/.config/mise/conf.d/90-site.toml` while present. Remove the old link manually if you retire this file. |
| `ignore` | Target paths or patterns in chezmoiignore syntax, one per line. Own ignored targets locally. |

For example, a site Pack can declare selected names in `skills.toml` as follows.

```toml
[packs.extra]
repo = "https://example.invalid/skills.git"
skills = { example = true }
```

Select the personal Pack for `facebook-marketplace`. Re-run
`chezmoi init --prompt` to select a newly declared Pack. An overlapping entry
inherits upstream fields and the site value wins for each field it supplies.
Use `false` to disable an inherited skill. Platform-owned and Harness-owned
skill names stay reserved.

Each MCP table accepts `command` and optional `args`, or `url`. Optional
`platforms` is an array of `"macos"` or `"omarchy"`. Optional `requires`
names one binary. For example, a Site kit can declare the following server.

```toml
[mcp.example]
url = "https://example.invalid/mcp"
platforms = ["macos"]
secrets = ["EXAMPLE_TOKEN"]
```

Keep credentials out of URLs, commands, arguments and TOML. The `secrets` array
contains environment variable names only. A single name on HTTP maps to Codex's
bearer-token option. Other secret-bearing combinations are skipped and reported.
A Platform mismatch or absent prerequisite keeps an entry from installing.
Remove retired entries manually with their Harness CLI. Use `-s user` for Claude.
Site additions can extend these paths and keys. A replacement keeps the previous
interface working with a `fleet-check` deprecation notice for at least 30 days.

### Sync and checks

Run `fleet-check` to see the Git state of the source and current repo, the last
sync, local edits, missing and ad-hoc entries, overlapping declarations,
duplicate commands and T3 links. `--brief` prints only findings.
It fetches remote-tracking refs with a short timeout. Antigravity's hook reads
`workspacePaths` from stdin and requests `--format agy`. T3 Antigravity keeps
its own hooks. A small archive in `references/t3-mcp-link.tar.gz` holds one
relative symlink. Chezmoi can deploy that archive member at each computed profile
path and detect a replaced link in its normal status output. Verify rules, one selected skill and Playwright in a fresh direct
and T3 session for each Harness after cutover.

Use `chezmoi apply` to try uncommitted source edits on the current branch.
`fleet-sync` checks the checkout and deployed edits, pulls with `--ff-only`,
applies with `--no-tty --error-on-conflict`, then runs `skills update -g -y`,
including ad-hoc global skills. A stopped sync sends a desktop notification.
See `~/.local/state/fleet/last-sync` (or the corresponding XDG state directory),
resolve the reported condition, then run `fleet-sync` again.

After rehearsal and cutover, enable the four-hour timer on Omarchy with
`systemctl --user daemon-reload` and `systemctl --user enable --now fleet-sync.timer`.
On macOS, load the agent with
`launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/org.dotfiles.fleet-sync.plist"`.
Both schedulers include mise's shims. Upgrade binaries separately with
`omarchy update` on Omarchy and `mise up` and `brew upgrade` on macOS.

`make test-chezmoi` runs the agentic smoke test using disposable homes, a local
upstream, a fixture Pack and Site kit, and stub installers and Harness CLIs.
It needs Python 3.11+, Git and either chezmoi or mise. The mise fallback
downloads chezmoi into a temporary home.
