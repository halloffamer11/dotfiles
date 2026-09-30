# ~/dotfiles/Makefile — machine provisioning entry points.
#
# Usage:
#   make bootstrap   # fresh machine: brew packages + herdr + reconciled config/skills + audiotee/mictee builds
#   make brew        # install/verify Brewfile packages only
#   make herdr       # install herdr with its own installer into ~/.local/bin; stops if another package manager owns one
#   make apply       # reconcile configs, authored skills, and declared external skills
#   make configs     # restow home-target config packages only
#   make skills      # restow authored skills into each harness dir + brew-provided skill links + per-file agent links
#   make externals   # ensure declared external skills are installed at current upstream
#   make external-updates  # update only the external skills declared by this repo
#   make delegate-codex-home  # delegate's own CODEX_HOME: the disposable browser and nothing else
#   make update      # verify Brewfile packages, run `herdr update`, and update declared external skills
#   make audiotee    # build the audiotee system-audio capture binary into ~/.local/bin (Swift 5.9+, macOS 14.2+)
#   make mictee      # build the mictee mic capture binary into ~/.local/bin (Swift)
#   make test-recorder  # regression harness for the record-meeting rig
#   make delegate-wizard  # the delegate catalog wizard on this machine's catalog with the accepted benchmark rows; WIZARD_ARGS adds flags (e.g. --tiers-from FILE, --plain)
#   make delegate-dashboard  # link and open the local dashboard; DELEGATE_DASHBOARD_PLACEMENT overrides split
#
# The two short forms, once `make configs` has linked stow/delegate/.local/bin/delegate
# into ~/.local/bin (ticket 34). Neither needs a checkout path:
#   delegate global [args]   # this target, with the args as WIZARD_ARGS
#   delegate project [args]  # the dashboard for the current directory's Git project
#
# Editing:
#   - CONFIG_PACKAGES: config packages under stow/, targeted at ~
#   - delegate ships only the `delegate` command. ~/.config/delegate/{lanes,routing}.json
#     and the lane-*.md agents in ~/.claude/agents are machine-local and never in the
#     repo: each machine keeps its own preferences, and a fresh one gets a starting
#     catalog from `make delegate-wizard`
#   - hammerspoon is NOT in CONFIG_PACKAGES: .stowrc sets --no-folding, but Hammerspoon
#     needs ~/.hammerspoon to be ONE whole-directory symlink (per-file links break
#     hs.configdir and the pathwatcher auto-reload — upstream issue #830), so `configs`
#     links it explicitly instead of stowing it
#   - HARNESS_SKILL_DIRS: which harnesses receive authored skills; add ~/.kiro/skills at work
#   - `skills` runs stow from agents/ (not repo root) so .stowrc's --no-folding is not read:
#     each skill stays ONE whole-directory symlink, so files added later appear without a restow.
#     Codex reads ~/.agents/skills (follows dir symlinks); ~/.codex/skills is deprecated upstream.
#   - agents are stowed per FILE into ~/.claude/agents (the package is flat, so folding is moot) so
#     machine-local agents can sit alongside; an agent added by a pull appears after the next `make skills`
#   - Recipes must be indented with a literal TAB (make syntax rule)
#   - Idempotency lives in the tools: `brew bundle` no-ops when satisfied; `stow -R` re-syncs
-include local.mk

CONFIG_PACKAGES ?= borders claude delegate ghostty git herdr nvim starship wezterm yazi zsh
HARNESS_SKILL_DIRS ?= $(HOME)/.claude/skills $(HOME)/.agents/skills $(HOME)/.kiro/skills
EXTRA_BREWFILES ?=
# The upstream installer's own variable and default; `make herdr` passes it through.
HERDR_INSTALL_DIR ?= $(HOME)/.local/bin
# Accepted benchmark rows the wizard reads (repo-relative). The pre-screen and the
# benchmark page use AA and Terminal-Bench; swerb rows are evidence only.
DELEGATE_ROWS ?= .scratch/delegate-redesign/_data/aa-accepted.json .scratch/delegate-redesign/_data/tbench-accepted.json
DELEGATE_DASHBOARD_PLACEMENT ?= split

.PHONY: bootstrap brew herdr herdr-update apply configs skills externals external-updates update audiotee mictee test-recorder delegate-wizard delegate-codex-home delegate-dashboard

bootstrap: brew herdr apply audiotee mictee delegate-codex-home

brew:
	brew bundle --file=$(CURDIR)/Brewfile
	@for f in $(EXTRA_BREWFILES); do brew bundle --file=$$f; done

# One owner per machine: the server and every client must be the same build. The guard
# changes nothing and stops while a Homebrew login service or another herdr on PATH
# (Homebrew, mise, a distribution package) could start a different build of the server.
# The installer is downloaded to a file first, so a failed download fails the target.
herdr:
	@if [ -e "$(HOME)/Library/LaunchAgents/homebrew.mxcl.herdr.plist" ]; then \
		echo "ERROR: the Homebrew login service homebrew.mxcl.herdr starts its own herdr server. From a terminal outside Herdr:"; \
		echo "  herdr server stop; launchctl bootout gui/$$(id -u)/homebrew.mxcl.herdr; rm ~/Library/LaunchAgents/homebrew.mxcl.herdr.plist"; \
		exit 1; fi
	@IFS=:; for d in $$PATH; do \
		if [ -x "$$d/herdr" ] && [ "$$d/herdr" != "$(HERDR_INSTALL_DIR)/herdr" ]; then \
			echo "ERROR: $$d/herdr has another owner. Remove it with that package manager, then run make herdr again."; \
			exit 1; fi; \
	done
	@if [ ! -x "$(HERDR_INSTALL_DIR)/herdr" ]; then \
		tmp="$$(mktemp)" && curl -fsSL https://herdr.dev/install.sh -o "$$tmp" && HERDR_INSTALL_DIR="$(HERDR_INSTALL_DIR)" sh "$$tmp"; \
		rc=$$?; rm -f "$$tmp"; exit $$rc; fi

