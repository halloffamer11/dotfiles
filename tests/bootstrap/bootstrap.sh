#!/bin/sh
# Tickets 03 and 04: one bootstrap command per platform. Every external tool
# (brew, npx, git clone, swift) is a stub, so this runs offline and only ever
# writes inside throwaway homes.
. "$(dirname "$0")/lib.sh"

stubs=$(mktemp -d)
bin=$(mktemp -d)   # a PATH holding only the real tools a check names
for c in sh env cat mkdir ln rm readlink find grep sed printf echo dirname basename sort \
         mktemp make stow perl test tr install cp touch head uname; do
  p=$(command -v $c) && ln -s "$p" "$bin/$c"
done
cat > "$stubs/npx" <<'STUB'
#!/bin/sh
echo "npx $*" >> "$HOME/calls.log"
STUB
cat > "$stubs/node" <<'STUB'
#!/bin/sh
STUB
cp "$stubs/node" "$stubs/npm"
cat > "$stubs/brew" <<'STUB'
#!/bin/sh
echo "brew $*" >> "$HOME/calls.log"
[ "$1" = --prefix ] && { echo /nonexistent; exit 0; }
exit 0
STUB
cat > "$stubs/git" <<'STUB'
#!/bin/sh
echo "git $*" >> "$HOME/calls.log"
[ "$1" = clone ] && { eval dest=\${$#}; mkdir -p "$dest/.git"; }
exit 0
STUB
cat > "$stubs/swift" <<'STUB'
#!/bin/sh
echo "swift $*" >> "$HOME/calls.log"
mkdir -p .build/release && : > .build/release/audiotee
STUB
cat > "$stubs/swiftc" <<'STUB'
#!/bin/sh
echo "swiftc $*" >> "$HOME/calls.log"
while [ $# -gt 0 ]; do [ "$1" = -o ] && : > "$2"; shift; done
STUB
chmod +x "$stubs"/*

# A stand-in delegate checkout whose installer only records that it ran.
fake_delegate() {
  mkdir -p "$1/delegate/.git"
  printf 'install:\n\t@echo delegate-install >> $(HOME)/calls.log\n' > "$1/delegate/Makefile"
}

boot() {  # boot HOME PROFILE PATH
  fake_delegate "$1"
  HOME="$1" PATH="$3" make -s -C "$REPO" bootstrap PROFILE="$2" HOME="$1" DELEGATE_DIR="$1/delegate" 2>&1
}

# --- macOS ---------------------------------------------------------------
g=$(fresh_home); fake_delegate "$g"
graph=$(make -n -C "$REPO" bootstrap PROFILE=macos HOME="$g" DELEGATE_DIR="$g/delegate" 2>&1)
check "macos: the command graph runs brew bundle, both audio builds and the Hammerspoon link" \
  sh -c 'for p in "brew bundle" "swift build" "swiftc" "ln -sfn .*hammerspoon"; do printf "%s\n" "$1" | grep -q "$p" || exit 1; done' _ "$graph"
check "the Brewfile declares node, which brings npm" grep -q '^brew "node"' "$REPO/Brewfile"

h=$(fresh_home)
out=$(boot "$h" macos "$bin") && bad "macos without brew stops" "$out"
check "macos without Homebrew stops with the starting instruction" has "$out" "Homebrew is missing.*brew.sh"
check "macos without Homebrew changes nothing in the home" [ -z "$(find "$h" -mindepth 1 -not -path "$h/delegate*")" ]
rm -rf "$h"

h=$(fresh_home)
echo mine > "$h/.zshrc"
out=$(boot "$h" macos "$stubs:$bin") && bad "macos with a real ~/.zshrc stops" "$out"
check "a real ~/.zshrc stops bootstrap with recovery guidance" has "$out" "move it aside"
check "the real ~/.zshrc is untouched and nothing was linked" \
  test "$(cat "$h/.zshrc")" = mine -a ! -e "$h/.config" -a ! -e "$h/.claude"
rm -rf "$h"

h=$(fresh_home)
out=$(boot "$h" macos "$stubs:$bin") || bad "macos: bootstrap succeeds in an isolated home" "$out"
log=$(cat "$h/calls.log" 2>/dev/null)
check "macos: brew bundle, the skills CLI, both audio builds and delegate's installer ran" \
  sh -c 'for p in "brew bundle" "npx" "swift build" "swiftc" "delegate-install"; do printf "%s\n" "$1" | grep -q "$p" || exit 1; done' _ "$log"
check "macos: config, Hammerspoon and the audio binaries are in place" \
  test -L "$h/.zshrc" -a -L "$h/.hammerspoon" -a -f "$h/.local/bin/mictee" -a -f "$h/.local/bin/audiotee"
rm -rf "$h"

# --- Linux ---------------------------------------------------------------
for profile in omarchy linux; do
  graph=$(make -n -C "$REPO" bootstrap PROFILE=$profile HOME="$g" DELEGATE_DIR="$g/delegate" 2>&1)
  check "$profile: the command graph reaches delegate's installer" has "$graph" "delegate-install"
  check "$profile: no brew, cask, Swift build, Borders or Hammerspoon in the command graph" \
    sh -c '! printf "%s\n" "$1" | grep -q -e "brew bundle" -e "swift build" -e "swiftc" -e "ln -sfn .*hammerspoon" -e "^stow .* borders"' _ "$graph"

  h=$(fresh_home)
  out=$(boot "$h" $profile "$bin") && bad "$profile without npm stops" "$out"
  check "$profile: missing prerequisites are named, with no distro command" \
    sh -c 'printf "%s\n" "$1" | grep -q "missing: .*node npm" && ! printf "%s\n" "$1" | grep -q -e apt -e pacman -e dnf' _ "$out"
  check "$profile: a failed preflight changes nothing" [ -z "$(find "$h" -mindepth 1 -not -path "$h/delegate*")" ]
  rm -rf "$h"

  h=$(fresh_home)
  out=$(boot "$h" $profile "$stubs:$bin") || bad "$profile: bootstrap succeeds" "$out"
  check "$profile: skills, agents and delegate reconciled" \
    sh -c 'grep -q "npx" "$1/calls.log" && grep -q delegate-install "$1/calls.log" && [ -n "$(ls "$1/.claude/agents")" ]' _ "$h"
  check "$profile: the result says system packages stay the distribution's" has "$out" "bootstrap installs none"
  before=$(find "$h" -type l | sort)
  boot "$h" $profile "$stubs:$bin" >/dev/null 2>&1 || bad "$profile: rerun succeeds"
  check "$profile: a rerun leaves the same links" [ "$before" = "$(find "$h" -type l | sort)" ]
  rm -rf "$h"
done
check "omarchy: Hyprland config only on the omarchy profile" \
  sh -c 'make -s -C "$1" configs-plan PROFILE=omarchy HOME=/tmp | grep -c hypr >/dev/null && [ "$(make -s -C "$1" configs-plan PROFILE=linux HOME=/tmp | grep -c "LINK: .config/hypr")" = 0 ]' _ "$REPO"

rm -rf "$stubs" "$bin" "$g"
finish
