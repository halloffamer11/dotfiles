#!/usr/bin/env python3
"""events.py — JSONL event encoder for delegate monitoring.

CLI:
  python3 events.py meter <usage.json>
  python3 events.py start <thread_id> <lane> <class-or-null> <effort> <timeout_s> <cwd> <brief> <out> <write-or-null>
  python3 events.py finish <thread_id> <lane> <class-or-null> <secs> <rc> <status> <child_session-or-null> <out>
"""
import json, os, sys
from datetime import datetime


def ts_now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def opt_val(v):
    if v in ("", "-", "null", None):
        return None
    return v


def ledger_path():
    return os.environ.get("DELEGATE_LEDGER") or os.path.expanduser("~/.cache/delegate/ledger.jsonl")


def append(obj):
    p = ledger_path()
    parent = os.path.dirname(p)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj) + "\n")


def meter_event(doc):
    return {
        "v": 1,
        "kind": "meter",
        "ts": ts_now(),
        "source": "probe",
        "cache_age_s": 0,
        "probed_at": doc.get("probed_at"),
        "lanes": doc.get("lanes", []),
    }


def start_event(thread_id, lane, class_, effort, timeout_s, cwd, brief, out, write=None):
    return {
        "v": 1,
        "kind": "dispatch.start",
        "ts": ts_now(),
        "thread_id": thread_id,
        "lane": lane,
        "class": opt_val(class_),
        "effort": effort,
        "timeout_s": int(timeout_s),
        "cwd": cwd,
        "brief": brief,
        "out": out,
        "write": opt_val(write),
    }


def finish_event(thread_id, lane, class_, secs, rc, status, child_session, out):
    return {
        "v": 1,
        "kind": "dispatch.finish",
        "ts": ts_now(),
        "thread_id": thread_id,
        "lane": lane,
        "class": opt_val(class_),
        "secs": int(secs),
        "rc": int(rc),
        "status": status,
        "child_session": opt_val(child_session),
        "out": out,
    }


def main():
    if len(sys.argv) < 2:
        sys.exit(2)
    cmd = sys.argv[1]
    try:
        if cmd == "meter":
            if len(sys.argv) != 3:
                sys.exit(2)
            with open(sys.argv[2], "r", encoding="utf-8") as f:
                doc = json.load(f)
            append(meter_event(doc))
        elif cmd == "start":
            if len(sys.argv) != 11:
                sys.exit(2)
            _, _, thread_id, lane, class_, effort, timeout_s, cwd, brief, out, write = sys.argv
            append(start_event(thread_id, lane, class_, effort, timeout_s, cwd, brief, out, write))
        elif cmd == "finish":
            if len(sys.argv) != 10:
                sys.exit(2)
            _, _, thread_id, lane, class_, secs, rc, status, child_session, out = sys.argv
            append(finish_event(thread_id, lane, class_, secs, rc, status, child_session, out))
        else:
            sys.exit(2)
    except Exception:
        sys.exit(2)


if __name__ == "__main__":
    main()
