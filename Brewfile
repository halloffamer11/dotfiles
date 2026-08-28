# Brewfile — provisioning manifest. `brew bundle` installs what's missing, no-ops what's present.
# Formula names verified against this machine's installs (homebrew-core).
brew "stow"    # symlink manager — everything in Makefile's configs/skills targets depends on it
brew "hunk"    # diff viewer; ships the hunk-review skill (linked by `make skills`)
brew "herdr"   # agent multiplexer; installs its own agent-state hooks on first launch
cask "hammerspoon" # hotkey/menubar orchestrator for the record-meeting rig

# Shell & prompt - .zshrc sources/evals all of these
brew "starship"
brew "zsh-autosuggestions"
brew "zsh-syntax-highlighting"
brew "fzf"
brew "zoxide"
brew "eza"
brew "terminal-notifier"

# Editors & VCS
brew "neovim"
brew "git"
brew "gh"
brew "lazygit"
brew "gitleaks"

# Files & search
brew "yazi"
brew "fd"
brew "ripgrep"

# Yazi preview dependencies (probed at runtime)
brew "ffmpeg"
brew "sevenzip"
brew "poppler"
brew "imagemagick"
brew "resvg"

# Docs & Python tooling 
brew "pandoc"
brew "pipx"

# macOS plumbing
brew "duti"

# Security and Passwords
cask "bitwarden"

# Terminals
cask "wezterm"                          # primary

# Apps
cask "raycast"
cask "helium-browser"
cask "zed@preview"

# Fonts
cask "font-meslo-lg-nerd-font"
cask "font-iosevka-term-nerd-font"
cask "font-jetbrains-mono-nerd-font"
cask "font-zed-mono-nerd-font"
cask "font-fira-code-nerd-font"
cask "font-hack-nerd-font"
cask "font-monaspice-nerd-font"     # GitHub 2024 (Monaspace; NF renames it Monaspice); texture healing; Argon/Neon compact variants
cask "font-0xproto-nerd-font"       # small-size legibility specialist
cask "font-commit-mono-nerd-font"   # neutral, smart kerning
cask "font-maple-mono-nf"           # rounded, compact
cask "font-cascadia-code-nf"        # MS terminal font, native NF glyphs, cursive italic
cask "font-geist-mono-nerd-font"    # Vercel; tight and modern
