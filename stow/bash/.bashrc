# Omarchy environment (OMARCHY_PATH + PATH), needed even for non-interactive shells
[[ -r /usr/share/omarchy/default/bash/env-bootstrap ]] && source /usr/share/omarchy/default/bash/env-bootstrap

# If not running interactively, don't do anything else (leave this above the rc source)
[[ $- != *i* ]] && return

# All the default Omarchy aliases and functions
# (don't mess with these directly, just overwrite them here!)
source "$OMARCHY_PATH/default/bash/rc"

# ---- Listing ---------------------------------------------------------------
# Omarchy's opinion stands: `ls` is already `eza -lh`, i.e. long-format, and
# nothing here overrides it -- these layer on top via bash alias expansion.
#   ls   -> long                 lsa / la  -> long + hidden
#   ll   -> long + git columns   lt / lta  -> long tree (+ hidden)
alias ll='ls --git'
alias la='lsa'

# ---- Editor ----------------------------------------------------------------
# Omarchy sets EDITOR and SUDO_EDITOR to `omarchy-launch-editor --inline`,
# which resolves to nvim via ~/.local/state/omarchy/defaults/editor.
# It leaves VISUAL unset; mirror EDITOR so tools preferring VISUAL agree.
export VISUAL="$EDITOR"

# ---- Yazi: 'y' to launch, q=cd into dir, Q=stay ----------------------------
y() {
  local tmp cwd
  tmp="$(mktemp "${TMPDIR:-/tmp}/yazi-cwd.XXXXXX")" || return 1
  command yazi "$@" --cwd-file="$tmp"
  IFS= read -r -d '' cwd <"$tmp"
  [ -n "$cwd" ] && [ "$cwd" != "$PWD" ] && [ -d "$cwd" ] && builtin cd -- "$cwd"
  rm -f -- "$tmp"
}

# ---- History ---------------------------------------------------------------
# Approximates zsh's share_history: append this shell's line, reload the file,
# so sibling panes see each other's commands at the next prompt (~7ms at 50k).
# starship owns PROMPT_COMMAND; starship_precmd_user_func is its documented
# hook and must hold a FUNCTION NAME, not be a function itself.
HISTSIZE=50000
HISTFILESIZE=50000
HISTCONTROL=ignoreboth:erasedups
_share_history() { history -a; history -c; history -r; }
starship_precmd_user_func=_share_history

# ---- Per-machine overrides (never committed) -------------------------------
[ -f "$HOME/.bashrc.local" ] && source "$HOME/.bashrc.local"
