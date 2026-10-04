#!/bin/sh
# Ticket 02: each profile links the shared configuration plus only its own,
# a dry run reports conflicts without touching them, and a rerun is a no-op.
. "$(dirname "$0")/lib.sh"

links_into_repo() {  # every managed link under $1 resolves into the repo
  find "$1" -type l | while read -r l; do
    case "$(readlink -f "$l")" in "$REPO"/*) ;; *) echo "$l"; esac
  done
}

for profile in macos omarchy linux; do
  h=$(fresh_home)
  plan=$(make -s -C "$REPO" configs-plan PROFILE=$profile HOME="$h" 2>&1)
  check "$profile: the plan names its profile" has "$plan" "^profile: $profile"
  check "$profile: a dry run writes nothing" [ -z "$(find "$h" -mindepth 1)" ]

  out=$(make -s -C "$REPO" configs PROFILE=$profile HOME="$h" 2>&1) || bad "$profile: configs runs" "$out"
  check "$profile: shared config is linked (nvim, git, starship, CLAUDE.md)" \
    test -L "$h/.config/nvim/init.lua" -a -L "$h/.gitconfig" -a -L "$h/.config/starship.toml" -a -L "$h/.claude/CLAUDE.md"
  check "$profile: every link points into the repo" [ -z "$(links_into_repo "$h")" ]
  case $profile in
    macos)
      check "macos: Borders, zsh and a whole-directory Hammerspoon link" \
        test -L "$h/.config/borders/bordersrc" -a -L "$h/.zshrc" -a -L "$h/.hammerspoon"
      check "macos: no Omarchy config" test ! -e "$h/.config/hypr" -a ! -e "$h/.bashrc" ;;
    omarchy)
      check "omarchy: Bash, Ghostty, Herdr, Hyprland and Voxtype" \
        test -L "$h/.bashrc" -a -L "$h/.config/ghostty/config" -a -L "$h/.config/herdr/config.toml" \
             -a -L "$h/.config/hypr/bindings.lua" -a -L "$h/.config/voxtype/config.toml"
      check "omarchy: no macOS artifact" \
        test ! -e "$h/.hammerspoon" -a ! -e "$h/.config/borders" -a ! -e "$h/.config/wezterm" ;;
    linux)
      check "linux: only the portable layer" \
        test ! -e "$h/.hammerspoon" -a ! -e "$h/.config/borders" -a ! -e "$h/.config/hypr" -a ! -e "$h/.bashrc" -a ! -e "$h/.zshrc"
      check "linux: the packages left out are named" has "$out" "^not selected for linux: .*hypr" ;;
  esac
  before=$(find "$h" | sort | xargs -I{} sh -c 'printf "%s %s\n" "{}" "$(readlink "{}")"')
  make -s -C "$REPO" configs PROFILE=$profile HOME="$h" >/dev/null 2>&1 || bad "$profile: rerun"
  after=$(find "$h" | sort | xargs -I{} sh -c 'printf "%s %s\n" "{}" "$(readlink "{}")"')
  check "$profile: a rerun changes nothing" [ "$before" = "$after" ]
  rm -rf "$h"
done

# Conflicts: a real file where a link would go is reported, never replaced.
h=$(fresh_home)
mkdir -p "$h/.claude" "$h/.hammerspoon"
echo mine > "$h/.zshrc"; echo mine > "$h/.claude/CLAUDE.md"
plan=$(make -s -C "$REPO" configs-plan PROFILE=macos HOME="$h" 2>&1)
check "a dry run reports a real ~/.zshrc as a conflict" has "$plan" "existing target.*\.zshrc"
check "a dry run reports a real ~/.hammerspoon" has "$plan" "CONFLICT: ~/.hammerspoon"
check "a dry run reports a real ~/.claude/CLAUDE.md" has "$plan" "CONFLICT: ~/.claude/CLAUDE.md"
check "the conflicting files are untouched" \
  test "$(cat "$h/.zshrc")" = mine -a "$(cat "$h/.claude/CLAUDE.md")" = mine -a ! -L "$h/.hammerspoon"
rm -rf "$h"

check "PROFILE outside the three is refused" sh -c '! make -s -C "$1" configs-plan PROFILE=windows HOME=/nonexistent >/dev/null 2>&1' _ "$REPO"
finish
