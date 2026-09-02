#!/usr/bin/env python3
"""
normalize.py — reduce a child's raw output to the return-schema object.

    normalize.py <raw-child-output> <out.json>      prints the child's session id

Each harness wraps the model's answer in its own envelope. This script finds
the schema object inside that envelope and writes ONLY the object to out.json,
so every caller reads the same five fields whatever harness ran.

Search order:
  1. envelope["structured_output"]           (agy, claude with --json-schema)
  2. envelope["response"|"text"|"result"]    as a dict, or a string holding JSON
  3. the envelope itself, if it already has status + deliverable (codex -o)
Fallbacks never fail the run: prose becomes status "partial" with the prose
as the deliverable; unparseable output becomes status "blocked".
"""
import json
import re
import sys

EMPTY = {"evidence": [], "open_questions": [], "changed_files": []}


def parse_envelope(raw):
    try:
        return json.loads(raw)
    except Exception:
        match = re.search(r"\{.*\}", raw, re.S)   # first {...} block in noisy stdout
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
    return {}


def extract_object(envelope, raw):
    if isinstance(envelope, dict):
        if isinstance(envelope.get("structured_output"), dict):
            return envelope["structured_output"]
        for key in ("response", "text", "result"):
            value = envelope.get(key)
            if isinstance(value, dict):
                return value
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except Exception:
                    return {"status": "partial", "deliverable": value.strip()[:4000],
                            **EMPTY, "open_questions": ["child returned prose, not the schema"]}
        if {"status", "deliverable"} <= set(envelope):
            return envelope
    return {"status": "blocked", "deliverable": raw.strip()[:4000],
            **EMPTY, "open_questions": ["unparseable child output"]}


def main():
    raw_path, out_path = sys.argv[1], sys.argv[2]
    with open(raw_path) as f:
        raw = f.read()
    envelope = parse_envelope(raw)
    obj = extract_object(envelope, raw)
    for noise in ("toolAction", "toolSummary"):   # agy adds these to structured output
        obj.pop(noise, None)
    with open(out_path, "w") as f:
        json.dump(obj, f, indent=1)
    session = ""
    if isinstance(envelope, dict):
        session = envelope.get("sessionId") or envelope.get("session_id") or envelope.get("conversation_id") or ""
    print(session)


if __name__ == "__main__":
    main()
