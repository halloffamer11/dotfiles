# ~/dotfiles/Makefile — machine provisioning entry points.
#
# Usage:
#   make bootstrap   # fresh machine: brew packages + reconciled config/skills + audiotee/mictee builds
#   make brew        # install/verify Brewfile packages only
#   make apply       # reconcile configs, authored skills, and declared external skills
#   make configs     # restow home-target config packages only
#   make skills      # restow authored skills into each harness dir + brew-provided skill links + per-file agent links
#   make externals   # ensure declared external skills are installed at current upstream
#   make external-updates  # update only the external skills declared by this repo
#   make delegate-codex-home  # delegate's own CODEX_HOME: the disposable browser and nothing else
#   make update      # verify Brewfile packages and update declared external skills
#   make audiotee    # build the audiotee system-audio capture binary into ~/.local/bin (Swift 5.9+, macOS 14.2+)
#   make mictee      # build the mictee mic capture binary into ~/.local/bin (Swift)
#   make test-recorder  # regression harness for the record-meeting rig
#   make delegate-wizard  # the delegate catalog wizard on the repo catalog with the accepted benchmark rows; WIZARD_ARGS adds flags (e.g. --tiers-from FILE, --plain)
#   make delegate-dashboard  # link and open the local dashboard; DELEGATE_DASHBOARD_PLACEMENT overrides split
#
# Editing:
#   - CONFIG_PACKAGES: config packages under stow/, targeted at ~
#   - delegate ships ~/.config/delegate/{lanes,routing}.json. One catalog serves every
#     machine: a lane whose harness CLI is not on PATH is vetoed at rank time
#     ("cli absent"), so the same file is correct on a box that lacks a CLI
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
# Accepted benchmark rows the wizard reads (repo-relative). The pre-screen and the
# benchmark page use AA and Terminal-Bench; swerb rows are evidence only.
DELEGATE_ROWS ?= .scratch/delegate-redesign/_data/aa-accepted.json .scratch/delegate-redesign/_data/tbench-accepted.json
DELEGATE_DASHBOARD_PLACEMENT ?= split

.PHONY: bootstrap brew apply configs skills externals external-updates update audiotee mictee test-recorder delegate-wizard delegate-codex-home delegate-dashboard

bootstrap: brew apply audiotee mictee delegate-codex-home

brew:
	brew bundle --file=$(CURDIR)/Brewfile
	@for f in $(EXTRA_BREWFILES); do brew bundle --file=$$f; done

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
	npx -y skills@latest add herdrdev/herdr --skill herdr --agent claude-code codex kiro-cli -g -y
	npx -y skills@latest add blader/humanizer --skill humanizer --agent claude-code codex kiro-cli -g -y

external-updates:
	npx -y skills@latest update -g -y herdr humanizer

update: brew external-updates

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

# Writes the repo catalog under stow/delegate, never ~/.config/delegate: setup.py
# renames over its target, which would turn a stowed symlink into a plain file.
# The wizard's refresh writes an agent file for each new native claude lane, so
# the per-file agent links are restowed after it exits — the `skills` step, and
# the reason a new lane is live with no second command (ticket 33).
delegate-wizard:
	python3 $(CURDIR)/agents/skills/delegate/scripts/setup.py --config-dir $(CURDIR)/stow/delegate/.config/delegate $(foreach f,$(DELEGATE_ROWS),--effort-rows $(CURDIR)/$(f)) $(WIZARD_ARGS)
	mkdir -p $(HOME)/.claude/agents && (cd $(CURDIR)/agents && stow -t $(HOME)/.claude/agents -R agents)

delegate-dashboard:
	@test "$${HERDR_ENV:-}" = 1
	@test -n "$${HERDR_PANE_ID:-}"
	@"$${HERDR_BIN_PATH:-herdr}" plugin link "$(CURDIR)/tools/delegate-dashboard"
	@python3 "$(CURDIR)/tools/delegate-dashboard/open.py" --placement "$(DELEGATE_DASHBOARD_PLACEMENT)" --target-pane "$${HERDR_PANE_ID}"

#   references/  — reference material pulled with the repo but not provisioned by brew/stow/skills (e.g. personal CLAUDE.md for the work Mac to cherry-pick from)
