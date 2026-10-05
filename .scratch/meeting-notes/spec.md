# Meeting notes pipeline

Phase 2 of the meeting recorder. Phase 1 (⌥⌘R → `bin/record-meeting` → m4a + JSON
sidecar in `~/Recordings`) is built. This effort turns a recording into a transcript
and notes on the machine. No audio, transcript or notes leave it.

**Status:** spec accepted by the user 2026-10-05, revised the same day after an
independent review (`research/2026-10-05-review.md`). Next: the provisioning probe
(Phase A) before any pipeline code.

## Goals

- Local-only, enforced at runtime, not only by intent.
- Reuse the speech models VoiceInk already downloaded when the SDK can load them as
  they are; never silently download a second copy.
- Small stages with versioned file contracts, safe to rerun.
- Nothing site-specific in the repo. Folders, calendar source, notes model and
  retention are machine-local settings.

## What VoiceInk does (source, 2026-10-05)

- Local engines: FluidAudio (Parakeet TDT 0.6b v2 English and v3 multilingual, Core
  ML), whisper.cpp, and transcribe.cpp (GGUF). VoiceInk tracks FluidAudio `main`
  (its `Package.resolved` pins a revision on `main`, not a release).
- Parakeet weights live in FluidAudio's shared cache,
  `~/Library/Application Support/FluidAudio/Models/<model repo>/`. VoiceInk is not
  sandboxed, so this is the real path.
- On one machine deployment the cache holds `parakeet-tdt-0.6b-v2-coreml`,
  `parakeet-tdt-0.6b-v3-coreml` (without `JointDecisionv3.mlmodelc`, which current
  FluidAudio `main` needs for v3), `parakeet-unified-en-0.6b`, and Silero VAD.
  There are no diarizer models.
- Whisper models live in `~/Library/Application Support/com.prakashjoshipax.VoiceInk/WhisperModels/`.
- VoiceInk has no CLI, URL scheme, watch folder or API for files, so it cannot be a
  stage. Its "clean output" is a regex filler-word filter, not AI.

## Model provisioning (Phase A, before pipeline code)

Cache reuse depends on the FluidAudio version: newer loaders expect different folder
names (`-coreml` stripped) and different v3 files than the installed cache has.

1. Pin one FluidAudio release and one model variant (default: v2 English) in the
   repo. Record the toolchain version.
2. Load models with `AsrModels.loadLocal` from an explicit directory and the SDK's
   offline guard on. A missing or mismatched file is an error; there is no network
   fallback at run time.
3. `meeting-notes provision` is the only step that may download. It checks the
   VoiceInk cache first, verifies it against the pinned loader, and otherwise
   downloads the pinned model and the diarizer bundle
   (`FluidInference/speaker-diarization-coreml`) once, with the user present.
4. `meeting-notes doctor` (read-only) reports which models load offline.

## Pipeline

```
~/Recordings/<id>/recording.json + master.caf (+ listen.m4a)
  └─ transcribe    → transcript.json   (FluidAudio, offline, per channel)
  └─ match-meeting → meeting.json      (calendar, read-only, optional)
  └─ make-notes    → notes.md          (local LLM, off until configured)
```

- Start from FluidAudio's own `fluidaudiocli transcribe` and `process --mode
  offline`. Write only a thin adapter for what they lack: offline loading,
  per-channel processing and the stable JSON below. The adapter is a SwiftPM
  package built by `make meeting-notes`; the `mictee` single-file `swiftc` pattern
  cannot build a package with dependencies.
- Alternatives if FluidAudio fails Phase A: WhisperKit or whisper.cpp (own weights
  plus a separate diarizer), sherpa-onnx (more integration work), pyannote
  (accuracy reference, needs Python).

### Recorder changes

- **Channel contract.** A lossless master (`master.caf`, 48 kHz float): channel 0 =
  mic, channel 1 = system. A missing leg is padded with silence and marked. The
  listening mix (`listen.m4a`) is a derived file. Old mono recordings are marked
  `layout: legacy-mono` and are diarized as one channel.
- **Synchronization.** Two processes start the legs, so equal sample rates do not
  mean equal timelines. Each leg logs its start against one monotonic clock, its
  sample count and any discontinuities (mictee restarts after a device change).
  The mux aligns the start offset, keeps gaps as silence and corrects drift.
- **Health.** Per leg: exit status, duration, gaps. Validate before deleting raw
  legs; keep diagnostics on failure. A one-leg salvage is a `partial` recording,
  not a success.

### Speaker attribution

`source` (mic or system) is stored apart from `speaker`. The mic can hear other
people in the room and leakage from speakers, so "mic = the user" is an assumption
shown as such, never a fact. Duplicate speech heard on both channels is merged by
time overlap. Calendar invitees are context for the notes, never speaker names.

## File contracts

- `recording.json`: format version, stable recording ID, requested and actual
  capture times, channel roles, per-leg health, state.
- `transcript.json`: format version; segments with start, end, source, speaker,
  raw text; a derived view with filler words removed; fingerprints of input audio,
  model and SDK version.
- `meeting.json`: matched event or `unmatched`. Ties and ambiguity stay unmatched.
- `notes.md`: the notes, with a header naming the transcript fingerprint, model and
  prompt version.
- Writes are atomic (temp file + rename); one lock per recording; a stage reruns
  only when its input fingerprints change; a file the user edited by hand is never
  overwritten (it keeps a hash of what was generated).

## Trigger and states

Hammerspoon starts the pipeline from `onExit` of a successful recording, after
`recording.json` validates, not at the stop key. The queue is files on disk, so a
reload loses nothing and a recording runs once. States: recorded, processing,
partial, failed, notes-ready; the menubar shows them.

## Long meetings

Use the disk-backed diarizer, cap memory, checkpoint per chunk, and summarize in
chunks without truncation. Test with multi-hour audio and window seams before the
trigger is enabled.

## Privacy, enforced

- The notes stage is off until a local model is configured. Only loopback
  endpoints are accepted; redirects and remote hosts are refused.
- SDK telemetry and any cloud fallback are off.
- Recording folders are mode 700; no transcript text in logs; the output folder
  must not be a synced folder (checked by `doctor`).
- An egress test runs the whole pipeline with the network blocked.
- Recordings, transcripts, logs and models never enter a repo checkout. Tests use
  synthetic fixtures only.

## Machine-local settings

`~/.config/meeting-notes/config.toml` (never committed): model variant, model
directory, notes endpoint and model, calendar source, output folder, retention.

## Build order

A. Provisioning probe: pin FluidAudio, load v2 offline from the VoiceInk cache (or
   provision), diarizer provisioned, `doctor`.
B. Recorder: channel contract, sync, health, `recording.json`.
C. `transcribe` adapter and file contracts, tested on synthetic two-channel audio.
D. `match-meeting`, `make-notes` behind the local-only checks.
E. Trigger, states, long-meeting and egress tests; then enable.

## Open questions

- Local notes model and server (default: Ollama on the same machine).
- Maximum meeting length and retention period.

## Out of scope

- Live transcription during the meeting.
- Any cloud transcription or cloud notes model.
