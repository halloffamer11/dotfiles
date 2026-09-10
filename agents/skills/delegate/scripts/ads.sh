#!/bin/sh
set -eu

# Pinned to our fork, not upstream. Upstream's grok relay pairs its read-only
# sandbox with `--permission-mode plan`, which gates every tool call in a
# headless pipe, so a --read-only grok run returns no work at all. The fix is on
# the fork's fix/grok-read-only-plan-mode branch. When it lands upstream, point
# ADS_REPO back at amElnagdy and pin the merge commit.
ADS_REPO=https://github.com/halloffamer11/delegate-skills.git
ADS_COMMIT=f14dc1eeb27ae8c6282830566950f832ce366d02
ADS_DIR=${ADS_DIR:-$HOME/.local/share/delegate/ads}

HARNESSES="claude codex agy grok"

case "${1:-}" in
  install)
    if [ ! -d "$ADS_DIR" ]; then
      mkdir -p "$(dirname "$ADS_DIR")"
      git clone "$ADS_REPO" "$ADS_DIR"
    else
      git -C "$ADS_DIR" fetch "$ADS_REPO"
    fi
    git -C "$ADS_DIR" checkout --detach "$ADS_COMMIT"
    short_sha=$(git -C "$ADS_DIR" rev-parse --short HEAD 2>/dev/null || printf "%.7s" "$ADS_COMMIT")
    echo "ads: $ADS_DIR at $short_sha"
    ;;
  check)
    if [ ! -d "$ADS_DIR" ]; then
      echo "ads: directory $ADS_DIR does not exist; run ads.sh install" >&2
      exit 1
    fi
    sha=$(git -C "$ADS_DIR" rev-parse HEAD 2>/dev/null || true)
    if [ "$sha" != "$ADS_COMMIT" ]; then
      echo "ads: commit mismatch (expected $ADS_COMMIT, got $sha); run ads.sh install" >&2
      exit 1
    fi
    for h in $HARNESSES; do
      relay="$ADS_DIR/skills/$h-delegate/scripts/relay.mjs"
      if [ ! -f "$relay" ]; then
        echo "ads: missing relay for $h at $relay; run ads.sh install" >&2
        exit 1
      fi
    done
    short_sha=$(git -C "$ADS_DIR" rev-parse --short HEAD 2>/dev/null || printf "%.7s" "$ADS_COMMIT")
    echo "ads: $ADS_DIR at $short_sha"
    ;;
  path)
    harness="${2:-}"
    if [ -z "$harness" ]; then
      echo "usage: ads.sh path <harness>" >&2
      exit 2
    fi
    echo "$ADS_DIR/skills/$harness-delegate/scripts/relay.mjs"
    ;;
  *)
    echo "usage: ads.sh install | check | path <harness>" >&2
    exit 2
    ;;
esac
