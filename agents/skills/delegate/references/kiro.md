# Kiro CLI — invocation reference (UNVERIFIED STUB)

verified-against: none — validate on the work machine before first use.

Documented in Kiro's docs, not yet tested here:
- `kiro-cli chat --list-models` exists; the catalog spans vendors including
  open-weight models (GLM etc.) — routing.md marks Kiro the flexible lane.
- No documented per-invocation `--model` flag: pinning may require a Kiro
  custom agent or a persistent setting. Treat model pinning as unsupported
  until verified. Do not mutate the user's global Kiro default model.

Work-machine validation checklist (replaces this stub with the standard
template + a real verified-against stamp):
1. `kiro-cli --version`; `kiro-cli chat --list-models`.
2. Find the non-interactive invocation path (the exec/--print equivalent).
3. Confirm sandbox/read-only options.
4. Rewrite this file in the codex.md/antigravity.md format.
