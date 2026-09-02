
# --- Completion & history (previously provided by Oh My Zsh) ---
fpath=(~/.grok/completions/zsh $fpath)   # grok CLI completions; must precede compinit
autoload -Uz compinit && compinit
HISTFILE="$HOME/.zsh_history"
HISTSIZE=50000
SAVEHIST=50000
setopt share_history hist_ignore_all_dups hist_reduce_blanks

# --- Plugins (brew-installed, sourced directly) ---
source "$(brew --prefix)/share/zsh-autosuggestions/zsh-autosuggestions.zsh"
source "$(brew --prefix)/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh"

# --- Environment ---
export EDITOR="nvim"
export VISUAL="nvim"
export PATH="$HOME/.local/bin:$PATH"
export PATH="$HOME/.grok/bin:$PATH"     # grok CLI (delegate skill lane)

# --- Prompt (Starship) ---
eval "$(starship init zsh)"

# --- Aliases ---
# eza: ls carries the shared flags; ll/la/lt build on it via alias expansion.
# No theme.yml on purpose — default ANSI colors inherit the Ghostty palette.
alias ls='eza --group-directories-first --icons=auto'
alias ll='ls -l --git'
alias la='ls -la --git'
alias lt='ls --tree --level=2'
alias pip='python3 -m pip'
# alias dots='git -C ~/dotfiles pull --rebase && stow -d ~/dotfiles/stow -t ~ --restow */ 2>/dev/null; git -C ~/dotfiles status --short'
alias dots='git -C ~/dotfiles pull --rebase && make -C ~/dotfiles configs; git -C ~/dotfiles status --short'

# --- Yazi: 'y' to launch, q=cd into dir, Q=stay ---
function y() {
	local tmp="$(mktemp -t "yazi-cwd.XXXXXX")" cwd
	command yazi "$@" --cwd-file="$tmp"
	IFS= read -r -d '' cwd < "$tmp"
	[ "$cwd" != "$PWD" ] && [ -d "$cwd" ] && builtin cd -- "$cwd"
	rm -f -- "$tmp"
}

# --- Tool integrations ---
source <(fzf --zsh)
eval "$(zoxide init zsh)"

# --- WezTerm shell integration (OSC 7 cwd + OSC 133 prompt zones) ---
# Must come after starship init: both register precmd hooks, and this one
# needs to run last so it wraps the prompt starship just generated.
# Guarded: silently a no-op on machines without the file (e.g. work laptop).
if [ -f "$HOME/.config/wezterm/shell-integration.sh" ]; then
  source "$HOME/.config/wezterm/shell-integration.sh"
fi

# --- Per-machine overrides (never committed) ---
if [ -f "$HOME/.zshrc.local" ]; then
	source "$HOME/.zshrc.local"
fi
