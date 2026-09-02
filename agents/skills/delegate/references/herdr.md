# Herdr visibility lane — invocation reference

verified-against: herdr CLI (2026-08-16); requires HERDR_ENV=1. Explicit
opt-in only: the user asked to watch ("in herdr", "where I can see it").
Never auto-select — herdr adds visibility, not capability, and creating
panes the user didn't ask for violates the herdr skill's rules.

## Recipe (child in its own unfocused tab, left open for the user)
TAB=$(herdr tab create --workspace "$HERDR_WORKSPACE_ID" --cwd "<workdir>" \
      --label "delegate-<task>" --no-focus)
PANE=$(printf '%s' "$TAB" | python3 -c 'import json,sys;print(json.load(sys.stdin)["result"]["root_pane"]["pane_id"])')
herdr agent start delegate-<task> --kind <claude|codex|agy> --pane "$PANE" --timeout 90000
herdr agent prompt delegate-<task> "$(cat <promptfile>)" --wait --timeout <ms>
herdr agent read delegate-<task> --source recent-unwrapped --lines 200

## Quirks (observed 2026-08-16)
- `agent start --kind claude` reported focused:true even in a --no-focus tab
  (agy/codex did not). If focus matters, `herdr tab focus "$HERDR_TAB_ID"`
  right after start.
- Prompts that only open a TUI panel (/usage, /status) return
  agent_prompt_stalled — that is expected, not failure; read the pane.
  (Usage is read headlessly by scripts/usage.py anyway; do not use herdr
  for telemetry.)
- Alternate-screen output may be unrecoverable from scrollback; if a read
  comes back short, ask the child to write its answer to a file.
- Do not close the tab: the point of this lane is that the user inspects it.
