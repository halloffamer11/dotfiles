#!/bin/sh
# full-modes.sh — write-lane test in PERMISSIVE modes. Run it yourself: sh tests/full-modes.sh
# Each harness gets a fresh git copy of the fixture under ~/.cache/delegate and must fix calc.py
# AND run the gate command (python3 assert). Reports FILE_FIXED and whether the gate ran.
# Modes: agy --dangerously-skip-permissions | grok auto, grok bypassPermissions (sandbox workspace)
#        claude --allowedTools "Bash Edit Write Read", claude --dangerously-skip-permissions
D=$(cd "$(dirname "$0")/.." && pwd); B=$D/tests/fixture/brief-write.md; S=$D/schemas/return.json
H=$HOME/.cache/delegate/full-$$; R=$H/results; mkdir -p "$R"
mk() { W=$H/$1; mkdir -p "$W"; cp "$D/tests/fixture/calc.py" "$W/"; (cd "$W" && git init -q && git add -A && git -c user.email=t@t -c user.name=t commit -qm fixture)
  { cat "$D/preamble.md"; echo "Writes are authorized inside $W only. Do not commit. Run the gate command in the definition of done and report its result."
    printf '\n# Working directory\n%s\n\n' "$W"; cat "$B"
    [ "$2" = grok ] && { printf '\n# Return schema\nYour final message is ONLY one JSON object matching:\n'; cat "$S"; }; } > "$W.prompt.md"; }
mk agy-full agy; mk grok-auto grok; mk grok-bypass grok; mk claude-allow claude; mk claude-bypass claude
( cd "$H/agy-full" && agy --model gemini-3.8-flash-high --mode accept-edits --dangerously-skip-permissions --print-timeout 6m --output-format json --json-schema "$S" --print "$(cat "$H/agy-full.prompt.md")" >"$R/agy-full.raw" 2>"$R/agy-full.err" </dev/null ) &
( cd "$H/grok-auto" && grok --prompt-file "$H/grok-auto.prompt.md" --permission-mode auto --sandbox workspace --no-subagents -m grok-4.6 --reasoning-effort low --output-format json --max-turns 40 --cwd "$H/grok-auto" >"$R/grok-auto.raw" 2>"$R/grok-auto.err" </dev/null ) &
( cd "$H/grok-bypass" && grok --prompt-file "$H/grok-bypass.prompt.md" --permission-mode bypassPermissions --sandbox workspace --no-subagents -m grok-4.6 --reasoning-effort low --output-format json --max-turns 40 --cwd "$H/grok-bypass" >"$R/grok-bypass.raw" 2>"$R/grok-bypass.err" </dev/null ) &
( cd "$H/claude-allow" && claude -p --permission-mode acceptEdits --allowedTools "Bash Edit Write Read" --model sonnet --output-format json --json-schema "$(cat "$S")" "$(cat "$H/claude-allow.prompt.md")" >"$R/claude-allow.raw" 2>"$R/claude-allow.err" </dev/null ) &
( cd "$H/claude-bypass" && claude -p --dangerously-skip-permissions --model sonnet --output-format json --json-schema "$(cat "$S")" "$(cat "$H/claude-bypass.prompt.md")" >"$R/claude-bypass.raw" 2>"$R/claude-bypass.err" </dev/null ) &
wait
for v in agy-full grok-auto grok-bypass claude-allow claude-bypass; do
  printf '%-14s ' "$v"; grep -q 'return a + b' "$H/$v/calc.py" && printf 'FILE_FIXED     ' || printf 'FILE_UNCHANGED '
  h=${v%%-*}; python3 "$D/extract.py" "$h" "$R/$v.raw" "$R/$v.json" >/dev/null
  python3 -c "import json,sys; o=json.load(open(sys.argv[1])); print('status=',o['status'],'| gate ran:', 'yes' if ('pass' in o['deliverable'].lower() and not o['open_questions']) else 'unclear', '|', o['deliverable'][:90].replace(chr(10),' '))" "$R/$v.json"
  e=$(head -c 160 "$R/$v.err" | tr '\n' ' '); [ -n "$e" ] && echo "     err: $e"
done
echo "raw results: $R"
