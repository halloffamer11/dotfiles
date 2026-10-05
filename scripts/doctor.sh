#!/bin/sh
# `make doctor`: what the machine needs, read only. It never writes, links or
# installs; it exits non-zero when any line below says ACTION.
# Inputs (from the Makefile): REPO, PROFILE, PLAN (configs-plan output),
# NEEDS (commands the profile requires), SKILLS (declared skill names),
# DELEGATE_DIR (the delegate checkout), UPSTREAM (checkouts to compare with
# their upstream main: dotfiles, delegate, both or neither).
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
# Home's own top level only (it holds ~/Library on a Mac); the config trees in full.
broken=$( { find "$HOME" -maxdepth 1 -type l 2>/dev/null
            for d in "$HOME/.config" "$HOME/.claude" "$HOME/.agents"; do
              [ -d "$d" ] && find "$d" -maxdepth 4 -type l 2>/dev/null; done; } | while read -r l; do
    case "$(readlink "$l")" in (*"$REPO"/*|*dotfiles/*) [ -e "$l" ] || echo "$l";; esac
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

# The rest of a deployment, which make apply does not finish on its own.
if command -v gitleaks >/dev/null 2>&1; then
  say "gitleaks: present"
elif [ "$PROFILE" = macos ]; then
  act "gitleaks is missing, so commits go unscanned: make brew"
else
  act "gitleaks is missing, so commits go unscanned: install it with your distribution's package manager"
fi

[ -f "$HOME/.gitconfig.local" ] && say "machine git settings: ~/.gitconfig.local" \
  || say "machine git settings: none (~/.gitconfig.local absent; git uses the repo's identity)"

if [ ! -d "$DELEGATE_DIR/.git" ]; then
  act "delegate is not checked out at $DELEGATE_DIR: make delegate"
else
  ads="$DELEGATE_DIR/agents/skills/delegate/scripts/ads.sh"
  if out=$(sh "$ads" check 2>&1); then
    say "delegate relays: ${out#ads: }"
  else
    act "delegate relays: ${out#ads: } (sh $ads install)"
  fi
  [ -f "$HOME/.config/delegate/lanes.json" ] && say "delegate catalog: present" \
    || act "no delegate catalog on this machine: make -C $DELEGATE_DIR delegate-wizard"
  if command -v codex >/dev/null 2>&1 && [ ! -e "$HOME/.local/share/delegate/codex-home/auth.json" ]; then
    act "delegate's codex home has no login: codex login, then make -C $DELEGATE_DIR delegate-codex-home"
  fi
fi

# A checkout is behind when its upstream main is a commit it does not have.
# This asks the remote and writes nothing; offline, it says so and moves on.
behind() {  # behind NAME DIR
  [ -d "$2/.git" ] || return 0
  git -C "$2" remote get-url origin >/dev/null 2>&1 || return 0
  remote=$(git -C "$2" ls-remote origin refs/heads/main 2>/dev/null | cut -f1)
  if [ -z "$remote" ]; then
    say "$1: upstream not checked (origin unreachable)"
  elif git -C "$2" merge-base --is-ancestor "$remote" HEAD 2>/dev/null; then
    say "$1: has upstream main"
  else
    act "$1 is behind upstream main: git -C $2 pull (before make apply)"
  fi
}
for r in $UPSTREAM; do
  case "$r" in
    dotfiles) behind dotfiles "$REPO" ;;
    delegate) behind delegate "$DELEGATE_DIR" ;;
  esac
done

[ "$action" -eq 0 ] && say "nothing to do"
exit $action
