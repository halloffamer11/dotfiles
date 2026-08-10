# ~/dotfiles/Makefile — machine provisioning entry points.
#
# Usage:
#   make bootstrap   # fresh machine: brew packages + config symlinks + agent skills + externals
#   make brew        # install/verify Brewfile packages only
#   make configs     # restow home-target config packages (what `dots` does, minus git pull)
#   make skills      # restow authored skills into each harness dir + brew-provided skill links
#   make externals   # (re)install externally-managed skills via the skills CLI
#   make update      # upgrade brew packages and externally-managed skills
#
# Editing:
#   - CONFIG_PACKAGES: config packages under stow/, targeted at ~
#   - HARNESS_SKILL_DIRS: which harnesses receive authored skills; add ~/.kiro/skills at work
#   - Recipes must be indented with a literal TAB (make syntax rule)
#   - Idempotency lives in the tools: `brew bundle` no-ops when satisfied; `stow -R` re-syncs
-include local.mk

CONFIG_PACKAGES ?= git herdr nvim starship wezterm yazi zsh hammerspoon
HARNESS_SKILL_DIRS ?= $(HOME)/.claude/skills $(HOME)/.agents/skills $(HOME)/.kiro/skills
EXTRA_BREWFILES ?= 

.PHONY: bootstrap brew configs skills externals update

bootstrap: brew configs skills externals

brew:
	brew bundle --file=$(CURDIR)/Brewfile
	@for f in $(EXTRA_BREWFILES); do brew bundle --file=$$f; done

configs:
	stow -d $(CURDIR)/stow -t $(HOME) -R $(CONFIG_PACKAGES)

skills:
	for t in $(HARNESS_SKILL_DIRS); do mkdir -p $$t && stow -d $(CURDIR)/agents -t $$t -R skills; done
	ln -sfn "$$(brew --prefix hunk)/libexec/skills/hunk-review" $(HOME)/.claude/skills/hunk-review

externals:
	npx -y skills add kunchenguid/lavish-axi -g -y
	npx -y skills add herdrdev/herdr --skill herdr -g -y
	npx -y skills add blader/humanizer -g -y

update:
	brew bundle --file=$(CURDIR)/Brewfile
	npx -y skills update -g -y
	@for f in $(EXTRA_BREWFILES); do brew bundle --file=$$f; done

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
