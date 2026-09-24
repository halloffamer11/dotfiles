#!/bin/sh
# Root CLAUDE.md far over budget: dated status copied from the tracker, dated
# decisions, one paragraph-length line that hides a rule, and a nested
# api/CLAUDE.md that links to the root file. Tripwires must fire.
. "$(dirname "$0")/_lib.sh" "$1"

mkdir -p api docs/issues
printf 'def handler(req):\n    return {"ok": True}\n' > api/handlers.py
printf 'SCHEMAS = {}\n' > api/schemas.py
i=1
while [ $i -le 12 ]; do
  n=$(printf '%02d' $i)
  printf '# %s: feature %s\n\n**Status:** landed\n' "$n" "$n" > docs/issues/$n.md
  i=$((i + 1))
done
printf '# 13: rate limiting\n\n**Status:** in progress\n' > docs/issues/13.md

{
  cat <<'X'
# ledger

Double-entry ledger service: `api/` (HTTP), `core/` (posting engine).

## Commands
- Install: `uv sync`
- Test: `uv run pytest -q`
- Lint: `uv run ruff check .`
- Serve: `uv run ledger serve --port 8080`

## Conventions
- Amounts are integers in minor units; never floats.
- Every posting balances to zero; `core.post` raises otherwise.
- Timestamps are UTC, ISO 8601, with a trailing Z.
- Public functions carry type hints.
- One module per aggregate in `core/`.
- Tests mirror the source tree under `tests/`.
- No network calls in unit tests; use the fakes in `tests/fakes.py`.
- Migrations are append-only.
- Log with `structlog`; never `print`.
- Error codes live in `core/errors.py`; do not invent new strings inline.
- Commit messages: `area: summary`, imperative, under 72 characters.
- Tickets live in `docs/issues/`, one file per ticket.

## Status
X
  i=1
  while [ $i -le 12 ]; do
    n=$(printf '%02d' $i)
    d=$(printf '2026-08-%02d' $((i + 10)))
    echo "- $d: ticket $n landed after review; tests green; follow-ups filed in the ticket."
    echo "- $d: ticket $n deployed to staging; smoke tests passed; production rollout scheduled."
    echo "- $d: ticket $n closed; see docs/issues/$n.md for the landed note."
    i=$((i + 1))
  done
  echo "- 2026-09-20: ticket 13 (rate limiting) in progress; token bucket drafted in core/limits.py."
  echo
  echo "## Decisions"
  i=1
  while [ $i -le 30 ]; do
    d=$(printf '2026-08-%02d' $(( (i % 28) + 1 )))
    echo "- $d: decision $i: chose option A over option B because A keeps postings immutable and B would need a migration; the user confirmed A in review."
    i=$((i + 1))
  done
  echo
  echo "## Notes"
  printf '%s' "- Back in August we spent a long time on the posting engine and found that retries in the API layer could double-post when the client timed out, which took most of a week to track down across three tickets, and the fix that finally held was to make every handler in api/ validate its input against the schemas in api/schemas.py and to require an Idempotency-Key header on every POST so a retry returns the first result instead of posting again, which is now a hard rule for anything under api/, and we also noticed along the way that the staging database had drifted from production because someone ran a migration by hand, which is why migrations are now append-only and run only through the deploy script, and there were several other smaller findings about logging and error codes that are recorded in the tickets for that period if anyone needs them later."
  echo
  i=1
  while [ $i -le 110 ]; do
    echo "- 2026-09-$(printf '%02d' $(( (i % 20) + 1 ))): review note $i: reviewer asked for clearer names in core/; addressed in the follow-up commit."
    i=$((i + 1))
  done
} > CLAUDE.md
ln -s CLAUDE.md AGENTS.md
ln -s ../CLAUDE.md api/CLAUDE.md
base_commit "ledger"

# --- this session (uncommitted) ---
echo "- 2026-09-23: ticket 13 token bucket passes unit tests; burst handling still open." >> CLAUDE.md
echo "- 2026-09-23: ticket 13 needs a decision on per-key vs per-IP limits; asked the user." >> CLAUDE.md
printf 'def allow(key):\n    return True  # WIP token bucket\n' > api/limits.py
