# Phase A probe, 2026-10-05

Question: can a pinned FluidAudio load the Parakeet model VoiceInk already downloaded,
fully offline, and how fast is it?

Answer: yes for v2. FluidAudio v0.17.5 (latest tag) loads
`~/Library/Application Support/FluidAudio/Models/parakeet-tdt-0.6b-v2-coreml` with
`AsrModels.loadLocal`. No fallback to an older release is needed.

## Setup

- Machine deployment: Apple M4 Pro, macOS 27.0.1, Swift 6.4.
- Throwaway SwiftPM probe and `fluidaudiocli`, both from v0.17.5, built outside any repo.
- Two guards on every run: `ModelHub.offlineMode = true` and an OS sandbox that denies
  all network access. Nothing was downloaded.
- Clips: a 2.56 s `say` sentence and a 317 s synthetic meeting (925 words, one TTS voice).

## Results

| Measure | Result |
| --- | --- |
| Offline load from the VoiceInk cache | works |
| Short clip | word-exact, confidence 0.996 |
| 317 s clip WER | 0.0% after numeral and punctuation normalization, confidence 0.983 |
| Speed | 0.92 s for 317 s of audio (about 343x realtime); CLI 347-350x |
| First load per binary | about 14 s (one-time Core ML compile) |
| Warm load | 0.12-0.13 s |
| Peak memory, 317 s clip | 522 MB max RSS, 64 MB footprint (CLI: 524 MB, 71 MB) |

## fluidaudiocli

- `fluidaudiocli transcribe <wav> --local-model-dir <dir> --model-version v2 --output-json <out>`
  runs offline. `--local-model-dir` is the offline path (it calls `loadLocal`); there is
  no separate offline flag. The default model version is v3, so pass v2.
- JSON keys: `audioFile`, `confidence`, `durationSeconds`, `mode`, `modelVersion`,
  `processingTimeSeconds`, `rtfx`, `text`, `wordTimings` (`word`, `startTime`,
  `endTime`, `confidence`).

## Build

- Debug build of FluidAudio plus the probe: 258 s. CLI on top of it: 29 s.
- The release (`-O`) build did not finish in over 20 minutes, twice. A debug build is
  enough: Core ML does the work, and debug already runs above 340x realtime.

## Not covered

- One synthetic voice on clean audio is a best case; real meetings will be worse.
- v3 from the cache (source reading says it lacks `JointDecisionv3.mlmodelc`).
- Diarization (assets not on disk) and two-channel recordings.
