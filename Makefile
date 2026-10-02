# ~/dotfiles/Makefile — machine provisioning entry points.
#
# Usage:
#   make bootstrap   # fresh machine: brew packages + reconciled config/skills + audiotee/mictee builds + delegate
#   make brew        # install/verify Brewfile packages only
#   make apply       # reconcile configs, agent links, and declared skills
#   make configs     # restow home-target config packages only
#   make skills      # brew-provided skill links + per-file agent links
#   make externals   # ensure declared skills (personal and third-party) are installed at current upstream
#   make external-updates  # update only the skills declared by this repo
#   make delegate    # clone halloffamer11/delegate into DELEGATE_DIR if absent, then run its `make install`
#   make update      # verify Brewfile packages and update declared skills
#   make audiotee    # build the audiotee system-audio capture binary into ~/.local/bin (Swift 5.9+, macOS 14.2+)
#   make mictee      # build the mictee mic capture binary into ~/.local/bin (Swift)
#   make test-recorder  # regression harness for the record-meeting rig
#
# Editing:
#   - CONFIG_PACKAGES: config packages under stow/, targeted at ~
#   - hammerspoon is NOT in CONFIG_PACKAGES: .stowrc sets --no-folding, but Hammerspoon
#     needs ~/.hammerspoon to be ONE whole-directory symlink (per-file links break
#     hs.configdir and the pathwatcher auto-reload — upstream issue #830), so `configs`
#     links it explicitly instead of stowing it
#   - This repo holds no authored skills. PERSONAL_SKILLS come from halloffamer11/skills
#     through the skills CLI, like the third-party ones; delegate has its own repo and
#     installer (DELEGATE_DIR), because it needs machine setup the skills CLI cannot do.
#   - SKILL_AGENTS: which harnesses the skills CLI installs into
#   - agents are stowed per FILE into ~/.claude/agents (the package is flat, so folding is moot) so
#     machine-local agents can sit alongside; an agent added by a pull appears after the next `make skills`
#   - Recipes must be indented with a literal TAB (make syntax rule)
#   - Idempotency lives in the tools: `brew bundle` no-ops when satisfied; `stow -R` re-syncs
-include local.mk

CONFIG_PACKAGES ?= borders claude ghostty git herdr nvim starship wezterm yazi zsh
SKILL_AGENTS ?= claude-code codex kiro-cli
PERSONAL_SKILLS ?= facebook-marketplace fresh-context toolsmith
DELEGATE_DIR ?= $(HOME)/projects/delegate
EXTRA_BREWFILES ?=
SKILLS_CLI = DISABLE_TELEMETRY=1 npx -y skills@latest

.PHONY: bootstrap brew apply configs skills externals external-updates update delegate audiotee mictee test-recorder

bootstrap: brew apply audiotee mictee delegate

brew:
	brew bundle --file=$(CURDIR)/Brewfile
	@for f in $(EXTRA_BREWFILES); do brew bundle --file=$$f; done

apply: configs skills externals

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
	ln -sfn "$$(brew --prefix hunk)/libexec/skills/hunk-review" $(HOME)/.claude/skills/hunk-review
	@[ -L $(HOME)/.claude/agents ] && rm $(HOME)/.claude/agents || true
	mkdir -p $(HOME)/.claude/agents && (cd $(CURDIR)/agents && stow -t $(HOME)/.claude/agents -R agents)

externals:
	@# These declarations are desired state: add installs a missing skill and refreshes an existing one.
	$(SKILLS_CLI) add halloffamer11/skills --skill $(PERSONAL_SKILLS) --agent $(SKILL_AGENTS) -g -y
	$(SKILLS_CLI) add herdrdev/herdr --skill herdr --agent $(SKILL_AGENTS) -g -y
	$(SKILLS_CLI) add blader/humanizer --skill humanizer --agent $(SKILL_AGENTS) -g -y

external-updates:
	$(SKILLS_CLI) update -g -y herdr humanizer $(PERSONAL_SKILLS)

update: brew external-updates

delegate:
	@[ -d $(DELEGATE_DIR)/.git ] || git clone https://github.com/halloffamer11/delegate.git $(DELEGATE_DIR)
	$(MAKE) -C $(DELEGATE_DIR) install

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
