#!/bin/sh
# smoke-write.sh [lane ...] — write-mode check: each lane gets its own copy of the fixture as a git repo and must fix calc.py. PASS = file now adds.
HERE=$(cd "$(dirname "$0")" && pwd); D=$HERE/..; R=$HOME/.cache/delegate/smoke-write-$$; mkdir -p "$R"   # under HOME: agy writes only inside its trusted workspaces
lanes=${*:-$(grep -v '^#' "$D/lanes.tsv" | awk -F'\t' '$4 ~ /impl/ {print $1}')}
for l in $lanes; do
  W=$R/wt-$l; mkdir -p "$W"; cp "$HERE/fixture/calc.py" "$W/"; (cd "$W" && git init -q && git add -A && git -c user.email=t@t -c user.name=t commit -qm fixture)
  ( sh "$D/dispatch.sh" "$l" "$HERE/fixture/brief-write.md" "$R/$l.json" --write "$W" --effort low > "$R/$l.line" 2>&1 ) &
done; wait
for l in $lanes; do
  if grep -q 'return a + b' "$R/wt-$l/calc.py"; then v=PASS; else v=FAIL; fi
  st=$(python3 -c "import json,sys; o=json.load(open(sys.argv[1])); print(o.get('status'), o.get('changed_files'))" "$R/$l.json" 2>/dev/null || echo "no-out")
  printf '%-4s %-16s status=%s | %s\n' "$v" "$l" "$st" "$(cut -c1-60 "$R/$l.line")"
done
echo "results in $R"
