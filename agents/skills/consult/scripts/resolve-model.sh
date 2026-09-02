#!/bin/sh
# resolve-model.sh <role> — map a stable ROLE name to the CURRENT slug from
# the live catalog, so routing.md never has to name a model version.
# Roles are family+tier; the newest version that matches wins.
# Exit 1 (empty output) when no slug matches — callers must treat that as
# "lane unavailable", never guess.
exec </dev/null
role=${1:?usage: resolve-model.sh <role>}
case "$role" in
  # Google via agy: slug shape gemini-<ver>-<tier>-<effort>
  gemini-mechanical) cli=agy;   pat='^gemini-[0-9.]+-flash-medium$' ;;
  gemini-routine)    cli=agy;   pat='^gemini-[0-9.]+-flash-high$' ;;
  gemini-reasoning)  cli=agy;   pat='^gemini-[0-9.]+-pro-high$' ;;
  # OpenAI via codex: slug shape gpt-<ver>-<tier>
  codex-deep|codex-review|codex-hard) cli=codex; pat='^gpt-[0-9.]+-sol$' ;;
  codex-routine|codex-value)          cli=codex; pat='^gpt-[0-9.]+-terra$' ;;
  codex-mechanical)                   cli=codex; pat='^gpt-[0-9.]+-luna$' ;;
  # xAI via grok: slug shape grok-<ver>
  grok-code)         cli=grok;  pat='^grok-[0-9.]+$' ;;
  # Anthropic via claude: aliases are already version-stable
  claude-deep)      echo fable;  exit 0 ;;
  claude-hard)      echo opus;   exit 0 ;;
  claude-routine)   echo sonnet; exit 0 ;;
  *) echo "unknown role: $role" >&2; exit 2 ;;
esac
case "$cli" in
  agy)   slugs=$(agy models 2>/dev/null | awk 'NF && $1 !~ /^Fetching/ {print $1}') ;;
  codex) slugs=$(codex debug models 2>/dev/null | grep -o '"slug":"[^"]*"' | sed 's/"slug":"//;s/"$//') ;;
  grok)  slugs=$(grok models 2>/dev/null | awk '/^ *[*-] grok-/ {print $2}') ;;
esac
printf '%s\n' "$slugs" | grep -E "$pat" | python3 -c '
import re,sys
c=[l.strip() for l in sys.stdin if l.strip()]
def ver(s):
    m=re.search(r"-([0-9]+(?:\.[0-9]+)*)(?:-|$)",s); return tuple(int(x) for x in m.group(1).split("."))
c.sort(key=ver,reverse=True)
print(c[0]) if c else sys.exit(1)'
