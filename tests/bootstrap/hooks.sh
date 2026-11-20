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
# Prefixed assignments run in a subshell: macOS sh (bash in POSIX mode) keeps an
# assignment made before a function call after the function returns.
commit() { echo "$1" >> "$repo/file"; g add file && g commit -q -m "$1"; }

(PATH="$stubs:$PATH" commit clean) >/dev/null 2>&1
check "hooks: a clean commit goes through" [ "$(g rev-list --count HEAD 2>/dev/null)" = 1 ]
check "hooks: gitleaks scans the staged changes" grep -q "gitleaks git --pre-commit --staged" "$h/calls.log"
check "hooks: the repository's own pre-commit still runs" grep -q local-pre-commit "$h/calls.log"

(PATH="$stubs:$PATH" commit FAKE_SECRET) >/dev/null 2>&1
check "hooks: a finding blocks the commit" [ "$(g rev-list --count HEAD)" = 1 ]
g reset -q --hard

(SKIP_GITLEAKS=1 PATH="$stubs:$PATH" commit FAKE_SECRET) >/dev/null 2>&1
check "hooks: SKIP_GITLEAKS=1 lets it through" [ "$(g rev-list --count HEAD)" = 2 ]

# No gitleaks: warn and commit. GITLEAKS names a missing command, since a real
# gitleaks may share a PATH directory with git (Homebrew on the macOS runner).
nogl=$( (GITLEAKS="$h/no-gitleaks" commit unscanned) 2>&1)
if [ "$(g rev-list --count HEAD)" = 3 ] && has "$nogl" "not installed"; then
  ok "hooks: without gitleaks the commit goes through with a warning"
else
  bad "hooks: without gitleaks the commit goes through with a warning" "$nogl"
fi

# Git LFS: its hooks live in .git/hooks, which core.hooksPath hides, so the
# dispatcher calls git-lfs. pre-push must get the refs on stdin, and so must the
# repository's own pre-push. GIT_LFS points at a stub.
cat > "$stubs/lfs" <<'STUB'
#!/bin/sh
echo "lfs $1 stdin=$(cat | tr '\n' ' ')" >> "$HOME/lfs.log"
[ -f "$HOME/lfs-fail" ] && exit 1
exit 0
STUB
chmod +x "$stubs/lfs"
printf '#!/bin/sh\necho "local-pre-push stdin=$(cat | tr "\\n" " ")" >> "$HOME/lfs.log"\n' > "$repo/.git/hooks/pre-push"
chmod +x "$repo/.git/hooks/pre-push"
git init -q --bare "$h/remote.git"
g remote add origin "$h/remote.git"
lfs_push() { (GIT_LFS="$stubs/lfs" SKIP_GITLEAKS=1 HOME="$h" GIT_CONFIG_NOSYSTEM=1 git -C "$repo" push -q origin HEAD:refs/heads/main) >/dev/null 2>&1; }

lfs_push
check "hooks: pre-push calls git-lfs with the refs on stdin" grep -q "lfs pre-push stdin=HEAD [0-9a-f]* refs/heads/main" "$h/lfs.log"
check "hooks: the repository's own pre-push still gets the refs" grep -q "local-pre-push stdin=HEAD [0-9a-f]* refs/heads/main" "$h/lfs.log"
check "hooks: the push goes through" [ -n "$(g rev-parse -q --verify refs/remotes/origin/main)" ]

touch "$h/lfs-fail"
commit lfs-blocked-push >/dev/null 2>&1 || true
lfs_push
check "hooks: a git-lfs pre-push failure blocks the push" [ "$(g rev-parse HEAD)" != "$(g rev-parse origin/main 2>/dev/null)" ]
rm -f "$h/lfs-fail"

finish
