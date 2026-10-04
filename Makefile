# ~/dotfiles/Makefile — machine provisioning entry points.
#
# Usage:
#   make bootstrap   # fresh machine. macOS: brew packages + config/skills + audiotee/mictee + delegate.
#                    # Linux (omarchy, linux): config/skills + delegate; system packages stay the distro's.
#   make brew        # install/verify Brewfile packages only
#   make apply       # reconcile configs, agent links, declared skills, and the delegate install
#   make configs     # restow the profile's config packages and link ~/.claude/CLAUDE.md
#   make configs-plan  # dry run of configs: the profile, its links and any conflicts; writes nothing
#   make test-bootstrap  # isolated-home checks of configs and skills (needs stow and make)
#   make skills      # drop stale authored-skill links + brew-provided skill links + per-file agent links
#   make externals   # ensure declared skills (personal and third-party) are installed at current upstream
#   make external-updates  # update only the skills declared by this repo
#   make delegate    # clone halloffamer11/delegate into DELEGATE_DIR if absent, then run its `make install`
#   make update      # verify Brewfile packages and update declared skills
#   make audiotee    # build the audiotee system-audio capture binary into ~/.local/bin (Swift 5.9+, macOS 14.2+)
#   make mictee      # build the mictee mic capture binary into ~/.local/bin (Swift)
#   make test-recorder  # regression harness for the record-meeting rig
#
# Editing:
#   - PROFILE: macos, omarchy or linux, detected (Darwin; Omarchy's /usr/share/omarchy or
#     ~/.local/share/omarchy; any other Linux). Override with `make PROFILE=linux ...` or a
#     PROFILE line in local.mk.
#   - CONFIG_PACKAGES: config packages under stow/, targeted at ~. Each profile is
#     COMMON_PACKAGES plus its own list; setting CONFIG_PACKAGES (local.mk) replaces the lot.
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

