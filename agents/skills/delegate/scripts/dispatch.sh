#!/bin/sh
# dispatch.sh — the ONE way a child harness is run.
#
# Couriers (the Haiku agents in ~/.claude/agents/*-runner.md) call this and
# relay the output file. The session may also call it inline for a short
# result. Whoever calls it, the child gets the same preamble, the same return
# schema, and the same safety flags, so the review surface is this file plus
# references/<harness>.md, which it mirrors.
#
# USAGE
#   dispatch.sh --harness agy|codex|grok|claude --role <role> --brief <task.md>
#               --cwd <dir> --out <file>
#               [--write <worktree>]        writes allowed, ONLY inside this worktree
#               [--effort low|medium|high]  reasoning effort (default medium)
#               [--tool-budget N]           child stops exploring after N tool calls (default 12)
#               [--resume <session-id>]     continue an earlier child instead of a cold start
#               [--keep-session]            codex only: keep the session so it can be resumed later
#               [--dry-run]                 print the command, run nothing
#
# INPUT  <task.md>: five lines, one per prefix, nothing else —
#   objective: ...   scope: ...   constraints: ...   done: ...   return: ...
# OUTPUT --out <file>: ONLY the object from schemas/return.json
#   {status, deliverable, evidence[], open_questions[], changed_files[]}
# PRINTS one line:  delegate: <role> -> <slug> via <harness> (rc=..; session=..; out=..)
#
# STEPS  1 parse args  2 resolve model by role  3 render the brief from the
#        template  4 build the harness command  5 run headless, stdin closed
#        6 normalise the child's envelope to the schema object
#
# TIMEOUTS: none here — the caller's Bash tool timeout is the limit (macOS has
# no timeout binary). sol@codex at high effort exceeds 10 minutes: callers use
# run_in_background and poll --out.

exec </dev/null            # every harness blocks on an open stdin
set -u

SKILL=$(cd "$(dirname "$0")/.." && pwd)
SCHEMA="$SKILL/schemas/return.json"
TEMPLATE="$SKILL/templates/brief.md"

# ---- 1. arguments ------------------------------------------------------------
harness=""; role=""; brief=""; cwd=""; out=""
write=""; effort="medium"; tool_budget=12; resume=""; keep_session=0; dry_run=0
while [ $# -gt 0 ]; do
  case $1 in
    --harness)      harness=$2;     shift ;;
    --role)         role=$2;        shift ;;
    --brief)        brief=$2;       shift ;;
    --cwd)          cwd=$2;         shift ;;
    --out)          out=$2;         shift ;;
    --write)        write=$2;       shift ;;
    --effort)       effort=$2;      shift ;;
    --tool-budget)  tool_budget=$2; shift ;;
    --resume)       resume=$2;      shift ;;
    --keep-session) keep_session=1 ;;
    --dry-run)      dry_run=1 ;;
    *) echo "dispatch.sh: unknown argument $1" >&2; exit 2 ;;
  esac
  shift
done
if [ -z "$harness" ] || [ -z "$role" ] || [ -z "$brief" ] || [ -z "$cwd" ] || [ -z "$out" ]; then
  sed -n '10,17p' "$0" >&2
  exit 2
fi
if [ -n "$write" ]; then
  cwd=$write            # a write-enabled child always runs inside its worktree
fi

# ---- 2. model by role (never from memory; empty = lane unavailable) ----------
slug=$(sh "$SKILL/scripts/resolve-model.sh" "$role")
if [ -z "$slug" ]; then
  echo "delegate: lane unavailable — role $role resolved to nothing on $harness" >&2
  exit 3
fi

# ---- 3. the brief: template + the five task lines ----------------------------
field() {
  # value of "<name>: ..." from the task file, empty if absent
  grep -i "^$1:" "$brief" | sed "s/^[^:]*:[[:space:]]*//"
}
if [ -n "$write" ]; then
  write_rule="Writes are authorized inside $write only (an isolated git worktree). Do not touch files outside it. Do not commit."
else
  write_rule="Read-only: do not create, edit, or delete files."
fi
prompt_file=$(mktemp -t delegate-brief).md
python3 "$SKILL/scripts/render-brief.py" "$TEMPLATE" "$prompt_file" \
  "$tool_budget" "$(field objective)" "$cwd" "$(field scope)" \
  "$(field constraints)" "$write_rule" "$(field done)" "$(field return)"

