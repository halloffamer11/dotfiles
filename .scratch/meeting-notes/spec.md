# Meeting notes pipeline

Phase 2 of the meeting recorder. Phase 1 (⌥⌘R → `bin/record-meeting`) is built.
Scope (narrowed 2026-10-06): replicate VoiceInk's drag-and-drop file transcription
for a meeting recording, on the machine and offline, and nothing more. The model
and the text handling follow VoiceInk's own settings. VoiceInk's optional AI
enhancement is mirrored only when it uses its Local CLI provider.

**Status:** spec accepted 2026-10-05, revised after an independent review
(`research/2026-10-05-review.md`), Phase A probe passed
(`research/2026-10-05-phase-a-probe.md`), recorder (Phase B) merged, scope narrowed
2026-10-06 (no calendar matching, no notes stage of our own).

## Goals

- Local-only, enforced at runtime, not only by intent.
- Reuse the speech models VoiceInk already downloaded when the SDK can load them as
  they are; never silently download a second copy.
- Small stages with versioned file contracts, safe to rerun.
- Nothing site-specific in the repo. Folders, model override and retention are
  machine-local settings.

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
- A dropped file (AudioImport, AudioFileTranscriptionService): the active mode's
  model transcribes it; then TranscriptionOutputFilter (tag blocks, bracketed text,
  filler words), paragraphs when the mode has text formatting on, the user's word
  replacements, and the mode's AI enhancement if on. The model is the mode's
  `selectedTranscriptionModelName` (else `CurrentTranscriptionModel`); Parakeet
  Unified runs through FluidAudio's `UnifiedAsrManager`.
- Enhancement providers include cloud APIs, Ollama, VoiceInk Refine (a local model
  that only the app can call, through its XPC service) and Local CLI
  (`/bin/zsh -lc <template>` with `VOICEINK_SYSTEM_PROMPT`, `VOICEINK_USER_PROMPT`
  and `VOICEINK_FULL_PROMPT`).

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
  └─ transcribe → transcript.json + transcript.md    (VoiceInk's model, offline, per channel)
  └─ enhance    → enhanced.md                        (optional: VoiceInk's Local CLI setting)
```

- The only model work in scope is the speech stack producing the transcript.
  There is no language model of our own.
- Model: VoiceInk's selected model (or `[transcribe] model` in config). Supported
  offline here: Parakeet Unified, Parakeet TDT v2 and v3 (FluidAudio), and Apple
  Speech (on-device, only with its assets already installed). Whisper needs a
  whisper.cpp binary, which is not installed, so it is not supported yet. A cloud
  model, an unsupported one, or one whose files do not load falls back in a fixed
  order (Unified, v2, v3, Apple Speech); transcript.json records what was asked
  for, what was used, and why.
- Text, as VoiceInk does for a file: its output filter with its filler words, and
  paragraphs when its mode has text formatting on. Not mirrored: word
  replacements and custom vocabulary (in VoiceInk's own database) and its VAD
  option.
- Channels: mic and system are transcribed apart (free from the recorder). Speaker
  diarization is off by default, as in VoiceInk (`[transcribe] diarize = true`).
- Enhancement (off unless `[enhance] enabled = true`): runs only when VoiceInk's
  mode has enhancement on with the Local CLI provider and a command template, with
  VoiceInk's exact contract. Its system template is read from the installed app at
  run time, not copied into this repo. Otherwise it is skipped with the reason.
- Transcription: a thin adapter, `meeting-asr` (SwiftPM package, `make
  meeting-notes`), over FluidAudio and Apple's Speech framework. `fluidaudiocli` is
  not used: its `process` command has no offline switch, and its load path deletes
  and re-downloads the diarizer cache after a failed load.

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
time overlap.

## File contracts

- `recording.json`: format version, stable recording ID, requested and actual
  capture times, channel roles, per-leg health, state; `pipeline` (state, failure
  reason, what enhancement did) is added by the pipeline.
- `transcript.json`: format version; recorded times; the model asked for and used
  (with the ones skipped and why), engine and language; per channel its role,
  duration, raw and filtered text; segments with start, end, source, speaker, raw
  text, filtered text and word timings; fingerprints of the audio, model and SDK.
- `transcript.md`: a short header (recording, times, model, channel roles), then
  the segments in time order, one paragraph each: `**[mm:ss] Speaker:** text`.
- `enhanced.md`: the Local CLI tool's answer, with a header naming the template,
  prompt and transcript fingerprint.
- Writes are atomic (temp file + rename); one lock per recording; a step reruns
  only when its input fingerprints change; a file the user edited by hand is never
  overwritten (it keeps a hash of what was generated).

## Trigger and states

Hammerspoon starts the pipeline from `onExit` of a successful recording, after
`recording.json` validates, not at the stop key. The queue is files on disk, so a
reload loses nothing and a recording runs once. States: recorded, partial (capture),
then processing, transcribed, enhanced or failed; the menubar shows them. Off until
`[run] auto_run = true`.

## Long meetings

Parakeet transcribes long files in windows (TDT and Unified both chunk). With
diarize on, use the disk-backed diarizer and cap memory. Test with multi-hour
audio and window seams before the trigger is enabled.

## Privacy, enforced

- The local-only rule covers transcription: every `meeting-asr` call runs in a
  no-network sandbox, and the speech models load from disk only.
- Enhancement runs the user's own Local CLI tool with normal network access.
  Turning it on (`[enhance] enabled = true`) is the decision to send the transcript
  to it; a machine deployment that must keep transcripts local leaves it off.
- SDK telemetry and any cloud fallback in the speech stack are off.
- Recording folders are mode 700; no transcript text in logs; the output folder
  must not be a synced folder (checked by `doctor`).
- An egress test runs the pipeline with the network fully blocked.
- Recordings, transcripts, logs and models never enter a repo checkout. Tests use
  synthetic fixtures only.

## Machine-local settings

`~/.config/meeting-notes/config.toml` (never committed): model override, diarize,
enhancement on/off and timeout, output folder, auto_run. Everything else comes from
VoiceInk's settings.
`tools/meeting-notes/config.example.toml` lists every key.

## Build order

A. Provisioning probe: pin FluidAudio, load v2 offline from the VoiceInk cache (or
   provision), diarizer provisioned, `doctor`.
B. Recorder: channel contract, sync, health, `recording.json`.
C. `transcribe` adapter and file contracts, tested on synthetic two-channel audio.
D. VoiceInk's model and text handling, optional Local CLI enhancement, `run` and
   `queue`.
E. Trigger, states, long-meeting and egress tests; then enable.

## Open questions

- Whether to support Whisper (needs a whisper.cpp binary) and VoiceInk's other
  local engines (Nemotron, Cohere, SenseVoice, transcribe.cpp).
- Maximum meeting length and retention period.

## Out of scope

- Live transcription during the meeting.
- Any cloud transcription, any language model of our own, calendar matching and
  notes writing.
