#!/bin/sh
# Ticket 01: one operation (`make skills externals`) reconciles Claude agents and
# the declared skills on macOS and Linux. npx and brew are stubs here, so the
# check needs no network and proves what would be asked of the skills CLI.
. "$(dirname "$0")/lib.sh"

stubs=$(mktemp -d)
cat > "$stubs/npx" <<'STUB'
#!/bin/sh
echo "$*" >> "$STUB_LOG"
STUB
chmod +x "$stubs/npx"
BASE_PATH=$(printf '%s' "$PATH" | tr ':' '\n' | grep -v -e homebrew -e linuxbrew | paste -sd: -)
# Homebrew leaves the PATH, but its stow stays: on a Mac that is the only stow.
ln -s "$(command -v stow)" "$stubs/stow"

run() {  # run HOME PATH: make skills externals, output on stdout
  STUB_LOG="$1/npx.log" HOME="$1" PATH="$2" make -s -C "$REPO" skills externals HOME="$1" 2>&1
}

# No Homebrew at all: Linux, or a Mac before brew.
h=$(fresh_home)
out=$(run "$h" "$stubs:$BASE_PATH") || bad "without brew: skills and externals succeed" "$out"
agents=$(ls "$REPO/agents/agents" | wc -l)
linked=$(find "$h/.claude/agents" -type l | wc -l)
check "without brew: every Claude agent is linked, per file" [ "$agents" -eq "$linked" ]
check "without brew: hunk-review is skipped with a notice" has "$out" "notice: .*hunk-review skill is skipped"
check "without brew: no hunk-review link" test ! -e "$h/.claude/skills/hunk-review"
log=$(cat "$h/npx.log")
check "humanizer comes from its upstream, unpinned" \
  sh -c 'printf "%s\n" "$1" | grep -q -- "skills@latest add blader/humanizer --skill humanizer "' _ "$log"
check "the Herdr TUI skill is not installed" sh -c '! printf "%s\n" "$1" | grep -q herdrdev/herdr' _ "$log"
check "the core Pack supplies the Stow core skills" \
  has "$log" 'add halloffamer11/skills --skill council fresh-context skillsmith toolsmith --agent'
check "the personal Pack supplies Marketplace and google-access" \
  has "$log" 'add halloffamer11/skills-personal --skill facebook-marketplace google-access --agent'
check "all sources install into the three Harnesses" \
  [ "$(printf '%s\n' "$log" | grep -c -- '--agent claude-code codex antigravity-cli -g -y$')" -eq 3 ]
STUB_LOG="$h/updates.log" HOME="$h" PATH="$stubs:$BASE_PATH" \
  make -s -C "$REPO" external-updates >/dev/null || bad "refresh declared sources"
check "external-updates refreshes from the same declared sources" cmp "$h/npx.log" "$h/updates.log"
check "no skill version is pinned" sh -c '! printf "%s\n" "$1" | grep -q "@[0-9]"' _ "$log"

STUB_LOG="$h/legacy.log" HOME="$h" PATH="$stubs:$BASE_PATH" \
  make -s -C "$REPO" external-updates PERSONAL_SKILLS=toolsmith >/dev/null || bad "legacy subset"
legacy=$(cat "$h/legacy.log")
check "a former one-Pack override retains its core selection" has "$legacy" 'add halloffamer11/skills --skill toolsmith --agent'
check "an empty personal selection skips its installer" test "$(wc -l < "$h/legacy.log")" -eq 2

STUB_LOG="$h/personal.log" HOME="$h" PATH="$stubs:$BASE_PATH" \
  make -s -C "$REPO" external-updates PERSONAL_SKILLS=facebook-marketplace >/dev/null || bad "personal-only override"
personal=$(cat "$h/personal.log")
check "a personal-only override uses the personal Pack" has "$personal" 'add halloffamer11/skills-personal --skill facebook-marketplace --agent'
check "a personal-only override skips the core Pack" sh -c '! printf "%s\n" "$1" | grep -q "add halloffamer11/skills --skill"' _ "$personal"

STUB_LOG="$h/both.log" HOME="$h" PATH="$stubs:$BASE_PATH" \
  make -s -C "$REPO" external-updates PERSONAL_SKILLS="toolsmith facebook-marketplace" >/dev/null || bad "mixed override"
both=$(cat "$h/both.log")
check "a mixed override splits by Pack" sh -c 'printf "%s\n" "$1" | grep -q "add halloffamer11/skills --skill toolsmith --agent" &&
  printf "%s\n" "$1" | grep -q "add halloffamer11/skills-personal --skill facebook-marketplace --agent"' _ "$both"

# Idempotent: a second run leaves the same links.
before=$(find "$h/.claude" -type l | sort)
run "$h" "$stubs:$BASE_PATH" >/dev/null || bad "without brew: rerun"
check "a rerun leaves the same links" [ "$before" = "$(find "$h/.claude" -type l | sort)" ]

# A stale link from before the split is removed; a live one is kept.
mkdir -p "$h/.claude/skills"
ln -s /nowhere/dotfiles/agents/skills/old "$h/.claude/skills/old"
ln -s "$REPO" "$h/.claude/skills/keep"
run "$h" "$stubs:$BASE_PATH" >/dev/null
check "a dangling link into the old dotfiles skills is removed" test ! -L "$h/.claude/skills/old"
check "a live link is kept" test -L "$h/.claude/skills/keep"
rm -rf "$h"

# Homebrew with hunk: the optional skill is linked.
h=$(fresh_home)
mkdir -p "$h/brew/libexec/skills/hunk-review"
cat > "$stubs/brew" <<STUB
#!/bin/sh
[ "\$1" = --prefix ] && [ "\$2" = hunk ] && echo "$h/brew" && exit 0
exit 1
STUB
chmod +x "$stubs/brew"
out=$(run "$h" "$stubs:$BASE_PATH") || bad "with hunk: skills succeed" "$out"
check "with Homebrew's hunk, hunk-review is linked" \
  [ "$(readlink "$h/.claude/skills/hunk-review")" = "$h/brew/libexec/skills/hunk-review" ]
rm -rf "$h"

# Homebrew without hunk.
h=$(fresh_home)
printf '#!/bin/sh\necho /nonexistent/hunk\n' > "$stubs/brew"
out=$(run "$h" "$stubs:$BASE_PATH") || bad "brew without hunk: skills succeed" "$out"
check "with Homebrew but no hunk, hunk-review is skipped with a notice" has "$out" "notice: "
rm -rf "$h" "$stubs"
finish
