# Meeting notes pipeline

Phase 2 of the meeting recorder. Phase 1 (⌥⌘R → `bin/record-meeting` → m4a + JSON
sidecar in `~/Recordings`) is built. This effort turns a recording into a transcript
and notes, on the machine, with no audio or transcript leaving it.

**Status:** draft. The design below is the one approved 2026-08-04 (toolsmith
`topics/recording-rig.md`), updated with what VoiceInk's source shows on 2026-10-05.

## Goals

- Transcription is local-only. No cloud speech API, ever.
- Reuse the speech models VoiceInk already downloaded. No second copy of the weights.
- Every stage is a small command with one input and one output, so a stage can be
  rerun or swapped without the others.
- Nothing site-specific in the repo. Output folders, calendar source and the notes
  model are machine-local settings.

## What VoiceInk does (source, 2026-10-05)

- Local engines: FluidAudio (Parakeet TDT 0.6b v2 English and v3 multilingual,
  Core ML on the Apple Neural Engine), whisper.cpp, and transcribe.cpp (GGUF).
- Parakeet weights live in FluidAudio's shared cache,
  `~/Library/Application Support/FluidAudio/Models/<model repo>/`
  (`AsrModels.defaultCacheDirectory(for:)`). VoiceInk is not sandboxed, so this is
  the real path, not a container path. Any FluidAudio program on the same account
  loads the same files.
- Whisper models live in `~/Library/Application Support/com.prakashjoshipax.VoiceInk/WhisperModels/`.
- VoiceInk has no CLI, URL scheme, watch folder or API for files. `open -a VoiceInk
  file.m4a` queues a file, but a person must press Start. So VoiceInk itself cannot
  be a pipeline stage; its models can.
- Its "clean output" is a regex filler-word filter (`FillerWordManager`), not AI.

## Pipeline

```
~/Recordings/meeting-*.m4a + .json
  └─ transcribe   → meeting-*.transcript.json   (FluidAudio Parakeet, local)
  └─ match-meeting → adds title and attendees    (calendar, read-only, optional)
  └─ make-notes   → meeting-*.notes.md           (local LLM)
```

1. `transcribe <audio>`: a small Swift CLI on the FluidAudio package (same pattern
   as `tools/mictee`, built by `make transcribe` into `~/.local/bin`). Loads the
   Parakeet model from the shared cache, with `--offline` failing loud if the model
   is missing instead of downloading. Runs FluidAudio's offline diarizer for speaker
   turns. Output: JSON with segments (start, end, speaker, text) and a plain-text
   rendering. Applies the same filler-word regex VoiceInk uses.
2. `match-meeting <sidecar>`: matches recording start and end to a calendar event
   to name the meeting and its attendees. Deterministic. The calendar source is a
   machine-local setting; with none set, the stage is skipped.
3. `make-notes <transcript>`: the only LLM stage. Summary, decisions, action items.
   Runs a local model (Ollama or another localhost OpenAI-compatible server), set
   in machine-local config.
4. Trigger: when ⌥⌘R stops a recording, Hammerspoon runs the chain in the
   background and posts a notification when notes are ready.

### Recorder change: keep the legs apart

The recorder mixes mic and system audio into one track and deletes the raw legs.
Keeping the mic on its own channel (stereo m4a: left = mic, right = system, plus the
existing mixed track or a mix made on demand) gives "me versus the room" for free,
before any diarization, and lets the diarizer work only on the system side.

## Machine-local settings

`~/.config/meeting-notes/config.toml` (never committed): model version (v2 or v3,
default = whichever VoiceInk uses on that machine), notes model endpoint, calendar
source, output folder. A site deployment may require a different output folder or
forbid the notes stage; that goes here.

## Open questions for the user

- Which machine runs the notes stage, and with which local model.
- Whether the pipeline stays in dotfiles `tools/` (default) or gets its own repo.

## Out of scope

- Live transcription during the meeting.
- Any cloud transcription or cloud notes model.
