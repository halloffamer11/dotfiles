#!/usr/bin/env python3
"""Synthetic tests for record-meeting-finalize (stdlib + ffmpeg; no capture devices).

Builds raw legs the way record-meeting leaves them in its temp dir, with a click
at one known instant in each leg, runs finalize, and checks master.caf,
listen.m4a and recording.json:

  1. aligned          mic starts 100 ms after system; clicks coincide in master.caf
  2. mic-gap          mictee logs a gap; the silence keeps the mic click aligned
  3. missing-mic      mic leg empty: partial (exit 3), ch0 silent, full length
  4. truncated-mic    mic ends 5 s early: partial, leg marked truncated
  5. stop-trim        a leg runs past the stop time: master ends at the stop
  6. both-empty       nothing captured: failed (exit 1), recording.json says so

Run:  make test-recorder   (or: python3 tools/record-meeting-tests/finalize_test.py)
"""
import array, json, pathlib, shutil, subprocess, sys, tempfile

HELPER = pathlib.Path(__file__).resolve().parents[2] / "stow/hammerspoon/.hammerspoon/bin/record-meeting-finalize"
RATE = 48000
NS = 1_000_000_000
SYS_FIRST = 5_000 * NS          # system leg's first sample on the shared clock
WORK = pathlib.Path(tempfile.mkdtemp(prefix="rm-finalize."))


def ns(seconds):
    return int(seconds * NS)


def leg(seconds, clicks, typecode):
    """Silence with a full-scale click at each sample index in clicks."""
    a = array.array(typecode, [0]) * int(seconds * RATE)
    for i in clicks:
        a[i] = 32000 if typecode == "h" else 0.9
    return a.tobytes()


def make_case(name, sys_secs=None, mic_secs=None, mic_delay=0.1, click_at=1.0, gaps=()):
    """A temp dir as record-meeting leaves it. click_at is an absolute time on
    the shared timeline (seconds after SYS_FIRST); gaps are (at_sample, samples)."""
    tmp = WORK / name / "tmp"
    tmp.mkdir(parents=True)
    mic_first = SYS_FIRST + ns(mic_delay)
    if sys_secs:
        (tmp / "system.raw").write_bytes(leg(sys_secs, [int(click_at * RATE)], "h"))
        # the watcher saw a first write of 100 ms of audio land 100 ms after it began
        (tmp / "system.first").write_text(f"{SYS_FIRST + ns(0.1)} {int(0.1 * RATE) * 2}\n")
    else:
        (tmp / "system.raw").write_bytes(b"")
    log = ["mictee: capturing: 48000.0 Hz 1 ch -> 48000 Hz mono f32"]
    if mic_secs:
        # where the click lands in the mic file: shared time minus the mic start,
        # minus any samples lost in gaps before it
        idx = int(round((click_at - mic_delay) * RATE)) - sum(s for at, s in gaps if at <= (click_at - mic_delay) * RATE)
        (tmp / "mic.raw").write_bytes(leg(mic_secs, [idx], "f"))
        log.append(f"mictee: first-sample host_ns={mic_first}")
        for at, s in gaps:
            log.append(f"mictee: gap at_sample={at} samples={s} host_ns=0")
        total = int(mic_secs * RATE)
        log.append(f"mictee: last-sample host_ns={mic_first + ns(mic_secs + sum(s for _, s in gaps) / RATE)} samples={total}")
    else:
        (tmp / "mic.raw").write_bytes(b"")
    (tmp / "mictee.log").write_text("\n".join(log) + "\n")
    return tmp


def finalize(tmp, stop_ns=0):
    out = tmp.parent / "out"
    r = subprocess.run([str(HELPER), "finalize", "--tmp", str(tmp), "--out", str(out), "--id", tmp.parent.name,
                        "--start-mono-ns", str(SYS_FIRST - ns(0.5)), "--start-epoch-ns", str(1_760_000_000 * NS),
                        "--spawn-ns", str(SYS_FIRST - ns(0.2)), "--stop-ns", str(stop_ns),
                        "--sys-rc", "0", "--mic-rc", "0"], capture_output=True, text=True)
    meta = json.loads((out / "recording.json").read_text()) if (out / "recording.json").exists() else None
    return r.returncode, out, meta, r.stderr


