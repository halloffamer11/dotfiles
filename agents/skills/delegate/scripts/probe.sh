#!/bin/sh
# probe.sh — read-only environment sensing for the delegate/council skills.
# Per known agent CLI: presence, version, model catalog. Never invokes a model.
# Absence is data, not an error: always exits 0.
exec </dev/null   # agy/codex block on an open stdin; the skill's own rule applies here too

probe() {
  name=$1 bin=$2 models_cmd=$3
  if command -v "$bin" >/dev/null 2>&1; then
    version=$("$bin" --version 2>/dev/null | head -1)
    printf '## %s: present (%s)\n' "$name" "${version:-version unknown}"
    if [ -n "$models_cmd" ]; then
      $models_cmd 2>/dev/null | sed 's/^/  /'
    fi
  else
    printf '## %s: absent\n' "$name"
  fi
}

# codex's raw catalog is JSON; extract just the slug field so the block
# stays comparable in size to the other CLIs' model lists.
codex_slugs() {
  codex debug models 2>/dev/null | grep -o '"slug":"[^"]*"' | sed 's/"slug":"//;s/"$//'
}

probe codex codex codex_slugs
probe antigravity agy "agy models"
probe claude claude ""
probe grok grok "grok models"
probe kiro kiro-cli "kiro-cli chat --list-models"
if [ "${DELEGATE_BALANCE:-${CONSULT_BALANCE:-0}}" = 1 ]; then   # CONSULT_BALANCE: deprecated alias
  printf "## usage (DELEGATE_BALANCE=1)\n"
  python3 "$(dirname "$0")/usage.py" --pretty 2>/dev/null | sed "s/^/  /" || printf "  usage.py failed — treat all lanes as unknown\n"
fi
exit 0
