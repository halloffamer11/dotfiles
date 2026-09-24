#!/bin/sh
# Session already committed its one fix. Nothing to settle. CLAUDE.md has a
# wordy but stable line under every tripwire: a diff-scoped review leaves it.
. "$(dirname "$0")/_lib.sh" "$1"

cat > parser.py <<'X'
def parse(s):
    return [t for t in s.split(",") if t]
X
cat > CLAUDE.md <<'X'
# csvtok

Splits comma-separated tokens.

- Test: `python -m pytest -q`
- Keep `parse` pure: it takes a string and returns a list, and it must never read files or the environment, because the fuzz harness calls it millions of times.
- Issues: GitHub issues on the repo; no local tracker.
X
base_commit "csvtok"

# --- this session (committed) ---
cat > parser.py <<'X'
def parse(s):
    """Split on commas and drop empty tokens."""
    return [t for t in s.split(",") if t]
X
git commit -qam "parser: docstring typo fix"
