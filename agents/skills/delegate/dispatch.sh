#!/bin/sh
# dispatch.sh <lane> <brief.md> <out.json> [--cwd DIR] [--write DIR] [--effort low|medium|high]
# One lane, one command, one file out. Lanes are rows in lanes.tsv; the command
# per harness is fixed below. Prints: delegate: <lane> rc=<n> secs=<n> out=<file>
# Read-only (default): file tools only, no shell. --write DIR: full-auto inside that
# git worktree (codex workspace-write sandbox, grok auto + workspace sandbox, agy
# skip-permissions). Both forms verified live on every lane 2026-09-02 (tests/).
exec </dev/null; set -u
HERE=$(cd "$(dirname "$0")" && pwd); SCHEMA=$HERE/schemas/return.json
lane=${1:?lane}; brief=${2:?brief}; out=${3:?out}; shift 3
cwd=$PWD; write=""; effort=medium
while [ $# -gt 0 ]; do case $1 in --cwd) cwd=$2; shift;; --write) write=$2; shift;; --effort) effort=$2; shift;; *) echo "bad arg $1" >&2; exit 2;; esac; shift; done
case $brief in /*) ;; *) brief=$PWD/$brief;; esac
case $out   in /*) ;; *) out=$PWD/$out;;     esac
[ -n "$write" ] && cwd=$write
[ -d "$cwd" ] || { echo "dispatch: cwd not a directory: $cwd" >&2; exit 2; }
[ -f "$brief" ] || { echo "dispatch: brief not found: $brief" >&2; exit 2; }
row=$(grep -v '^#' "$HERE/lanes.tsv" | awk -F'\t' -v l="$lane" '$1==l {print $2"\t"$3}')
[ -n "$row" ] || { echo "dispatch: unknown lane $lane" >&2; exit 2; }
harness=${row%%	*}; slug=${row#*	}
prompt=$(mktemp -t brief).md
{ cat "$HERE/preamble.md"
  if [ -n "$write" ]; then echo "Writes are authorized inside $write only. Do not commit."
  else echo "Read-only: do not create, edit, or delete files."; fi
  # agy read-only auto-denies every command and ends the run with an empty response (verified 1.1.24).
  [ "$harness" = agy ] && [ -z "$write" ] && echo "You have NO terminal: any command tool is auto-denied and ends this session. Use the file tools only."
  printf '\n# Working directory\n%s\nEvery relative path in this brief is under it. Do not search elsewhere.\n\n' "$cwd"; cat "$brief"
  [ "$harness" = grok ] && { printf '\n# Return schema\nYour final message is ONLY one JSON object matching:\n'; cat "$SCHEMA"; }
} > "$prompt"
raw=$(mktemp -t delegate-raw); t0=$(date +%s)
cd "$cwd" || exit 2
case $harness in
  agy)   case $effort in low) pt=6m;; high) pt=25m;; *) pt=10m;; esac
         if [ -n "$write" ]; then set -- --mode accept-edits --dangerously-skip-permissions; else set -- --mode plan --sandbox; fi
         agy --model "$slug" "$@" --print-timeout $pt --output-format json --json-schema "$SCHEMA" --print "$(cat "$prompt")" >"$raw" 2>"$raw.err" ;;
  codex) sb=read-only; [ -n "$write" ] && sb=workspace-write
         codex exec --ignore-user-config --skip-git-repo-check -C "$cwd" -m "$slug" -c "model_reasoning_effort=\"$effort\"" -s $sb --output-schema "$SCHEMA" -o "$raw" --ephemeral "$(cat "$prompt")" >/dev/null 2>"$raw.err" ;;
  grok)  if [ -n "$write" ]; then set -- --permission-mode auto --sandbox workspace
         else set -- --permission-mode plan --tools read_file,list_dir,grep; fi
         grok --prompt-file "$prompt" "$@" --no-subagents --disable-web-search -m "$slug" --reasoning-effort "$effort" --output-format json --max-turns 40 --cwd "$cwd" >"$raw" 2>"$raw.err" ;;
esac
rc=$?
session=$(python3 "$HERE/extract.py" "$harness" "$raw" "$out")
echo "delegate: $lane rc=$rc secs=$(( $(date +%s)-t0 )) out=$out session=${session:-?} err=$raw.err"
exit $rc