def channels(caf):
    """master.caf as two float lists (ch0, ch1)."""
    raw = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(caf),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    a = array.array("f")
    a.frombytes(raw)
    return a[0::2], a[1::2]


def peak(x):
    return max(range(len(x)), key=lambda i: abs(x[i])) if len(x) else None


def report(name, checks):
    bad = [k for k, v in checks.items() if not v]
    print(f"[{name}] {'PASS' if not bad else 'FAIL ' + ', '.join(bad)}")
    return not bad


def case_aligned():
    rc, out, meta, err = finalize(make_case("aligned", sys_secs=10, mic_secs=9.9))
    mic, sysc = channels(out / "master.caf")
    return report("aligned", {
        "rc0": rc == 0, "state": meta and meta["state"] == "recorded",
        "click-sys@1.0s": peak(sysc) == RATE, "click-mic@1.0s": abs(peak(mic) - RATE) <= 1,
        "offset": meta and meta["legs"]["mic"]["start_offset_s"] == 0.1,
        "timing": meta and meta["legs"]["mic"]["timing"] == "host-time"
        and meta["legs"]["system"]["timing"] == "first-data-estimate",
        "length": abs(len(sysc) - 10 * RATE) <= 1,
        "listen": (out / "listen.m4a").exists() and (out / "listen.m4a").stat().st_size > 0,
        "json": meta and meta["format_version"] == 1 and meta["channels"] == {"0": "mic", "1": "system"},
        "mode700": oct(out.stat().st_mode & 0o777) == "0o700",
    })


def case_gap():
    gaps = [(int(0.5 * RATE), int(0.25 * RATE))]  # 250 ms lost half a second into the mic leg
    rc, out, meta, err = finalize(make_case("mic-gap", sys_secs=10, mic_secs=9.65, click_at=3.0, gaps=gaps))
    mic, sysc = channels(out / "master.caf")
    return report("mic-gap", {
        "rc0": rc == 0, "click-aligned": abs(peak(mic) - 3 * RATE) <= 1 and peak(sysc) == 3 * RATE,
        "gap-recorded": meta and meta["legs"]["mic"]["gaps"] == [{"at_sample": gaps[0][0], "samples": gaps[0][1]}],
        "gap-silent": max(abs(v) for v in mic[int(0.6 * RATE):int(0.85 * RATE)]) == 0,
    })


def case_missing_mic():
    rc, out, meta, err = finalize(make_case("missing-mic", sys_secs=6))
    mic, sysc = channels(out / "master.caf")
    return report("missing-mic", {
        "rc3": rc == 3, "state": meta and meta["state"] == "partial",
        "ch0-silent": max(abs(v) for v in mic) == 0, "length": abs(len(mic) - 6 * RATE) <= 1,
        "marked": meta and meta["legs"]["mic"]["present"] is False,
        "listen": (out / "listen.m4a").exists(),
    })


def case_truncated():
    rc, out, meta, err = finalize(make_case("truncated-mic", sys_secs=10, mic_secs=4.9))
    return report("truncated-mic", {
        "rc3": rc == 3, "state": meta and meta["state"] == "partial",
        "truncated": meta and meta["legs"]["mic"].get("truncated") is True,
    })


def case_stop_trim():
    rc, out, meta, err = finalize(make_case("stop-trim", sys_secs=10, mic_secs=9.9), stop_ns=SYS_FIRST + ns(7))
    mic, sysc = channels(out / "master.caf")
    return report("stop-trim", {
        "rc0": rc == 0, "length": abs(len(sysc) - 7 * RATE) <= 1,
        "duration": meta and abs(meta["actual"]["duration_s"] - 7) < 0.01,
    })


def case_both_empty():
    rc, out, meta, err = finalize(make_case("both-empty"))
    return report("both-empty", {
        "rc1": rc == 1, "state": meta and meta["state"] == "failed",
        "no-master": not (out / "master.caf").exists(),
        "raw-kept": (WORK / "both-empty" / "tmp" / "mictee.log").exists(),
    })


if __name__ == "__main__":
    results = [case_aligned(), case_gap(), case_missing_mic(), case_truncated(), case_stop_trim(), case_both_empty()]
    shutil.rmtree(WORK, ignore_errors=True)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    sys.exit(0 if all(results) else 1)
