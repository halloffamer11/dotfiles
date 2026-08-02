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
	{
		event = { Up = { streak = 1, button = "Left" } },
		mods = "NONE",
		action = act.CompleteSelection("ClipboardAndPrimarySelection"),
	},
}
-- Left option is Alt, right option composes (matches macos-option-as-alt = left)
config.send_composed_key_when_left_alt_is_pressed = false
config.send_composed_key_when_right_alt_is_pressed = true

return config
