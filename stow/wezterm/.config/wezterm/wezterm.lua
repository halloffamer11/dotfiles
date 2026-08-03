-- WezTerm config — primary terminal since 2026-07-27 (Ghostty demoted to
-- fallback, stow/ghostty retained). herdr owns splits/tabs/multiplexing,
-- so no pane keybinds here: WezTerm is just the window — theme, font,
-- translucency, scrollback. Default keybinds still apply (Cmd+W close tab,
-- Cmd+K clear scrollback, Ctrl+Shift+P command palette).

local wezterm = require("wezterm")
local config = wezterm.config_builder()
local act = wezterm.action

-- === Theme ===
-- Verified built-in scheme names — swap the active line, save to live-reload:
--   "rose-pine-moon"               (translucent-friendly, Kun's pick)  [active]
--   "Everforest Dark Hard (Gogh)"  (baseline, matches Ghostty default)
--   "Gruvbox Material (Gogh)"      (current Ghostty test-drive)
--   "Catppuccin Mocha"
config.color_scheme = "rose-pine-moon"
-- config.color_scheme = "Grubbox Material"

-- === Font ===
-- Same options installed as Ghostty: MesloLGS NF / IosevkaTerm / JetBrainsMono / ZedMono
config.font = wezterm.font("MesloLGS NF")
config.font_size = 16.0
config.freetype_load_target = "Light"
config.freetype_load_flags = "NO_HINTING"

-- === Window ===
-- Frosted-glass look: terminal at 85% opacity, macOS blurs the wallpaper
-- behind it. Set opacity = 1.0 / blur = 0 to go solid again.
config.window_background_opacity = 0.85
config.macos_window_background_blur = 50
config.window_decorations = "RESIZE"
config.window_padding = { left = 10, right = 10, top = 10, bottom = 0 }
config.hide_tab_bar_if_only_one_tab = true
config.use_fancy_tab_bar = false
config.inactive_pane_hsb = { saturation = 0.5, brightness = 0.6 }
config.adjust_window_size_when_changing_font_size = false

-- === Performance ===
config.front_end = "WebGpu" -- Metal-native on Apple Silicon
config.webgpu_power_preference = "HighPerformance"
config.max_fps = 120
config.animation_fps = 120

-- === Behavior ===
config.scrollback_lines = 100000
config.term = "xterm-256color"
-- copy-on-select -> clipboard (matches Ghostty copy-on-select = clipboard)
config.mouse_bindings = {
	-- Restores WezTerm's default click-opens-link behavior on top of
	-- copy-on-select (plain CompleteSelection removes the link half).
	{
		event = { Up = { streak = 1, button = "Left" } },
		mods = "NONE",
		action = act.CompleteSelectionOrOpenLinkAtMouseCursor("ClipboardAndPrimarySelection"),
	},
	-- Cmd+click opens links; inside herdr use Cmd+Shift+click (Shift
	-- bypasses herdr's mouse capture, then matches here as CMD).
	{
		event = { Up = { streak = 1, button = "Left" } },
		mods = "SUPER",
		action = act.OpenLinkAtMouseCursor,
	},
}

-- Prompt-jump through scrollback (Shift+Up/Down, needs OSC 133 zones
-- from shell-integration.sh; upstream ships no default binding).
config.keys = {
	{ key = "UpArrow", mods = "SHIFT", action = act.ScrollToPrompt(-1) },
	{ key = "DownArrow", mods = "SHIFT", action = act.ScrollToPrompt(1) },
	-- Forward Cmd bracket chords to herdr as kitty CSI-u sequences.
	-- '[' = codepoint 91, ']' = 93; modifier field = 1 + shift(1)+alt(2)+super(8)
	{ key = "[", mods = "CMD", action = act.SendString("\x1b[91;9u") },
	{ key = "]", mods = "CMD", action = act.SendString("\x1b[93;9u") },
	-- cmd+shift+[ / ] need ALL SIX spellings (debug-log-verified 2026-08-02):
	--   [ +CMD|SHIFT  claims the chord from macOS's native Show Prev/Next Tab
	--                 shortcut at the keyEquivalent stage (without it, WezTerm
	--                 never receives the keypress at all);
	--   { +CMD|SHIFT  is the spelling dispatch actually matches (mapped char,
	--                 shift still in mods);
	--   { +CMD        masks WezTerm's default tab-nav in the shift-consumed slot.
	-- Do not prune any of them without retesting both chords.
	{ key = "[", mods = "CMD|SHIFT", action = act.SendString("\x1b[91;10u") },
	{ key = "]", mods = "CMD|SHIFT", action = act.SendString("\x1b[93;10u") },
	{ key = "{", mods = "CMD|SHIFT", action = act.SendString("\x1b[91;10u") },
	{ key = "{", mods = "CMD", action = act.SendString("\x1b[91;10u") },
	{ key = "}", mods = "CMD|SHIFT", action = act.SendString("\x1b[93;10u") },
	{ key = "}", mods = "CMD", action = act.SendString("\x1b[93;10u") },
	{ key = "[", mods = "CMD|ALT", action = act.SendString("\x1b[91;11u") },
	{ key = "]", mods = "CMD|ALT", action = act.SendString("\x1b[93;11u") },
	{ key = "[", mods = "CTRL|ALT", action = act.SendString("\x1b[91;7u") },
	{ key = "]", mods = "CTRL|ALT", action = act.SendString("\x1b[93;7u") },
}

-- cmd+1..9 → herdr focus_agent, as CSI-u (overrides WezTerm's ActivateTab defaults)
for i = 1, 9 do
	table.insert(config.keys, {
		key = tostring(i),
		mods = "CMD",
		action = act.SendString(string.format("\x1b[%d;9u", 48 + i)),
	})
end

-- Left option is Alt, right option composes (matches macos-option-as-alt = left)
config.send_composed_key_when_left_alt_is_pressed = false
config.send_composed_key_when_right_alt_is_pressed = true

return config
