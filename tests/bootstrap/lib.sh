# Shared helpers for the isolated-home bootstrap checks. Each check runs make
# against a throwaway HOME, so the runner's own home is never touched.
REPO=$(cd "$(dirname "$0")/../.." && pwd)
FAILS=0
# Tools such as chezmoi and mise read XDG_* before HOME. Unset, they follow the throwaway HOME.
unset XDG_CONFIG_HOME XDG_DATA_HOME XDG_STATE_HOME XDG_CACHE_HOME
ok() { echo "PASS $1"; }
bad() { echo "FAIL $1"; [ -n "$2" ] && printf '%s\n' "$2" | sed 's/^/     /'; FAILS=$((FAILS + 1)); }
check() { name=$1; shift; if "$@"; then ok "$name"; else bad "$name"; fi; }
fresh_home() { mktemp -d "${TMPDIR:-/tmp}/dotfiles-home.XXXXXX"; }
finish() { [ "$FAILS" -eq 0 ] || { echo "$FAILS failed"; exit 1; }; }
has() { printf '%s\n' "$1" | grep -q -- "$2"; }  # has TEXT PATTERN
