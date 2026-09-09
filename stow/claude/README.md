# claude — Claude Code statusline

`stow`ed to `~/.claude/statusline.sh`. Cross-platform: bash 3.2 (stock macOS
bash) and BSD/GNU userland. `jq` is the one hard dependency — it is in the
Brewfile.

Colours come from the live Omarchy theme (`~/.local/state/omarchy/current/
theme/colors.toml`). Off Omarchy that file is absent and the script falls back
to a frozen copy of the same palette, so both machines render alike. Point
`CLAUDE_STATUSLINE_THEME` at another `colors.toml` to override.

## The other half: settings.json

`~/.claude/settings.json` is deliberately NOT stowed — it carries per-machine
hooks, plugins and autoMode rules. Add this block by hand on each machine:

    "statusLine": {
      "type": "command",
      "command": "~/.claude/statusline.sh",
      "padding": 1,
      "refreshInterval": 30
    }

The command takes an optional style argument: `chev` (default, two lines split
by a chevron), `bar` (two lines, `┃`), `one` (single dense line).

## Layout

    line 1   folder · git branch · model+effort+context · 5h usage · cache+duration
    line 2   session · worktree · agent · herdr pane · output style · vim mode

Empty segments drop out, so line 2 disappears entirely in a plain session.
Glyphs are nerd-font — the Brewfile's nerd fonts cover them.