# ---- 4. the command, per harness (mirrors references/<harness>.md) -----------
case $harness in
  agy)
    # Antigravity: --print must be LAST; --mode plan is the read-only guard.
    mode=plan
    if [ -n "$write" ]; then mode=accept-edits; fi
    set -- agy --model "$slug" --mode "$mode" --sandbox \
           --output-format json --json-schema "$SCHEMA"
    if [ -n "$resume" ]; then set -- "$@" --conversation "$resume"; fi
    set -- "$@" --print "$(cat "$prompt_file")"
    ;;
  codex)
    # Codex: -s read-only|workspace-write is the guard; -o writes the last message.
    sandbox=read-only
    if [ -n "$write" ]; then sandbox=workspace-write; fi
    if [ -n "$resume" ]; then
      set -- codex exec resume "$resume" --skip-git-repo-check -C "$cwd" \
             --output-schema "$SCHEMA" -o "$out" "$(cat "$prompt_file")"
    else
      set -- codex exec --ignore-user-config --skip-git-repo-check -C "$cwd" \
             -m "$slug" -c "model_reasoning_effort=\"$effort\"" -s "$sandbox" \
             --output-schema "$SCHEMA" -o "$out"
      if [ "$keep_session" = 0 ]; then set -- "$@" --ephemeral; fi
      set -- "$@" "$(cat "$prompt_file")"
    fi
    ;;
  grok)
    # Grok: --tools is the read-only guard (removes shell and edit tools entirely).
    if [ -n "$write" ]; then
      set -- grok --prompt-file "$prompt_file" --permission-mode acceptEdits \
             --allow Write --allow Edit --sandbox workspace
    else
      set -- grok --prompt-file "$prompt_file" --permission-mode plan \
             --tools read_file,list_dir,grep
    fi
    set -- "$@" --no-subagents --disable-web-search -m "$slug" \
           --reasoning-effort "$effort" --output-format json \
           --json-schema "$(cat "$SCHEMA")" --max-turns $((tool_budget * 2)) --cwd "$cwd"
    if [ -n "$resume" ]; then set -- "$@" -r "$resume"; fi
    ;;
  claude)
    # Headless Claude: --permission-mode plan is the read-only guard; OAuth form (no --bare).
    permission=plan
    if [ -n "$write" ]; then permission=acceptEdits; fi
    set -- claude -p --permission-mode "$permission" --model "$slug" \
           --output-format json --json-schema "$(cat "$SCHEMA")"
    if [ -n "$resume" ]; then set -- "$@" --resume "$resume"; fi
    set -- "$@" "$(cat "$prompt_file")"
    ;;
  *)
    echo "dispatch.sh: unknown harness $harness" >&2
    exit 2
    ;;
esac

if [ "$dry_run" = 1 ]; then
  echo "would run (in $cwd):"
  for arg in "$@"; do
    if [ "$arg" = "$(cat "$prompt_file")" ]; then printf ' <brief>'
    else printf ' %s' "$arg" | cut -c1-160 | tr -d '\n'
    fi
  done
  echo
  echo "brief: $prompt_file"
  exit 0
fi

# ---- 5. run ------------------------------------------------------------------
cd "$cwd" || exit 2
raw=$(mktemp -t delegate-raw)
"$@" >"$raw" 2>"$raw.err"
rc=$?

# ---- 6. normalise: keep only the schema object in $out -----------------------
# agy prints {conversation_id, structured_output}; grok {sessionId, text};
# claude {session_id, structured_output|result}; codex wrote the last message to $out.
source=$raw
if [ "$harness" = codex ]; then
  source=$out.raw
  cp "$out" "$source" 2>/dev/null
fi
session_id=$(python3 "$SKILL/scripts/normalize.py" "$source" "$out")

# ---- 7. one retry on the next-newest slug ------------------------------------
# A freshly listed model version can be rejected by the service for a while
# (seen 2026-09-02: agy listed 3.8-flash, then failed on it). If the child
# exited non-zero with no usable answer, and this is a cold start, re-resolve
# the role with this slug excluded and run once more. Never loops.
retry_note=""
if [ "$rc" -ne 0 ] && [ -z "$resume" ] && [ -z "${DELEGATE_EXCLUDE:-}" ]; then
  status=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('status',''))" "$out" 2>/dev/null)
  if [ "$status" = "blocked" ] || [ "$status" = "partial" ]; then
    next_slug=$(DELEGATE_EXCLUDE="$slug" sh "$SKILL/scripts/resolve-model.sh" "$role")
    if [ -n "$next_slug" ] && [ "$next_slug" != "$slug" ]; then
      echo "delegate: $slug failed (rc=$rc); retrying once on $next_slug" >&2
      DELEGATE_EXCLUDE="$slug" exec sh "$0" --harness "$harness" --role "$role" --brief "$brief" \
        --cwd "$cwd" --out "$out" --effort "$effort" --tool-budget "$tool_budget" \
        ${write:+--write "$write"} ${keep_session:+$( [ "$keep_session" = 1 ] && echo --keep-session )}
    fi
  fi
fi
if [ -n "${DELEGATE_EXCLUDE:-}" ]; then retry_note="; retried-after=${DELEGATE_EXCLUDE}"; fi

echo "delegate: $role -> $slug via $harness (rc=$rc; effort=$effort; out=$out; session=${session_id:-?}; err=$raw.err$retry_note)"
exit $rc
