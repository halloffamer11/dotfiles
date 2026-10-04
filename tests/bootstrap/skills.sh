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
check "herdr and humanizer come from their upstreams, unpinned" \
  sh -c 'has() { printf "%s\n" "$1" | grep -q -- "$2"; }; has "$1" "skills@latest add herdrdev/herdr --skill herdr " && has "$1" "skills@latest add blader/humanizer --skill humanizer "' _ "$log"
check "skills install into Claude Code, Codex and Kiro only" \
  [ "$(printf '%s\n' "$log" | grep -c -- '--agent claude-code codex kiro-cli -g -y$')" -eq 3 ]
check "no skill version is pinned" sh -c '! printf "%s\n" "$1" | grep -q "@[0-9]"' _ "$log"

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
