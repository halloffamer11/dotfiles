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

-- meeting-notes pipeline: after a saved recording, `meeting-notes run --if-enabled <dir>`
-- runs in the background. It does nothing (exit 5) unless [run] auto_run = true in
-- ~/.config/meeting-notes/config.toml. At load, `meeting-notes queue --if-enabled` runs
-- once to catch recordings a reload or crash interrupted. Menu bar "✎ notes…" while
-- it works; an alert when notes or a transcript are ready, or when it failed. The
-- notes come from the agent CLI set in [notes] command; without it, a transcript only.
local NOTES = os.getenv("HOME") .. "/.hammerspoon/bin/meeting-notes"
local pipeline = { tasks = {}, menubar = nil }

local function pipelineUI()
	local busy = false
	for t in pairs(pipeline.tasks) do
		busy = busy or t:isRunning()
	end
	if busy and not pipeline.menubar then
		pipeline.menubar = hs.menubar.new()
		pipeline.menubar:setTitle("✎ notes…")
	elseif not busy and pipeline.menubar then
		pipeline.menubar:delete()
		pipeline.menubar = nil
	end
end

local function startPipeline(args, label)
	local task
	task = hs.task.new(NOTES, function(exitCode, stdOut, stdErr)
		pipeline.tasks[task] = nil
		pipelineUI()
		if exitCode == 5 then
			return -- auto_run is off
		end
		local last = (stdOut or ""):gsub("%s+$", ""):match("[^\n]*$") or ""
		if exitCode ~= 0 then
			hs.alert.show("Meeting notes FAILED (" .. label .. ") — open Hammerspoon console")
			print("meeting-notes stderr: " .. (stdErr or ""))
		elseif last:find("notes%-ready") then
			hs.alert.show("Notes ready: " .. label)
		elseif last:find("notes%-unstructured") then
			hs.alert.show("Notes saved, but not in the expected sections: " .. label)
		elseif last:find("transcribed") then
			hs.alert.show("Transcript ready: " .. label)
		elseif last:find("^queue:") and not last:find("^queue: 0 processed") then
			hs.alert.show("Meeting notes " .. last)
		end
	end, args)
	if task:start() then
		pipeline.tasks[task] = true
		hs.timer.doAfter(1, pipelineUI) -- after --if-enabled had its chance to exit
	end
end

local function onExit(exitCode, stdOut, stdErr)
	stopUI()
	recorder.task = nil
	local dir = (stdOut or ""):gsub("%s+$", "")
	if exitCode == 0 or exitCode == 3 then
		if exitCode == 0 then
			hs.alert.show("Saved: " .. dir)
		else -- partial: one leg missing or cut short, see recording.json
			hs.alert.show("Saved PARTIAL (a capture leg is missing): " .. dir)
			print("record-meeting stderr: " .. (stdErr or ""))
		end
		startPipeline({ "run", "--if-enabled", dir }, dir:match("[^/]+$") or dir)
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
startPipeline({ "queue", "--if-enabled" }, "queue")

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
