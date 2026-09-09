#!/usr/bin/env bash
# Claude Code status line. Reads the status JSON on stdin.
# Colours come from the active Omarchy theme (colors.toml).
# Usage in settings.json:  "command": "~/.claude/statusline.sh <style>"
#   styles: chev  (two lines, sections split by )   [default]
#           bar   (two lines, sections split by ┃)
#           one   (single dense line)
set -u
# Portable: bash 3.2 (stock macOS) and BSD/GNU userland. Needs jq on PATH.
style="${1:-chev}"

input=$(cat)
now=$(date +%s)

# ---------- colours from Omarchy ----------
# Omarchy publishes the live theme here; elsewhere (macOS) point
# CLAUDE_STATUSLINE_THEME at any colors.toml, or fall through to the defaults
# below -- the Omarchy palette frozen, so both machines look alike.
theme="${CLAUDE_STATUSLINE_THEME:-$HOME/.local/state/omarchy/current/theme/colors.toml}"
fallback() { # fallback <key> -> hex
  case $1 in
    accent)          echo d97757 ;;
    foreground)      echo e7e7e7 ;;
    dark_foreground) echo 8d8d89 ;;
    red)             echo d76563 ;;
    yellow)          echo c68f32 ;;
    orange)          echo d97757 ;;
    green)           echo 78bd74 ;;
    cyan)            echo 1fb5bc ;;
    blue)            echo 648ad8 ;;
    magenta)         echo be80ca ;;
  esac
}
col() { # col <key> -> "r;g;b"
  local hex
  hex=$(sed -n "s/^$1[[:space:]]*=[[:space:]]*\"#\([0-9a-fA-F]\{6\}\)\".*/\1/p" "$theme" 2>/dev/null | head -1)
  [[ -n $hex ]] || hex=$(fallback "$1")
  [[ -n $hex ]] || { echo ""; return; }
  printf '%d;%d;%d' 0x${hex:0:2} 0x${hex:2:2} 0x${hex:4:2}
}
fg() { local c; c=$(col "$1"); [[ -n $c ]] && printf '\033[38;2;%sm' "$c"; }
R=$'\033[0m'; B=$'\033[1m'; D=$'\033[2m'
C_ACC=$(fg accent); C_FG=$(fg foreground); C_MUTE=$(fg dark_foreground)
C_RED=$(fg red); C_YEL=$(fg yellow); C_GRN=$(fg green)
C_CYAN=$(fg cyan); C_BLUE=$(fg blue); C_MAG=$(fg magenta); C_ORG=$(fg orange)
case $style in
  bar|one) sep="${C_MUTE} ┃ ${R}" ;;
  *)       sep="${C_MUTE}  ${R}" ;;
esac
isep=" "   # inside a section

