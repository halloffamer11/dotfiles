-- Reload config automatically whenever a file in ~/.hammerspoon changes
hs.pathwatcher.new(os.getenv("HOME") .. "/.hammerspoon/", hs.reload):start()
hs.alert.show("Hammerspoon config loaded")

-- ⌥⌘R — record-meeting toggle (placeholder until the rig lands)
hs.hotkey.bind({ "cmd", "alt" }, "r", function()
	hs.alert.show("⌥⌘R works — rig not wired yet")
end)
