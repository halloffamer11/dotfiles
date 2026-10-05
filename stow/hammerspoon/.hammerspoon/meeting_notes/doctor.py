"""doctor: read-only health check of the meeting-notes setup."""
import os

from .common import FFMPEG, adapter

SYNCED = ("Library/Mobile Documents", "Library/CloudStorage", "Dropbox", "Google Drive", "OneDrive", "iCloud Drive")


def run(cfg):
    ok = True

    def line(good, what):
        nonlocal ok
        ok &= good
        print(f"{'ok  ' if good else 'FAIL'}  {what}")

    print(f"config: {cfg['config_path']} ({'found' if os.path.exists(cfg['config_path']) else 'defaults'})")
    exe = cfg["paths"]["adapter"]
    line(os.access(exe, os.X_OK), f"adapter {exe} (make meeting-notes)")
    line(os.path.exists(FFMPEG), f"ffmpeg {FFMPEG}")
    line(os.path.exists("/usr/bin/sandbox-exec"), "sandbox-exec (no-network runs)")
    m = cfg["models"]
    diar = os.path.join(m["models_root"], m["diarizer_folder"])
    line(os.path.isdir(m["asr_dir"]), f"ASR model folder {m['asr_dir']}")
    line(os.path.isdir(diar), f"diarizer model folder {diar}")
    if os.access(exe, os.X_OK) and os.path.isdir(m["asr_dir"]) and os.path.isdir(diar):
        try:
            adapter(cfg, "check", "--model-dir", m["asr_dir"], "--version", m["asr_version"],
                    "--models-root", m["models_root"])
            line(True, "models load offline (network denied)")
        except RuntimeError as e:
            line(False, f"models load offline: {e}")
    rec = os.path.realpath(cfg["paths"]["recordings"])
    synced = [s for s in SYNCED if s in rec]
    line(not synced, f"output folder {rec} is not in a synced folder")
    if os.path.isdir(rec):
        mode = os.stat(rec).st_mode & 0o777
        line(mode & 0o077 == 0, f"output folder mode {oct(mode)} (want 700: chmod 700 {rec})")
        for d in sorted(os.listdir(rec)):
            p = os.path.join(rec, d)
            if os.path.isdir(p) and os.path.exists(os.path.join(p, "recording.json")) and os.stat(p).st_mode & 0o077:
                line(False, f"recording folder {p} is readable by others")
    n = cfg["notes"]
    if n["command"]:
        from .notes import resolve
        cmd = n["command"] if isinstance(n["command"], list) else [n["command"]]
        found = resolve(cmd[0])
        line(bool(found), f"notes command {cmd[0]} ({found or 'not found'})")
        if n["prompt_file"]:
            line(os.path.exists(os.path.expanduser(n["prompt_file"])), f"notes prompt_file {n['prompt_file']}")
    else:
        print("off   notes ([notes] command not set)")
    print(f"{'on  ' if cfg['run']['auto_run'] else 'off '}  auto_run (Hammerspoon starts the pipeline after a recording)")
    print("ALL OK" if ok else "PROBLEMS FOUND")
    return 0 if ok else 1


