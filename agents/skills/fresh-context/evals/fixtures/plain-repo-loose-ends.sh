#!/bin/sh
# Plain repo, no tracker: a dead copy of old code, a session notes file that
# holds one standing fact among the status, half-done WIP, and dated bullets
# appended to CLAUDE.md.
. "$(dirname "$0")/_lib.sh" "$1"

cat > cli.py <<'X'
import argparse, utils

def main():
    p = argparse.ArgumentParser()
    p.add_argument("path")
    a = p.parse_args()
    for line in utils.summarize(a.path):
        print(line)

if __name__ == "__main__":
    main()
X
cat > utils.py <<'X'
def summarize(path):
    with open(path) as f:
        lines = f.read().splitlines()
    return [f"lines: {len(lines)}", f"words: {sum(len(l.split()) for l in lines)}"]
X
cat > CLAUDE.md <<'X'
# wc-lite

A tiny word-count CLI.

- Run: `python cli.py <file>`
- Test: `python -m pytest -q`
- Output goes to stdout, one `key: value` per line.
X
base_commit "wc-lite"

# --- this session (uncommitted) ---
cp utils.py utils_old.py
cat > cli.py <<'X'
import argparse, json, utils

def main():
    p = argparse.ArgumentParser()
    p.add_argument("path")
    p.add_argument("--json", action="store_true")  # WIP: not wired yet
    a = p.parse_args()
    for line in utils.summarize(a.path):
        print(line)

if __name__ == "__main__":
    main()
X
cat > notes.md <<'X'
# session notes
- copied utils.py to utils_old.py before refactor (refactor abandoned)
- started --json flag; parser accepts it, output not switched yet
- IMPORTANT from user: stdout must stay ASCII, the legacy log parser breaks on anything else, so use json.dumps(..., ensure_ascii=True)
- next: switch output on --json, add a test
X
cat >> CLAUDE.md <<'X'
- 2026-09-23: started the --json flag; parser done, output not switched, next is the test
- 2026-09-23: utils refactor abandoned, utils_old.py kept for reference
X
