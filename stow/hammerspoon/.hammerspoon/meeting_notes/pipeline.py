"""run and queue: transcribe, then the optional enhancement, with progress in
recording.json "pipeline".

pipeline.state: processing, then transcribed or enhanced, or failed with a
reason; pipeline.enhancement says what the enhancement step did (written,
unchanged, or skipped and why). A hand-edited output is kept and the run goes on.

queue runs every recording folder whose capture state is recorded or partial
and whose pipeline state is missing, or processing with a free lock (a run that
died). failed is retried only with --retry. The queue is the folders on disk,
so a Hammerspoon reload loses nothing.
"""
import json, os

from . import enhance, transcribe
from .common import Busy, Refused, lock_is_free, read_recording, recording_lock, set_pipeline


def run(rec, cfg, force=False, log=print):
    """Returns the final pipeline state."""
    with recording_lock(rec):
        read_recording(rec)
        set_pipeline(rec, "processing")
        try:
            try:
                path, how = transcribe.run(rec, cfg, force)
                log(f"transcribe: {how} {path}")
            except Refused as e:
                log(f"transcribe: kept as edited ({e})")
            try:
                path, how = enhance.run(rec, cfg, force)
                log(f"enhance: {how} {path or ''}".rstrip())
            except Refused as e:
                how = f"kept as edited ({e})"
                log(f"enhance: {how}")
            final = "enhanced" if how in ("written", "unchanged") or how.startswith("kept") else "transcribed"
            set_pipeline(rec, final, enhancement=how)
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
