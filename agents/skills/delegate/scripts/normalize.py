#!/usr/bin/env python3
"""
normalize.py — reduce a child's raw output to the return-schema object.

    normalize.py <raw-child-output> <out.json>      prints the child's session id

Each harness wraps the model's answer in its own envelope. This script finds
the schema object inside that envelope and writes ONLY the object to out.json,
so every caller reads the same five fields whatever harness ran.

Search order:
  1. envelope["structured_output"|"structuredOutput"]  (agy, claude with --json-schema)
  2. envelope["response"|"text"|"result"]    as a dict, a string holding JSON, or
     prose ending in a JSON object (grok without --json-schema): the LAST
     balanced {...} block wins, missing schema fields are filled with defaults
  3. the envelope itself, if it already has status + deliverable (codex -o)
Fallbacks never fail the run: prose becomes status "partial" with the prose
as the deliverable; unparseable output becomes status "blocked".
"""
import json
import re
import sys

EMPTY = {"evidence": [], "open_questions": [], "changed_files": []}


def last_json_object(text):
    """The last balanced top-level {...} block in text that parses as a dict, or None."""
    depth, start, found = 0, None, None
    in_str = esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc: esc = False
            elif ch == "\\": esc = True
            elif ch == '"': in_str = False
            continue
        if ch == '"': in_str = True
        elif ch == "{":
            if depth == 0: start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    obj = json.loads(text[start:i + 1])
                    if isinstance(obj, dict): found = obj
                except Exception:
                    pass
    return found


def with_defaults(obj):
    """Fill schema fields a child omitted; an omitted status is a partial result."""
    if "status" not in obj:
        obj["status"] = "partial"
        obj.setdefault("open_questions", []).append("child omitted status; treated as partial")
    obj.setdefault("deliverable", "")
    for key, empty in EMPTY.items():
        obj.setdefault(key, list(empty))
    return obj


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
        for key in ("structured_output", "structuredOutput"):
            if isinstance(envelope.get(key), dict):
                return envelope[key]
        # agy error envelope: {"status": "ERROR"|"CANCELED", "response": "", "error": "..."}.
        # Say why, instead of degrading the empty response to a silent "partial".
        if envelope.get("status") in ("ERROR", "CANCELED") and not envelope.get("structured_output"):
            reason = envelope.get("error") or f"child {envelope['status'].lower()} with no output (agy plan mode ends the run on the first command attempt)"
            return {"status": "blocked", "deliverable": f"agy {envelope['status']}: {reason}",
                    **EMPTY, "open_questions": [f"harness failure: {reason}"[:200]]}
        for key in ("response", "text", "result"):
            value = envelope.get(key)
            if isinstance(value, dict):
                return value
            if isinstance(value, str):
                try:
                    return with_defaults(json.loads(value))
                except Exception:
                    tail = last_json_object(value)
                    if tail is not None and ("deliverable" in tail or "status" in tail):
                        return with_defaults(tail)
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