# ---------- pull every field in one jq call ----------
command -v jq >/dev/null || { echo "statusline: jq not on PATH"; exit 0; }
IFS=$'\x1f' read -r model ctx_pct ctx_size five_pct five_reset \
  dur_ms cache_warm cache_hit cache_exp effort fast \
  sname agent cwd wt_name ostyle vim <<<"$(jq -r '
  def s(v): if v == null then "" else (v|tostring) end;
  [ s(.model.display_name),
    s(.context_window.used_percentage), s(.context_window.context_window_size),
    s(.rate_limits.five_hour.used_percentage), s(.rate_limits.five_hour.resets_at),
    s(.cost.total_duration_ms),
    s(.prompt_cache.warm), s(if .prompt_cache.hit_ratio == null then null else (.prompt_cache.hit_ratio*100|round) end), s(.prompt_cache.expires_at),
    s(.effort.level), s(.fast_mode),
    s(.session_name), s(.agent.name),
    s(.workspace.current_dir),
    s(.worktree.name // .workspace.git_worktree),
    s(.output_style.name), s(.vim.mode)
  ] | join("\u001f")' <<<"$input")"

# ---------- helpers ----------
pct_col() { # colour a percentage by load
  local p=${1%.*}; p=${p:-0}
  if   (( p >= 80 )); then printf '%s' "$C_RED"
  elif (( p >= 50 )); then printf '%s' "$C_YEL"
  else printf '%s' "$C_GRN"; fi
}
pct() { [[ -n $1 ]] && printf '%s%d%%%s' "$(pct_col "$1")" "${1%.*}" "$R"; }
until_short() { # epoch -> 2h10m / 45m / 3d4h
  local s=$(( $1 - now )); (( s < 0 )) && s=0
  local d=$(( s/86400 )) h=$(( s%86400/3600 )) m=$(( s%3600/60 ))
  if   (( d > 0 )); then printf '%dd%dh' "$d" "$h"
  elif (( h > 0 )); then printf '%dh%02dm' "$h" "$m"
  else printf '%dm' "$m"; fi
}
ctx_col() { # context colour tiers: green <50, yellow <70, orange <85, red
  local p=${1%.*}; p=${p:-0}
  if   (( p >= 85 )); then printf '%s' "$C_RED"
  elif (( p >= 70 )); then printf '%s' "$C_ORG"
  elif (( p >= 50 )); then printf '%s' "$C_YEL"
  else printf '%s' "$C_GRN"; fi
}
ctx_pct() { # ctx_pct <pct> -> bold percentage in the tier colour
  local p=${1%.*}; p=${p:-0}
  printf '%s%s%d%%%s' "$(ctx_col "$p")" "$B" "$p" "$R"
}
dur() { local s=$(( ${1:-0} / 1000 )); (( s >= 3600 )) && printf '%dh%02dm' $((s/3600)) $((s%3600/60)) || printf '%dm' $((s/60)); }

# ---------- git (cached 5s per directory) ----------
git_seg=""
if [[ -n $cwd ]]; then
  # cksum, not md5sum: POSIX everywhere. The timestamp is stored in the file,
  # so there is no `stat` call to differ between GNU and BSD.
  cache="${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}}/claude-sl-$(printf '%s' "$cwd" | cksum | tr -dc '0-9' | cut -c1-16)"
  cached=""; [[ -f $cache ]] && cached=$(<"$cache")
  if [[ -n $cached && $(( now - ${cached%%$'\x1f'*} )) -lt 5 ]]; then
    git_seg=${cached#*$'\x1f'}
  else
    if git -C "$cwd" rev-parse --is-inside-work-tree &>/dev/null; then
      st=$(git -C "$cwd" status --porcelain=v2 --branch 2>/dev/null)
      branch=$(sed -n 's/^# branch.head //p' <<<"$st")
      ab=$(sed -n 's/^# branch.ab +\([0-9]*\) -\([0-9]*\)/\1 \2/p' <<<"$st")
      ahead=${ab%% *}; behind=${ab##* }
      dirty=$(grep -c '^[12u?]' <<<"$st")
      git_seg="${C_CYAN} ${branch}${R}"
      (( dirty > 0 )) && git_seg+="${C_YEL}*${dirty}${R}"
      [[ ${ahead:-0} -gt 0 ]] && git_seg+="${C_GRN}⇡${ahead}${R}"
      [[ ${behind:-0} -gt 0 ]] && git_seg+="${C_RED}⇣${behind}${R}"
    fi
    printf '%s\x1f%s' "$now" "$git_seg" >"$cache"
  fi
fi

# ---------- line one sections ----------
# Emoji are chosen from the always-wide set (U+1F3xx..1F9xx) so they never
# overlap the following text; U+23xx clocks and hourglasses are avoided.
win=""
if [[ -n $ctx_size ]]; then
  if (( ctx_size >= 1000000 )); then win="$(( ctx_size / 1000000 ))M"; else win="$(( ctx_size / 1000 ))k"; fi
fi
# show the window size unless the display name already carries it (e.g. "Opus 1M")
lc() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }   # bash 3.2 has no ${x,,}
[[ -n $win && $model != *"$win"* && $(lc "$model") != *"$(lc "$win")"* ]] && model+=" $win"
S_MODEL="${C_ACC}${B}🤖 ${model}${R}"
[[ -n $effort ]] && S_MODEL+="${isep}${C_MUTE}⚡${effort}${R}"
[[ $fast == true ]] && S_MODEL+="🚀"
S_CTX="🧠 $(ctx_pct "$ctx_pct")"
SEC_MAIN="${S_MODEL}${isep}${S_CTX}"

SEC_USAGE=""; [[ -n $five_pct ]] && SEC_USAGE="🕔 $(pct "$five_pct")${isep}${D}↻$(until_short "$five_reset")${R}"

S_CACHE=""
if [[ $cache_warm == true ]]; then
  S_CACHE="🔥 ${C_GRN}${cache_hit:-?}%${R}"
  [[ -n $cache_exp ]] && S_CACHE+="${isep}${D}$(until_short "$cache_exp")${R}"
elif [[ -n $cache_warm ]]; then
  S_CACHE="🧊 ${C_MUTE}cold${R}"
fi
S_DUR=""; [[ -n $dur_ms ]] && S_DUR="🏃 ${D}$(dur "$dur_ms")${R}"
SEC_CLOCK="${S_CACHE}${S_CACHE:+${S_DUR:+$isep}}${S_DUR}"

# ---------- other segments ----------
S_DIR="📁 ${C_FG}${B}$(basename "${cwd:-?}")${R}"
S_WT=""; [[ -n $wt_name ]] && S_WT="🌳 ${C_GRN}${wt_name}${R}"
S_SESS=""; [[ -n $sname ]] && S_SESS="🔖 ${C_BLUE}${sname}${R}"
S_AGENT=""; [[ -n $agent ]] && S_AGENT="🎭 ${C_MAG}${agent}${R}"
S_HERDR=""
if [[ ${HERDR_ENV:-} == 1 && -n ${HERDR_PANE_ID:-} ]]; then
  S_HERDR="🐑 ${C_CYAN}${HERDR_WORKSPACE_ID:-?}${R}${D}:${R}${C_CYAN}${HERDR_TAB_ID##*:}${R}${D}:${R}${C_CYAN}${HERDR_PANE_ID##*:}${R}"
fi
S_STYLE=""; [[ -n $ostyle && $ostyle != default ]] && S_STYLE="📝 ${ostyle}"
S_VIM=""; [[ -n $vim ]] && S_VIM="${C_YEL}${B}${vim}${R}"

join() { local out="" s; for s in "$@"; do [[ -n $s ]] || continue; out+="${out:+$sep}$s"; done; printf '%s' "$out"; }

LINE1=("$S_DIR" "$git_seg" "$SEC_MAIN" "$SEC_USAGE" "$SEC_CLOCK")
LINE2=("$S_SESS" "$S_WT" "$S_AGENT" "$S_HERDR" "$S_STYLE" "$S_VIM")

case $style in
  one)
    join "${LINE1[@]}" "${LINE2[@]}"; echo ;;
  *)
    join "${LINE1[@]}"; echo
    join "${LINE2[@]}"; echo ;;
esac
