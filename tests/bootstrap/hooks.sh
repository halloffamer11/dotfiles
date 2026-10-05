#!/bin/sh
# Global git hooks: pre-commit runs gitleaks on the staged changes, and every
# hook still runs the repository's own copy. gitleaks is a stub here.
. "$(dirname "$0")/lib.sh"

h=$(fresh_home)
out=$(make -s -C "$REPO" configs PROFILE=linux HOME="$h" 2>&1) || bad "hooks: configs runs" "$out"
check "hooks: the hook directory and pre-commit are linked" test -x "$h/.config/git/hooks/pre-commit"

stubs=$(mktemp -d)
cat > "$stubs/gitleaks" <<'STUB'
#!/bin/sh
echo "gitleaks $*" >> "$HOME/calls.log"
git diff --cached | grep -q FAKE_SECRET && exit 1
exit 0
STUB
chmod +x "$stubs/gitleaks"

repo="$h/repo"
git init -q "$repo"
printf '#!/bin/sh\necho local-pre-commit >> "$HOME/calls.log"\n' > "$repo/.git/hooks/pre-commit"
chmod +x "$repo/.git/hooks/pre-commit"
g() { HOME="$h" GIT_CONFIG_NOSYSTEM=1 git -C "$repo" "$@"; }
commit() { echo "$1" >> "$repo/file"; g add file && g commit -q -m "$1"; }

PATH="$stubs:$PATH" commit clean >/dev/null 2>&1
check "hooks: a clean commit goes through" [ "$(g rev-list --count HEAD 2>/dev/null)" = 1 ]
check "hooks: gitleaks scans the staged changes" grep -q "gitleaks git --pre-commit --staged" "$h/calls.log"
check "hooks: the repository's own pre-commit still runs" grep -q local-pre-commit "$h/calls.log"

PATH="$stubs:$PATH" commit FAKE_SECRET >/dev/null 2>&1
check "hooks: a finding blocks the commit" [ "$(g rev-list --count HEAD)" = 1 ]
g reset -q --hard

SKIP_GITLEAKS=1 PATH="$stubs:$PATH" commit FAKE_SECRET >/dev/null 2>&1
check "hooks: SKIP_GITLEAKS=1 lets it through" [ "$(g rev-list --count HEAD)" = 2 ]

# No gitleaks on PATH: warn and commit.
nogl=$(PATH=$(printf '%s' "$PATH" | tr ':' '\n' | while read -r d; do [ -x "$d/gitleaks" ] || printf '%s:' "$d"; done); commit unscanned 2>&1)
check "hooks: without gitleaks the commit goes through with a warning" \
  sh -c '[ "$1" = 3 ] && printf "%s\n" "$2" | grep -q "not installed"' _ "$(g rev-list --count HEAD)" "$nogl"

finish
