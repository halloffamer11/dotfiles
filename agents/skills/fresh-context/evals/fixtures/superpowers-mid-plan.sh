#!/bin/sh
# Superpowers layout mid-plan: step 3 done in code but unchecked, an abandoned
# experiment, scratch files, and a status section pasted into CLAUDE.md.
. "$(dirname "$0")/_lib.sh" "$1"

mkdir -p src docs/superpowers/plans
cat > README.md <<'X'
# tally
Small CLI that tallies CSV columns. `python -m tally <file>`.
X
cat > src/tally.py <<'X'
import csv, sys

def tally(path):
    counts = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            for k, v in row.items():
                counts.setdefault(k, {}).setdefault(v, 0)
                counts[k][v] += 1
    return counts
X
cat > src/export.py <<'X'
"""Export tallies. Plan: docs/superpowers/plans/2026-09-20-json-export.md"""

def to_rows(counts):
    return [(col, val, n) for col, vals in counts.items() for val, n in vals.items()]
X
cat > docs/superpowers/plans/2026-09-01-csv-import.md <<'X'
# CSV import plan
- [x] 1. Read with csv.DictReader
- [x] 2. Tally per column
- [x] 3. Tests for empty files
X
cat > docs/superpowers/plans/2026-09-20-json-export.md <<'X'
# JSON export plan
- [x] 1. Flatten counts to rows (`to_rows`)
- [x] 2. Decide output shape: list of {column, value, count}
- [ ] 3. JSON writer `write_json(counts, fp)`
- [ ] 4. `--json` CLI flag
- [ ] 5. Tests
X
cat > CLAUDE.md <<'X'
# tally

CLI that tallies CSV columns.

## Commands
- Run: `python -m tally <file>`
- Test: `python -m pytest -q`

## Conventions
- Standard library only; no third-party runtime dependencies.
- Plans live in `docs/superpowers/plans/`.

## Active plan
- `docs/superpowers/plans/2026-09-01-csv-import.md`
X
base_commit "tally: csv import and export rows"

# --- this session (uncommitted) ---
cat >> src/export.py <<'X'

import json

def write_json(counts, fp):
    rows = [{"column": c, "value": v, "count": n} for c, v, n in to_rows(counts)]
    json.dump(rows, fp, indent=2)
X
mkdir -p experiment scratch
cat > experiment/try_orjson.py <<'X'
import orjson  # tried for speed; rejected
def write_json(counts, fp):
    fp.write(orjson.dumps(counts).decode())
X
printf 'stdlib json: 41 ms\norjson: 29 ms\n(10k rows)\n' > scratch/bench.txt
cat > notes-tmp.md <<'X'
- orjson is faster (29 vs 41 ms on 10k rows) but breaks the stdlib-only rule. Decision: keep stdlib json.
- step 3 done, next is step 4 (--json flag)
X
cat >> CLAUDE.md <<'X'

## Current focus
Working on the JSON export plan. Steps 1 and 2 were done last week and step 3, the JSON writer, was finished in this session on 2026-09-23 using the standard library json module after an experiment with orjson showed it to be faster (29 ms against 41 ms on ten thousand rows) but not worth breaking the standard-library-only rule, so the next thing to do is step 4, which adds the --json flag to the CLI, and then step 5, the tests, after which the plan is complete and can be closed.
X
