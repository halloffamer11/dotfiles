#!/bin/sh
# Ticket 05: the maintenance vocabulary on every profile. `doctor` diagnoses
# without writing, `update` leaves Linux packages alone, and `dots` pulls before
# it reconciles. Every run here uses a throwaway HOME.
. "$(dirname "$0")/lib.sh"

# What these targets would write in a live home: the managed links and the
# skill dirs. Their targets, not the directories' mtimes, which a running
# Claude or editor session changes on its own.
live_state() {
  for p in .zshrc .bashrc .gitconfig .hammerspoon .claude/CLAUDE.md .claude/statusline.sh \
           .config/nvim .config/starship.toml .config/git/ignore; do
    printf '%s %s\n' "$p" "$(readlink "$HOME/$p" 2>/dev/null || { [ -e "$HOME/$p" ] && echo real || echo absent; })"
  done
  ls "$HOME/.claude/agents" "$HOME/.claude/skills" "$HOME/.agents/skills" 2>/dev/null
}
live_before=$(live_state)

# doctor asks each checkout's remote whether it is behind. Off here, so a run
# needs no network; the behind check below uses a local remote instead.
export DOCTOR_UPSTREAM=
# Stand-ins for the deployment pieces doctor looks at: gitleaks on PATH and a
# delegate checkout whose relay check passes.
stub=$(mktemp -d "${TMPDIR:-/tmp}/dotfiles-stub.XXXXXX")
printf '#!/bin/sh\nexit 0\n' > "$stub/gitleaks"; chmod +x "$stub/gitleaks"
fake_delegate() {  # fake_delegate HOME: a checkout at the default DELEGATE_DIR
  d="$1/projects/delegate"; mkdir -p "$d/agents/skills/delegate/scripts"
  git init -q "$d"
  printf '#!/bin/sh\necho "ads: stub at abc1234"\n' > "$d/agents/skills/delegate/scripts/ads.sh"
  mkdir -p "$1/.config/delegate"; echo '{}' > "$1/.config/delegate/lanes.json"
}

for profile in macos omarchy linux; do
  h=$(fresh_home)
  out=$(make -s -C "$REPO" doctor PROFILE=$profile HOME="$h" 2>&1); rc=$?
  check "$profile: doctor on a fresh home asks for action and exits non-zero" \
    sh -c '[ "$1" -ne 0 ] && printf "%s\n" "$2" | grep -q "ACTION: .*not in place yet"' _ "$rc" "$out"
  check "$profile: doctor names its profile" has "$out" "^profile: $profile"
  check "$profile: doctor writes nothing" [ -z "$(find "$h" -mindepth 1)" ]

  check "$profile: doctor on a fresh home asks for delegate" has "$out" "ACTION: delegate is not checked out"

  make -s -C "$REPO" configs PROFILE=$profile HOME="$h" >/dev/null 2>&1
  for s in herdr humanizer facebook-marketplace fresh-context toolsmith; do mkdir -p "$h/.agents/skills/$s"; done
  fake_delegate "$h"
  out=$(PATH="$stub:$PATH" make -s -C "$REPO" doctor PROFILE=$profile HOME="$h" 2>&1); rc=$?
  # a missing prerequisite (no brew in this container) is the one thing allowed to remain
  rest=$(printf '%s\n' "$out" | grep ACTION | grep -v "missing prerequisites")
  check "$profile: after configs, skills and delegate, doctor finds nothing else to do" [ -z "$rest" ] || printf '%s\n' "$out"

  ln -s "$REPO/stow/gone" "$h/.config/gone"
  out=$(make -s -C "$REPO" doctor PROFILE=$profile HOME="$h" 2>&1)
  check "$profile: a broken link into the repo is reported" has "$out" "  $h/.config/gone"
  rm -rf "$h/.agents/skills/humanizer"
  out=$(make -s -C "$REPO" doctor PROFILE=$profile HOME="$h" 2>&1)
  check "$profile: a declared skill that is gone is reported" has "$out" "not installed: humanizer"
  rm -rf "$h"

  graph=$(make -n -C "$REPO" update PROFILE=$profile HOME=/nonexistent 2>&1)
  if [ $profile = macos ]; then
    check "macos: update reconciles Homebrew and the declared skills" \
      sh -c 'printf "%s\n" "$1" | grep -q "brew bundle" && printf "%s\n" "$1" | grep -q "skills@latest update"' _ "$graph"
  else
    check "$profile: update leaves system packages alone and updates the skills" \
      sh -c '! printf "%s\n" "$1" | grep -q "brew" && printf "%s\n" "$1" | grep -q "skills@latest update"' _ "$graph"
  fi
