"""doctor: read-only health check of the meeting-notes setup."""
import os

from . import enhance, voiceink
from .common import FFMPEG, adapter

SYNCED = ("Library/Mobile Documents", "Library/CloudStorage", "Dropbox", "Google Drive", "OneDrive", "iCloud Drive")


def run(cfg):
    ok = True

    def line(good, what):
        nonlocal ok
        ok &= good
        print(f"{'ok  ' if good else 'FAIL'}  {what}")

    def info(what):
        print(f"info  {what}")

    print(f"config: {cfg['config_path']} ({'found' if os.path.exists(cfg['config_path']) else 'defaults'})")
    exe = cfg["paths"]["adapter"]
    line(os.access(exe, os.X_OK), f"adapter {exe} (make meeting-notes)")
    line(os.path.exists(FFMPEG), f"ffmpeg {FFMPEG}")
    line(os.path.exists("/usr/bin/sandbox-exec"), "sandbox-exec (no-network runs)")

    vi = voiceink.settings()
    line(vi["found"], "VoiceInk settings readable")
    override = cfg["transcribe"]["model"]
    info(f"VoiceInk mode {vi['mode']!r}: model {vi['model']!r}, language {vi['language']!r}, "
         f"paragraphs {'on' if vi['text_formatting'] else 'off'}" + (f"; config override {override!r}" if override else ""))
    if os.access(exe, os.X_OK):
        from .transcribe import choose_model
        try:
            name, _, log = choose_model(cfg, vi)
            for entry in log:
                if "skipped" in entry:
                    info(f"model {entry['model']} ({entry['role']}) skipped: {entry['skipped']}")
            line(True, f"transcription model {name} loads offline (network denied)")
        except RuntimeError as e:
            line(False, str(e))
        if cfg["transcribe"]["diarize"]:
            try:
                adapter(cfg, "check-diarizer", "--models-root", cfg["models"]["models_root"])
                line(True, "diarizer loads offline")
            except RuntimeError as e:
                line(False, f"diarizer: {e}")

    e = vi["enhancement"]
    info(f"VoiceInk enhancement: {'on' if e['enabled'] else 'off'}, provider "
         f"{e['provider'] or '(first connected; not readable here)'}, model {e['model']!r}, prompt {e['prompt_title']!r}, "
         f"Local CLI template {'set' if e['cli_template'] else 'not set'}")
    try:
        enhance.plan(cfg)
        line(True, f"enhancement: VoiceInk Local CLI ({e['cli_template']}), prompt {e['prompt_title']!r}")
    except enhance.Skipped as s:
        info(f"enhancement skipped: {s}")

    rec = os.path.realpath(cfg["paths"]["recordings"])
    synced = [s for s in SYNCED if s in rec]
    line(not synced, f"output folder {rec} is not in a synced folder")
    if os.path.isdir(rec):
        mode = os.stat(rec).st_mode & 0o777
        line(mode & 0o077 == 0, f"output folder mode {oct(mode)}" + ("" if mode & 0o077 == 0 else f" (chmod 700 {rec})"))
        for d in sorted(os.listdir(rec)):
            p = os.path.join(rec, d)
            if os.path.isdir(p) and os.path.exists(os.path.join(p, "recording.json")) and os.stat(p).st_mode & 0o077:
                line(False, f"recording folder {p} is readable by others")
    print(f"{'on  ' if cfg['run']['auto_run'] else 'off '}  auto_run (Hammerspoon starts the pipeline after a recording)")
    print("ALL OK" if ok else "PROBLEMS FOUND")
    return 0 if ok else 1