# The configuration every profile takes: nothing in it needs macOS or Omarchy.
COMMON_PACKAGES := claude git nvim starship yazi
MACOS_PACKAGES := borders ghostty herdr wezterm zsh
OMARCHY_PACKAGES := bash ghostty herdr hypr voxtype
LINUX_PACKAGES :=
ifeq ($(shell uname -s),Darwin)
DETECTED_PROFILE := macos
else ifneq ($(wildcard /usr/share/omarchy $(HOME)/.local/share/omarchy),)
DETECTED_PROFILE := omarchy
else
DETECTED_PROFILE := linux
endif
PROFILE ?= $(DETECTED_PROFILE)
ifeq ($(PROFILE),macos)
PROFILE_PACKAGES := $(MACOS_PACKAGES)
else ifeq ($(PROFILE),omarchy)
PROFILE_PACKAGES := $(OMARCHY_PACKAGES)
else ifeq ($(PROFILE),linux)
PROFILE_PACKAGES := $(LINUX_PACKAGES)
else
$(error PROFILE must be macos, omarchy or linux, not '$(PROFILE)')
endif
CONFIG_PACKAGES ?= $(sort $(COMMON_PACKAGES) $(PROFILE_PACKAGES))
# Packages under stow/ this profile leaves out, named so a skipped one is a choice, not a surprise.
UNSELECTED_PACKAGES = $(filter-out $(CONFIG_PACKAGES) hammerspoon,$(notdir $(wildcard $(CURDIR)/stow/*)))
SKILL_AGENTS ?= claude-code codex kiro-cli
PERSONAL_SKILLS ?= facebook-marketplace fresh-context toolsmith
DELEGATE_DIR ?= $(HOME)/projects/delegate
EXTRA_BREWFILES ?=
SKILLS_CLI = DISABLE_TELEMETRY=1 npx -y skills@latest

.PHONY: bootstrap preflight conflicts brew apply configs configs-plan skills externals external-updates update delegate audiotee mictee test-recorder test-bootstrap

# Prerequisites run left to right. Each profile first checks what it cannot do without, so
# a machine missing one stops before anything in the home directory changes; existing
# files in the way stop it next, with what to do, since stow never adopts or overwrites.
ifeq ($(PROFILE),macos)
bootstrap: preflight brew conflicts apply audiotee mictee
else
bootstrap: preflight conflicts apply
	@echo "note: Linux system packages (git, make, stow, node, npm, the tools the configs call) are the distribution's or yours; bootstrap installs none."
endif

LINUX_NEEDS := git make stow node npm
preflight:
ifeq ($(PROFILE),macos)
	@command -v brew >/dev/null 2>&1 || { echo "ERROR: Homebrew is missing. Install it from https://brew.sh (after xcode-select --install), then run make bootstrap again."; exit 1; }
else
	@missing=""; for c in $(LINUX_NEEDS); do command -v $$c >/dev/null 2>&1 || missing="$$missing $$c"; done; \
	if [ -n "$$missing" ]; then echo "ERROR: missing:$$missing. Install them with your distribution's package manager, then run make bootstrap again."; exit 1; fi
endif

conflicts:
	@# A plain `make`, not $(MAKE): `make -n bootstrap` then prints this check instead of running it.
	@plan="$$(MAKEFLAGS= make -s --no-print-directory -C $(CURDIR) configs-plan PROFILE=$(PROFILE) HOME=$(HOME) CONFIG_PACKAGES='$(CONFIG_PACKAGES)')"; \
	found="$$(printf '%s\n' "$$plan" | grep -E 'CONFLICT|existing target' || true)"; \
	if [ -n "$$found" ]; then printf '%s\n' "$$found"; \
		echo "ERROR: files already at these paths would be replaced. Compare each with the repo's copy, keep what you need, move it aside (mv FILE FILE.pre-dotfiles), then run make bootstrap again."; exit 1; fi

brew:
	brew bundle --file=$(CURDIR)/Brewfile
	@for f in $(EXTRA_BREWFILES); do brew bundle --file=$$f; done

apply: configs skills externals delegate

configs:
	@echo "profile: $(PROFILE)"
	stow -d $(CURDIR)/stow -t $(HOME) -R $(CONFIG_PACKAGES)
	@[ -z "$(strip $(UNSELECTED_PACKAGES))" ] || echo "not selected for $(PROFILE): $(strip $(UNSELECTED_PACKAGES))"
ifeq ($(PROFILE),macos)
	@if [ -d $(HOME)/.hammerspoon ] && [ ! -L $(HOME)/.hammerspoon ]; then \
		echo "ERROR: ~/.hammerspoon is a real directory (Hammerspoon launched before configs?) — move it aside first"; exit 1; fi
	ln -sfn $(CURDIR)/stow/hammerspoon/.hammerspoon $(HOME)/.hammerspoon
endif
	@# ~/.claude/CLAUDE.md is Orin's global steering file, kept in references/. A real
	@# file there is someone's data: stop rather than replace it.
	@if [ -e $(HOME)/.claude/CLAUDE.md ] && [ ! -L $(HOME)/.claude/CLAUDE.md ]; then \
		echo "ERROR: ~/.claude/CLAUDE.md is a real file — diff it against references/CLAUDE.md, then move it aside"; exit 1; fi
	mkdir -p $(HOME)/.claude && ln -sfn $(CURDIR)/references/CLAUDE.md $(HOME)/.claude/CLAUDE.md
	@# stow -R unlinks before relinking; a Hyprland reload landing in that
	@# window raises a persistent "config has errors" overlay that outlives
	@# the restow. Reloading here clears it. No-op without hyprctl (macOS).
	@if command -v hyprctl >/dev/null 2>&1; then hyprctl reload >/dev/null; fi

# What `configs` would do, without doing it: stow's simulation lists each link it would
# make and each existing file in the way, and the two hand-made links are checked the same way.
configs-plan:
	@echo "profile: $(PROFILE) (detected $(DETECTED_PROFILE))"
	@echo "packages: $(CONFIG_PACKAGES)"
	@[ -z "$(strip $(UNSELECTED_PACKAGES))" ] || echo "not selected: $(strip $(UNSELECTED_PACKAGES))"
	@stow -n -v -d $(CURDIR)/stow -t $(HOME) -R $(CONFIG_PACKAGES) 2>&1 | grep -v '^WARNING: in simulation mode' || true
ifeq ($(PROFILE),macos)
	@if [ -e $(HOME)/.hammerspoon ] && [ ! -L $(HOME)/.hammerspoon ]; then echo "CONFLICT: ~/.hammerspoon is a real directory"; \
		else echo "LINK: .hammerspoon => $(CURDIR)/stow/hammerspoon/.hammerspoon"; fi
endif
	@if [ -e $(HOME)/.claude/CLAUDE.md ] && [ ! -L $(HOME)/.claude/CLAUDE.md ]; then echo "CONFLICT: ~/.claude/CLAUDE.md is a real file"; \
		else echo "LINK: .claude/CLAUDE.md => $(CURDIR)/references/CLAUDE.md"; fi

skills:
	@# Before 2026-10-01 this repo stowed its own skills into the harness skill dirs. After a
	@# pull those links dangle, and the skills CLI or delegate's installer replaces them.
	@for t in $(HOME)/.claude/skills $(HOME)/.agents/skills $(HOME)/.kiro/skills; do for l in $$t/*; do \
		if [ -L "$$l" ] && [ ! -e "$$l" ]; then case "$$(readlink "$$l")" in */dotfiles/agents/skills/*) rm "$$l" && echo "removed stale link $$l";; esac; fi; \
	done; done
	@# hunk-review ships inside Homebrew's hunk; without both, it is skipped and the rest goes on.
	@hunk="$$(command -v brew >/dev/null 2>&1 && brew --prefix hunk 2>/dev/null)/libexec/skills/hunk-review"; \
	if [ -d "$$hunk" ]; then mkdir -p $(HOME)/.claude/skills && ln -sfn "$$hunk" $(HOME)/.claude/skills/hunk-review && echo "linked hunk-review"; \
	else echo "notice: Homebrew's hunk is not installed, so the optional hunk-review skill is skipped"; fi
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

test-bootstrap:
	@for t in $(CURDIR)/tests/bootstrap/*.sh; do sh "$$t" || exit 1; done

test-recorder:
	python3 $(CURDIR)/tools/record-meeting-tests/harness.py
