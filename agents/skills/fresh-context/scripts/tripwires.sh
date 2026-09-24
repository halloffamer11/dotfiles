#!/bin/sh
# Tripwires for fresh-context step 3. Run from the project root.
# Prints the size of each instruction file, one FIRE line per tripwire, and
# one WARN line per status word for the agent to judge.
# Exit status: 0 when nothing fires, 1 when something fires.
# awk for the checks: a grep on PATH may be a shim with other defaults.
# python3, when present, only reads claudeMdExcludes: an excluded file never
# loads, so it is not checked.

MAX_LINES=200
MAX_BYTES=10240
MAX_LINE_CHARS=300

fired=0

# Instruction files: every CLAUDE.md, AGENTS.md, CLAUDE.local.md and rule.
# Skips dependency and worktree trees, and `_`-prefixed non-content dirs.
list() {
  find . \( -name .git -o -name node_modules -o -name .worktrees -o -name '_*' \) -prune \
    -o \( -name CLAUDE.md -o -name AGENTS.md -o -name CLAUDE.local.md \
          -o -path '*/.claude/rules/*.md' \) "$@" -print | loaded
}

# Drops files that match a claudeMdExcludes glob in the project or user
# settings, and names each one on stderr.
loaded() {
  command -v python3 >/dev/null 2>&1 || { cat; return; }
  python3 -c '
import fnmatch, json, os, sys
pats = []
for s in (".claude/settings.json", ".claude/settings.local.json",
          os.path.expanduser("~/.claude/settings.json")):
    try:
        pats += json.load(open(s)).get("claudeMdExcludes", [])
    except (OSError, ValueError):
        pass
for line in sys.stdin:
    p = line.rstrip("\n")
    paths = (os.path.abspath(p), os.path.realpath(p))
    if any(fnmatch.fnmatch(a, x) for a in paths for x in pats):
        print("skip  excluded   " + p, file=sys.stderr)
    else:
        print(p)
'
}

# Links: a link to a file in the same directory is fine; any other target
# loads text that another file already loads, or points outside the directory.
list -type l | while IFS= read -r f; do
  target=$(readlink "$f")
  case "$target" in
    */*) echo "FIRE  link       $f -> $target" ;;
  esac
done | awk '{print} END {exit NR > 0}' || fired=1

# Sizes and per-line checks, on regular files only, so a link is not
# counted twice.
list -type f | {
  rc=0
  while IFS= read -r f; do
    awk -v f="$f" -v ml="$MAX_LINES" -v mb="$MAX_BYTES" -v mc="$MAX_LINE_CHARS" '
      { bytes += length($0) + 1 }
      length($0) > mc { printf "FIRE  long-line  %s:%d (%d chars)\n", f, FNR, length($0); hit = 1 }
      # A date outside a path is state. A date inside a file name
      # (`plans/2026-09-20-x.md`) is a pointer, so it does not count.
      $0 ~ /(^|[^\/0-9-])20[0-9][0-9]-[0-9][0-9]-[0-9][0-9]([^0-9-]|$)/ {
        printf "FIRE  date       %s:%d: %s\n", f, FNR, substr($0, 1, 80); hit = 1
      }
      # Status words are only a hint: a rule can say "blocked" too.
      tolower($0) ~ /landed|blocked|waiting on|in progress/ {
        printf "WARN  status     %s:%d: %s\n", f, FNR, substr($0, 1, 80)
      }
      # A root line that names one directory ("In `web/`") or a glob
      # ("tests/**") may belong in a nested file or a scoped rule.
      f == "./CLAUDE.md" && ($0 ~ /^[-*] +[Ii]n `?[A-Za-z0-9_.-]+\/`?/ || $0 ~ /\*\*\/|\/\*\*/) {
        printf "WARN  scope      %s:%d: %s\n", f, FNR, substr($0, 1, 80)
      }
      END {
        printf "size  %5d lines %7d bytes  %s\n", NR, bytes, f
        if (NR > ml) { printf "FIRE  lines>%d  %s (%d)\n", ml, f, NR; hit = 1 }
        if (bytes > mb) { printf "FIRE  bytes>%d %s (%d)\n", mb, f, bytes; hit = 1 }
        exit hit
      }' "$f" || rc=1
  done
  exit $rc
} || fired=1

exit $fired
