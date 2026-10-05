"""Command line for meeting-notes; see bin/meeting-notes."""
import argparse, os, subprocess, sys

from . import doctor, match, notes, pipeline, transcribe
from .common import Busy, Refused, settings

EXIT_DISABLED, EXIT_REFUSED, EXIT_BUSY = 5, 4, 75


def main(argv=None):
    ap = argparse.ArgumentParser(prog="meeting-notes")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, helptext in (("match", "find the calendar event -> meeting.json"),
                           ("transcribe", "speech to text and speakers -> transcript.json"),
                           ("notes", "local LLM notes -> notes.md"),
                           ("run", "match, transcribe, notes in order")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("dir")
        p.add_argument("--force", action="store_true", help="rerun even when the fingerprints are unchanged")
        if name == "run":
            p.add_argument("--if-enabled", action="store_true", help="do nothing (exit 5) unless auto_run = true")
    q = sub.add_parser("queue", help="run every recording that has not been processed")
    q.add_argument("--retry", action="store_true", help="also retry failed recordings")
    q.add_argument("--if-enabled", action="store_true", help="do nothing (exit 5) unless auto_run = true")
    sub.add_parser("doctor", help="read-only health check")
    a = ap.parse_args(argv)
    cfg = settings()
    try:
        if getattr(a, "if_enabled", False) and not cfg["run"]["auto_run"]:
            print("meeting-notes: auto_run is off ([run] auto_run = true in config.toml turns it on)")
            return EXIT_DISABLED
        if a.cmd == "doctor":
            return doctor.run(cfg)
        if a.cmd == "queue":
            done, failed = pipeline.queue(cfg, a.retry)
            print(f"queue: {done} processed, {failed} failed")
            return 1 if failed else 0
        rec = os.path.abspath(a.dir)
        if a.cmd == "run":
            print(f"{rec}: {pipeline.run(rec, cfg, a.force)}")
            return 0
        path, how = {"match": match.run, "transcribe": transcribe.run, "notes": notes.run}[a.cmd](rec, cfg, a.force)
        if how == "off":
            print("meeting-notes: notes are off ([notes] endpoint and model in config.toml)")
            return EXIT_DISABLED
        print(f"meeting-notes: unchanged, skipped: {path}" if how == "unchanged" else path)
        return 0
    except Refused as e:
        print(f"meeting-notes: {e}", file=sys.stderr)
        return EXIT_REFUSED
    except Busy as e:
        print(f"meeting-notes: {e}", file=sys.stderr)
        return EXIT_BUSY
    except (RuntimeError, ValueError, OSError, KeyError, subprocess.CalledProcessError) as e:
        print(f"meeting-notes: {e}", file=sys.stderr)
        return 1
