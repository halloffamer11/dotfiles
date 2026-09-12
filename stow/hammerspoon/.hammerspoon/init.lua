-- Reload config automatically whenever a file in ~/.hammerspoon changes
hs.pathwatcher.new(os.getenv("HOME") .. "/.hammerspoon/", hs.reload):start()

-- record-meeting rig: ⌥⌘R toggles; red menu-bar timer while recording
local recorder = { task = nil, menubar = nil, timer = nil, startedAt = nil }
local SCRIPT = os.getenv("HOME") .. "/.hammerspoon/bin/record-meeting"

local function stopUI()
	if recorder.timer then
		recorder.timer:stop()
		recorder.timer = nil
	end
	if recorder.menubar then
		recorder.menubar:delete()
		recorder.menubar = nil
	end
end

local function updateTitle()
	local secs = math.floor(hs.timer.secondsSinceEpoch() - recorder.startedAt)
	recorder.menubar:setTitle(
		hs.styledtext.new(
			string.format("● %02d:%02d", math.floor(secs / 60), secs % 60),
			{ color = { red = 1, green = 0.2, blue = 0.2 } }
		)
	)
end

local function onExit(exitCode, stdOut, stdErr)
	stopUI()
	recorder.task = nil
	if exitCode == 0 then
		hs.alert.show("Saved: " .. (stdOut or ""):gsub("%s+$", ""))
	else
		hs.alert.show("Recording FAILED — open Hammerspoon console")
		print("record-meeting stderr: " .. (stdErr or ""))
	end
end

local function toggleRecording()
	if recorder.task and recorder.task:isRunning() then
		hs.alert.show("Stopping…")
		recorder.task:interrupt() -- SIGINT; mux runs, then onExit fires
	else
		recorder.task = hs.task.new(SCRIPT, onExit)
		if not recorder.task:start() then
			hs.alert.show("record-meeting failed to start")
			recorder.task = nil
			return
		end
		recorder.startedAt = hs.timer.secondsSinceEpoch()
		recorder.menubar = hs.menubar.new()
		updateTitle()
		recorder.timer = hs.timer.doEvery(1, updateTitle)
		hs.alert.show("● Recording")
	end
end

hs.hotkey.bind({ "cmd", "alt" }, "r", toggleRecording)

-- delegate rows in the Claude Code status line: ⌥⌘D toggles them (ticket 23).
-- Terminal-agnostic on purpose: Ghostty keybinds cannot run a program. The
-- status line follows the flag file at its next refresh, 30 s at most.
local DELEGATE_REPORT = os.getenv("HOME") .. "/.claude/skills/delegate/scripts/report.py"

local function toggleDelegateRows()
	hs.task
		.new("/usr/bin/env", function(exitCode, stdOut, stdErr)
			if exitCode == 0 then
				hs.alert.show((stdOut or ""):gsub("%s+$", ""))
			else
				hs.alert.show("delegate rows toggle FAILED — open Hammerspoon console")
				print("report.py statusline toggle stderr: " .. (stdErr or ""))
			end
		end, { "python3", DELEGATE_REPORT, "statusline", "toggle" })
		:start()
end

hs.hotkey.bind({ "cmd", "alt" }, "d", toggleDelegateRows)
hs.alert.show("Hammerspoon config loaded")