# `herdr update` replaces the binary in place. The running server keeps its old build
# until Herdr is quit and started again; `herdr status` then shows server_binary_stale: no.
herdr-update: herdr
	"$(HERDR_INSTALL_DIR)/herdr" update

apply: configs skills externals

delegate-codex-home:
	mkdir -p $(HOME)/.local/share/delegate/codex-home $(HOME)/.cache/playwright-mcp
	sed 's|@HOME@|$(HOME)|g' $(CURDIR)/agents/skills/delegate/assets/codex-home/config.toml > $(HOME)/.local/share/delegate/codex-home/config.toml
	@if [ -f $(HOME)/.codex/auth.json ]; then \
		ln -sfn $(HOME)/.codex/auth.json $(HOME)/.local/share/delegate/codex-home/auth.json; \
	else \
		echo "NOTE: ~/.codex/auth.json is absent — run 'codex login', then 'make delegate-codex-home' again"; \
	fi

configs:
	stow -d $(CURDIR)/stow -t $(HOME) -R $(CONFIG_PACKAGES)
	@if [ -d $(HOME)/.hammerspoon ] && [ ! -L $(HOME)/.hammerspoon ]; then \
		echo "ERROR: ~/.hammerspoon is a real directory (Hammerspoon launched before configs?) — move it aside first"; exit 1; fi
	ln -sfn $(CURDIR)/stow/hammerspoon/.hammerspoon $(HOME)/.hammerspoon
	@# stow -R unlinks before relinking; a Hyprland reload landing in that
	@# window raises a persistent "config has errors" overlay that outlives
	@# the restow. Reloading here clears it. No-op without hyprctl (macOS).
	@if command -v hyprctl >/dev/null 2>&1; then hyprctl reload >/dev/null; fi

skills:
	for t in $(HARNESS_SKILL_DIRS); do mkdir -p $$t && (cd $(CURDIR)/agents && stow -t $$t -R skills); done
	ln -sfn "$$(brew --prefix hunk)/libexec/skills/hunk-review" $(HOME)/.claude/skills/hunk-review
	@[ -L $(HOME)/.claude/agents ] && rm $(HOME)/.claude/agents || true
	mkdir -p $(HOME)/.claude/agents && (cd $(CURDIR)/agents && stow -t $(HOME)/.claude/agents -R agents)

externals:
	@# These declarations are desired state: add installs a missing skill and refreshes an existing one.
	DISABLE_TELEMETRY=1 npx -y skills@latest add herdrdev/herdr --skill herdr --agent claude-code codex kiro-cli -g -y
	DISABLE_TELEMETRY=1 npx -y skills@latest add blader/humanizer --skill humanizer --agent claude-code codex kiro-cli -g -y

external-updates:
	DISABLE_TELEMETRY=1 npx -y skills@latest update -g -y herdr humanizer

update: brew herdr-update external-updates

audiotee:
	rm -rf /tmp/audiotee-build
	git clone --depth 1 https://github.com/makeusabrew/audiotee.git /tmp/audiotee-build
	cd /tmp/audiotee-build && swift build -c release
	mkdir -p $(HOME)/.local/bin
	install /tmp/audiotee-build/.build/release/audiotee $(HOME)/.local/bin/audiotee

mictee:
	mkdir -p $(HOME)/.local/bin
	swiftc -O -o $(HOME)/.local/bin/mictee $(CURDIR)/tools/mictee/mictee.swift

test-recorder:
	python3 $(CURDIR)/tools/record-meeting-tests/harness.py

# Writes this machine's catalog, ~/.config/delegate, and the agent file of each new
# native claude lane straight into ~/.claude/agents, so a new lane is live with no
# second command (ticket 33). Neither is in the repo.
delegate-wizard:
	python3 $(CURDIR)/agents/skills/delegate/scripts/setup.py $(foreach f,$(DELEGATE_ROWS),--effort-rows $(CURDIR)/$(f)) $(WIZARD_ARGS)

delegate-dashboard:
	@test "$${HERDR_ENV:-}" = 1
	@test -n "$${HERDR_PANE_ID:-}"
	@"$${HERDR_BIN_PATH:-herdr}" plugin link "$(CURDIR)/tools/delegate-dashboard"
	@python3 "$(CURDIR)/tools/delegate-dashboard/open.py" --placement "$(DELEGATE_DASHBOARD_PLACEMENT)" --target-pane "$${HERDR_PANE_ID}"

#   references/  — reference material pulled with the repo but not provisioned by brew/stow/skills (e.g. personal CLAUDE.md for the work Mac to cherry-pick from)
