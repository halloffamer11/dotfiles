#!/usr/bin/env python3
"""Sample-level fidelity fingerprint for record-meeting audio (needs numpy).

Feed it raw PCM or any file ffmpeg can decode. It flags discontinuity spikes —
the signature of dropped/stitched buffers (crackle, "record player" popping).
Only rigorous when the recording contains a steady tone (e.g. play a 440 Hz
sine during a test recording); on speech/music, treat spike counts as relative.

Usage:
  python3 fidelity.py <file> [s16|f32]     raw PCM (48k mono assumed)
  python3 fidelity.py <file.m4a>           decoded via ffmpeg first

History: this analysis exonerated audiotee (0 spikes) and convicted ffmpeg's
avfoundation mic input (221 spikes at 512-sample spacing, 75% buffer loss) —
the reason the mic leg is mictee. Re-run after macOS/audiotee/mictee upgrades.
"""
import subprocess, sys, tempfile
import numpy as np

RATE = 48000

def load(path, fmt):
    if path.endswith((".m4a", ".wav", ".mp3", ".aac", ".flac")):
        tmp = tempfile.NamedTemporaryFile(suffix=".raw", delete=False)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-i", path, "-f", "s16le", "-ar", str(RATE), "-ac", "1", tmp.name],
                       check=True)
        return np.fromfile(tmp.name, dtype=np.int16).astype(np.float64)
    dtype = np.float32 if fmt == "f32" else np.int16
    x = np.fromfile(path, dtype=dtype).astype(np.float64)
    return x * 32767.0 if fmt == "f32" else x

def main():
    path = sys.argv[1]
    fmt = sys.argv[2] if len(sys.argv) > 2 else "s16"
    x = load(path, fmt)
    print(f"samples={len(x)} ({len(x)/RATE:.2f}s)")
    nz = np.where(np.abs(x) > 200)[0]
    if len(nz) < RATE // 2:
        print("mostly silence — play audio during the test recording")
        return 1
    x = x[nz[0]:nz[-1]]
    amp = np.percentile(np.abs(x), 99)
    d = np.abs(np.diff(x))
    # 2.5x the max slope of a 440 Hz sine at this rate; clusters within 100 samples merge
    spikes = np.where(d > amp * 0.058 * 2.5)[0]
    events = []
    for s in spikes:
        if not events or s - events[-1] > 100:
            events.append(s)
    rate_s = len(events) / (len(x) / RATE)
    print(f"active={len(x)/RATE:.2f}s amp~{amp:.0f} spike-events={len(events)} ({rate_s:.1f}/s)")
    if len(events) > 2:
        gaps = np.diff(events)
        print(f"spacing: median={np.median(gaps):.0f} samples "
              f"({np.median(gaps)/RATE*1000:.0f}ms) — regular spacing = buffer-boundary drops")
    print("verdict:", "CLEAN (<0.5/s)" if rate_s < 0.5 else "SUSPECT — investigate legs separately")
    return 0 if rate_s < 0.5 else 1

if __name__ == "__main__":
    sys.exit(main())
