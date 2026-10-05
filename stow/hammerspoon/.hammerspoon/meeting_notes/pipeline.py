"""run and queue: the stages in order, with progress in recording.json "pipeline".

Order: match -> transcribe -> notes. match goes first because a matched meeting's
invitee count bounds the diarizer's speaker count. Each stage is optional in
[run] (match, transcribe, notes = true|false); match also needs a calendar
source and notes an endpoint and model, else they are skipped.

pipeline.state: processing, then transcribed (no notes stage), notes-ready, or
failed with a reason. A hand-edited output is kept and the run goes on.

queue runs every recording folder whose capture state is recorded or partial
and whose pipeline state is missing, or processing with a free lock (a run that
died). failed is retried only with --retry. The queue is the folders on disk,
so a Hammerspoon reload loses nothing.
"""
import json, os

from . import match, notes, transcribe
from .common import Busy, Refused, lock_is_free, read_recording, recording_lock, set_pipeline


def run(rec, cfg, force=False, log=print):
    """Returns the final pipeline state."""
    r = cfg["run"]
    with recording_lock(rec):
        read_recording(rec)
        set_pipeline(rec, "processing")
        try:
            steps = []
            if r["match"] and cfg["match"]["source"] != "none":
                steps.append(("match", match.run))
            if r["transcribe"]:
                steps.append(("transcribe", transcribe.run))
            if r["notes"] and notes.enabled(cfg):
                steps.append(("notes", notes.run))
            for name, fn in steps:
                try:
                    path, how = fn(rec, cfg, force)
                    log(f"{name}: {how} {path or ''}".rstrip())
                except Refused as e:
                    log(f"{name}: kept as edited ({e})")
            final = "notes-ready" if any(n == "notes" for n, _ in steps) and os.path.exists(
                os.path.join(rec, "notes.md")) else "transcribed" if os.path.exists(
                os.path.join(rec, "transcript.json")) else "processed"
            set_pipeline(rec, final)
            return final
        except Exception as e:
            set_pipeline(rec, "failed", f"{type(e).__name__}: {e}")
            raise


def pending(cfg, retry=False):
    root = cfg["paths"]["recordings"]
    if not os.path.isdir(root):
        return []
    out = []
    for d in sorted(os.listdir(root)):
        rec = os.path.join(root, d)
        path = os.path.join(rec, "recording.json")
        if not os.path.isfile(path):
            continue
        try:
            meta = json.load(open(path))
        except ValueError:
            continue
        if meta.get("format_version") != 1 or meta.get("state") not in ("recorded", "partial"):
            continue
        state = (meta.get("pipeline") or {}).get("state")
        if state is None or (state == "processing" and lock_is_free(rec)) or (retry and state == "failed"):
            out.append(rec)
    return out


def queue(cfg, retry=False, log=print):
    """Returns (done, failed) counts."""
    done = failed = 0
    for rec in pending(cfg, retry):
        try:
            log(f"{os.path.basename(rec)}: {run(rec, cfg, log=log)}")
            done += 1
        except Busy:
            log(f"{os.path.basename(rec)}: busy, skipped")
        except Exception as e:
            log(f"{os.path.basename(rec)}: failed: {e}")
            failed += 1
    return done, failed
