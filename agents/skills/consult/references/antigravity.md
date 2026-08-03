# Antigravity CLI (agy, Google) — invocation reference

verified-against: 1.1.10 (2026-08-03)

## Read-only
agy --model <slug> --mode plan --sandbox --print "$(cat <promptfile>)" </dev/null

## Write-enabled (only when the user authorized implementation; isolated worktree)
Same but `--mode accept-edits`.

## Models
Slug IDs only, from live `agy models` (e.g. gemini-3.6-flash-medium,
gemini-3.1-pro-high). Catalog also lists claude-* and gpt-oss-* lanes.

## Quirks
- Hard-fails on unknown `--model` — always pick from live `agy models` output.
- Display names ("Gemini 3.5 Flash (Medium)") are dead; slugs replaced them.
- Serves non-Gemini models too: per routing.md Harness selection, prefer agy
  only for Gemini models (native pairing).
- Cold start (observed 2026-08-03): a session's first --print call can hang
  to the 5m default timeout with zero output, then succeed in seconds on
  identical retry. No output after ~60s → kill and retry once before
  treating it as failure; a second hang is a real failure, not drift.
