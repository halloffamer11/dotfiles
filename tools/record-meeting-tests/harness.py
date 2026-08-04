#!/usr/bin/env python3
"""Regression harness for the record-meeting rig (stdlib only).

Emulates how the script is really stopped — a process-group SIGINT, which is
what Hammerspoon's hs.task:interrupt() and a terminal Ctrl-C both deliver —
and validates the failure modes that have actually bitten:

  1. happy-path        normal record + stop
  2. quick-stop        stop during capture startup (ffmpeg device-init window)
  3. double-INT        duplicate group signal (the original data-loss bug)
  4. triple-INT        signal hammering
  5. concurrent        second invocation must refuse, first must survive
  6. orphan-recovery   SIGKILL leaves capture legs running; next run must reap
                       them and record successfully (work-laptop "crisscross")

Run:  make test-recorder     (or: python3 tools/record-meeting-tests/harness.py)
Recordings go to a throwaway temp dir; nothing touches ~/Recordings.
For sample-level fidelity analysis (needs numpy + audible tone), see fidelity.py.
"""
import json, os, pathlib, shutil, signal, subprocess, sys, tempfile, time

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "stow/hammerspoon/.hammerspoon/bin/record-meeting"
WORK = pathlib.Path(tempfile.mkdtemp(prefix="rm-harness."))
REC = WORK / "rec"
ENV = dict(os.environ, RECORDINGS_DIR=str(REC))

def spawn():
    return subprocess.Popen([str(SCRIPT)], env=ENV, start_new_session=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def group_int(p, n=1, gap=0.15):
    for _ in range(n):
        try:
            os.killpg(p.pid, signal.SIGINT)
        except (ProcessLookupError, PermissionError):
            break
        time.sleep(gap)

def finish(p, timeout=30):
    try:
        return p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try: os.killpg(p.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError): pass
        p.communicate()
        return None, None

def new_recordings(before):
    return set(REC.glob("meeting-*.m4a")) - before

def duration_of(m4a):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(m4a)], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)

def legs_alive():
    out = subprocess.run(["pgrep", "-x", "audiotee"], capture_output=True, text=True).stdout
    out += subprocess.run(["pgrep", "-x", "mictee"], capture_output=True, text=True).stdout
    return [int(x) for x in out.split()]

def check_saved(name, p, out, err, before, run_secs):
    new = new_recordings(before)
    if p.returncode != 0 or not new:
        print(f"[{name}] FAIL rc={p.returncode} files={sorted(f.name for f in new)} stderr={(err or '').strip()[:200]}")
        return False
    m4a = new.pop()
    dur = duration_of(m4a)
    meta = json.loads(m4a.with_suffix(".json").read_text())
    ok = dur > max(0.5, run_secs - 4) and dur < run_secs + 2 \
        and meta["system_leg"] == 1 and meta["mic_leg"] == 1
    print(f"[{name}] {'PASS' if ok else 'FAIL'} dur={dur:.1f}s (ran {run_secs}s) "
          f"legs=sys:{meta['system_leg']} mic:{meta['mic_leg']}")
    return ok

def signal_case(name, run_secs, n_int, gap=0.15):
    before = set(REC.glob("meeting-*.m4a"))
    p = spawn()
    time.sleep(run_secs)
    group_int(p, n_int, gap)
    out, err = finish(p)
    if out is None:
        print(f"[{name}] FAIL: script did not exit after SIGINT")
        return False
    return check_saved(name, p, out, err, before, run_secs)

def concurrent_case():
    name = "concurrent-refused"
    before = set(REC.glob("meeting-*.m4a"))
    a = spawn()
    time.sleep(3)
    b = spawn()
    b_out, b_err = finish(b, timeout=15)
    b_ok = b is not None and b.returncode == 1 and "already running" in (b_err or "")
    group_int(a)
    a_out, a_err = finish(a)
    a_ok = a_out is not None and check_saved(name + "/first-run", a, a_out, a_err, before, 3 + 1)
    print(f"[{name}] {'PASS' if (b_ok and a_ok) else 'FAIL'} "
          f"second-refused={b_ok} (rc={b.returncode})")
    return b_ok and a_ok

def orphan_case():
    name = "orphan-recovery"
    p = spawn()
    time.sleep(4)
    os.killpg(p.pid, signal.SIGKILL)   # hard kill: children survive in own pgids
    p.communicate()
    time.sleep(1)
    orphans = legs_alive()
    if not orphans:
        print(f"[{name}] FAIL: expected orphaned legs after SIGKILL, found none")
        return False
    before = set(REC.glob("meeting-*.m4a"))
    q = spawn()
    time.sleep(6)
    group_int(q)
    out, err = finish(q)
    if out is None:
        print(f"[{name}] FAIL: recovery run did not exit")
        return False
    reaped = "reaping orphaned" in (err or "")
    saved = check_saved(name + "/recovery-run", q, out, err, before, 6)
    clean = not legs_alive()
    print(f"[{name}] {'PASS' if (reaped and saved and clean) else 'FAIL'} "
          f"orphans-found={len(orphans)} reap-message={reaped} no-strays-after={clean}")
    return reaped and saved and clean

if __name__ == "__main__":
    if not SCRIPT.exists():
        sys.exit(f"script not found: {SCRIPT}")
    REC.mkdir(parents=True)
    results = [
        signal_case("happy-8s", 8, 1),
        signal_case("quick-stop-1.5s", 1.5, 1),
        signal_case("double-INT", 6, 2, gap=0.05),
        signal_case("triple-INT", 6, 3, gap=0.02),
        concurrent_case(),
        orphan_case(),
    ]
    strays = legs_alive()
    if strays:
        print(f"[teardown] WARNING: stray capture processes left: {strays} — killing")
        for pid in strays:
            try: os.kill(pid, signal.SIGKILL)
            except ProcessLookupError: pass
        results.append(False)
    shutil.rmtree(WORK, ignore_errors=True)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    sys.exit(0 if all(results) else 1)
