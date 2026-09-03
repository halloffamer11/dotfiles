#!/bin/sh
# smoke.sh [lane ...]  — run every lane (or the named ones) on the fixture, in parallel; PASS = status done and evidence line 2.
HERE=$(cd "$(dirname "$0")" && pwd); D=$HERE/..; R=$(mktemp -d -t smoke)
lanes=${*:-$(grep -v '^#' "$D/lanes.tsv" | cut -f1)}
for l in $lanes; do ( sh "$D/dispatch.sh" "$l" "$HERE/fixture/brief.md" "$R/$l.json" --cwd "$HERE/fixture" --effort low > "$R/$l.line" 2>&1 ) & done; wait
for l in $lanes; do
  v=$(python3 -c "import json,sys
try: o=json.load(open(sys.argv[1])); ok=o.get('status')=='done' and any(e.get('line')==2 for e in o.get('evidence',[]))
except Exception: ok=False
print('PASS' if ok else 'FAIL')" "$R/$l.json" 2>/dev/null || echo FAIL)
  printf '%-4s %s\n' "$v" "$(cat "$R/$l.line")"
done
echo "results in $R"
