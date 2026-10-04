#!/bin/sh
# `make doctor`: what the machine needs, read only. It never writes, links or
# installs; it exits non-zero when any line below says ACTION.
# Inputs (from the Makefile): REPO, PROFILE, PLAN (configs-plan output),
# NEEDS (commands the profile requires), SKILLS (declared skill names).
action=0
say() { echo "$*"; }
act() { echo "ACTION: $*"; action=1; }

say "profile: $PROFILE"

missing=""
for c in $NEEDS; do command -v "$c" >/dev/null 2>&1 || missing="$missing $c"; done
[ -z "$missing" ] && say "prerequisites: present ($NEEDS)" || act "missing prerequisites:$missing"

conflicts=$(printf '%s\n' "$PLAN" | grep -E 'CONFLICT|existing target' || true)
if [ -n "$conflicts" ]; then
  act "files in the way of managed links (move them aside, then make apply):"
  printf '%s\n' "$conflicts" | sed 's/^/  /'
else
  say "conflicts: none"
fi
# A restow simulation unlinks and relinks what is already in place, so a link
# is pending only when the plan makes it without first removing it.
pending=$(printf '%s\n' "$PLAN" | awk '/^UNLINK: /{u[$2]=1} /^LINK: /{l[$2]=1} END{n=0; for (p in l) if (!(p in u)) n++; print n}')
[ "$pending" -eq 0 ] || act "$pending managed link(s) not in place yet: make apply"

# A managed link is one that points into this checkout; a dangling one is a
# file the repo no longer has (or moved).
broken=$(for d in "$HOME" "$HOME/.config" "$HOME/.claude" "$HOME/.claude/agents" "$HOME/.claude/skills"; do
  [ -d "$d" ] || continue
  find "$d" -maxdepth 4 -type l 2>/dev/null | while read -r l; do
    case "$(readlink "$l")" in *"$REPO"/*|*dotfiles/*) [ -e "$l" ] || echo "$l";; esac
  done
done | sort -u)
if [ -n "$broken" ]; then
  act "broken links into the repo (make apply removes the stale skill ones; delete the rest):"
  printf '%s\n' "$broken" | sed 's/^/  /'
else
  say "broken managed links: none"
fi

absent=""
for s in $SKILLS; do
  [ -e "$HOME/.agents/skills/$s" ] || [ -e "$HOME/.claude/skills/$s" ] || absent="$absent $s"
done
[ -z "$absent" ] && say "declared skills: installed ($SKILLS); versions are refreshed by make apply" \
  || act "declared skills not installed:$absent (make externals)"

[ "$action" -eq 0 ] && say "nothing to do"
exit $action
