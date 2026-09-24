#!/bin/sh
# Area-only instructions in the root CLAUDE.md, and an unscoped misc rule that
# mixes topics, contradicts CLAUDE.md, and carries state. Two of the area
# lines were added this session.
. "$(dirname "$0")/_lib.sh" "$1"

mkdir -p src tests web/src migrations notebooks docs/issues .claude/rules
printf 'def area(w, h):\n    return w * h\n' > src/geo.py
printf 'from src.geo import area\n\ndef test_area():\n    assert area(2, 3) == 6\n' > src/geo_test.py
printf 'import pytest\n\n@pytest.fixture\ndef client():\n    return object()\n' > tests/conftest.py
printf 'export const App = () => null;\n' > web/src/App.tsx
printf '{"name": "web", "packageManager": "pnpm@9.0.0"}\n' > web/package.json
printf 'lockfileVersion: 9.0\n' > web/pnpm-lock.yaml
printf 'CREATE TABLE shapes (id INTEGER PRIMARY KEY);\n' > migrations/0001_init.sql
printf 'ALTER TABLE shapes ADD COLUMN kind TEXT;\n' > migrations/0002_kind.sql
printf '{"cells": [], "nbformat": 4}\n' > notebooks/explore.ipynb
printf '# 004: notebook support\n\n**Status:** in progress. `src/nb.py` loads cells; rendering not started.\n' > docs/issues/004-notebooks.md
cat > CLAUDE.md <<'X'
# shapes

Geometry service: Python in `src/`, React front end in `web/`, SQL in `migrations/`.

## Commands
- Test: `python -m pytest -q`
- Web dev server: `cd web && pnpm dev`

## Conventions
- Python: type hints on public functions.
- In `web/`, use pnpm, never npm or yarn: the lockfile is `pnpm-lock.yaml`.
- In `web/`, component files are PascalCase (`App.tsx`).
- Test files (`tests/**` and `src/**/*_test.py`): use the fixtures in `tests/conftest.py`; do not build clients by hand.

## Tickets
- `docs/issues/`, one file per ticket.
X
cat > .claude/rules/misc.md <<'X'
# Misc
- Use npm in web/ for installs.
- Prefer f-strings over format().
- 2026-09-19: notebook cleanup in progress, see ticket 004.
X
base_commit "shapes"

# --- this session (uncommitted) ---
printf 'import json\n\ndef load(path):\n    return json.load(open(path))["cells"]\n' > src/nb.py
cat >> CLAUDE.md <<'X'
- Never edit a migration in `migrations/` once it is on main; add a new numbered file instead.
- To read a `.ipynb` notebook, convert it first with `jupyter nbconvert --to script`; do not read the raw JSON.
X