done

h=$(fresh_home); fake_delegate "$h"
printf '#!/bin/sh\necho "ads: commit mismatch; run ads.sh install" >&2; exit 1\n' > "$h/projects/delegate/agents/skills/delegate/scripts/ads.sh"
rm "$h/.config/delegate/lanes.json"
out=$(PATH="$stub:$PATH" make -s -C "$REPO" doctor PROFILE=linux HOME="$h" 2>&1)
check "doctor reports delegate relays that need ads.sh install" has "$out" "ACTION: delegate relays: commit mismatch.*ads.sh install"
check "doctor reports a machine with no delegate catalog" has "$out" "ACTION: no delegate catalog.*delegate-wizard"
out=$(PATH=/usr/bin:/bin make -s -C "$REPO" doctor PROFILE=linux HOME="$h" 2>&1)
if ! PATH=/usr/bin:/bin command -v gitleaks >/dev/null 2>&1; then
  check "doctor reports a machine without gitleaks" has "$out" "ACTION: gitleaks is missing"
fi
rm -rf "$h"

# Behind: the delegate checkout lacks a commit its upstream main has.
h=$(fresh_home); fake_delegate "$h"; d="$h/projects/delegate"
git -C "$d" -c user.email=t@t -c user.name=t commit -q --allow-empty -m one
git init -q --bare "$h/upstream.git"; git -C "$d" remote add origin "$h/upstream.git"
git -C "$d" push -q origin HEAD:refs/heads/main 2>/dev/null
out=$(DOCTOR_UPSTREAM=delegate PATH="$stub:$PATH" make -s -C "$REPO" doctor PROFILE=linux HOME="$h" 2>&1)
check "doctor says a current delegate checkout has upstream main" has "$out" "^delegate: has upstream main"
git clone -q -b main "$h/upstream.git" "$h/other" 2>/dev/null
git -C "$h/other" -c user.email=t@t -c user.name=t commit -q --allow-empty -m two
git -C "$h/other" push -q origin HEAD:refs/heads/main 2>/dev/null
out=$(DOCTOR_UPSTREAM=delegate PATH="$stub:$PATH" make -s -C "$REPO" doctor PROFILE=linux HOME="$h" 2>&1)
check "doctor reports a delegate checkout behind upstream main" has "$out" "ACTION: delegate is behind upstream main: git -C $d pull"
rm -rf "$h"

h=$(fresh_home); mkdir -p "$h/.claude"; echo mine > "$h/.claude/CLAUDE.md"
out=$(make -s -C "$REPO" doctor PROFILE=linux HOME="$h" 2>&1)
check "doctor reports a file in the way of a managed link" has "$out" "CONFLICT: ~/.claude/CLAUDE.md"
rm -rf "$h"

for rc in "$REPO/stow/zsh/.zshrc" "$REPO/stow/bash/.bashrc"; do
  check "dots pulls, then reconciles, in $(basename "$rc")" \
    grep -q "^alias dots='git -C ~/dotfiles pull --rebase && make -C ~/dotfiles apply" "$rc"
done
check "make apply refreshes the external skills (externals is in apply)" \
  grep -q "^apply: .*externals" "$REPO/Makefile"
check "the operator guide covers all three profiles" \
  sh -c 'for w in "## macOS" "## Omarchy" "## Generic Linux" "## Maintenance"; do grep -q "$w" "$1" || exit 1; done' _ "$REPO/docs/bootstrap.md"
check "a machine's ~/.gitconfig.local comes last, so its identity wins" \
  sh -c 'tail -n 2 "$1" | grep -q "path = ~/.gitconfig.local"' _ "$REPO/stow/git/.gitconfig"
rm -rf "$stub"
check "the runner's live home is untouched" \
  [ "$live_before" = "$(live_state)" ]
finish
