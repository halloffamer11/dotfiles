#!/usr/bin/env python3
"""extract.py <harness> <raw-file> <out-file>  ->  prints session id.
Reduce a harness envelope to the return-schema object. Never raises."""
import json, sys
harness, raw_path, out_path = sys.argv[1:4]
FIELDS = {"status": "blocked", "deliverable": "", "evidence": [], "open_questions": [], "changed_files": []}

def last_object(text):
    depth = 0; start = None; found = None; in_str = esc = False
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
            if depth == 0:
                try:
                    o = json.loads(text[start:i + 1])
                    if isinstance(o, dict): found = o
                except Exception: pass
    return found

raw = open(raw_path).read()
env = None
try: env = json.loads(raw)
except Exception: pass
obj, session = None, ""
if isinstance(env, dict):
    if harness == "agy":
        session = env.get("conversation_id", "")
        obj = env.get("structured_output") or last_object(env.get("response") or "")
    elif harness == "grok":
        session = env.get("sessionId", "")
        obj = last_object(env.get("text") or "")
    elif harness == "codex":          # codex -o wrote the object itself
        obj = env if "status" in env else last_object(raw)
if obj is None: obj = last_object(raw)
if isinstance(obj, dict) and obj.get("status") not in ("done", "partial", "blocked"): obj = None  # an envelope, not a result
if obj is None:
    obj = dict(FIELDS); obj["open_questions"] = ["harness returned no schema object"]; obj["deliverable"] = raw[:2000]
else:
    for k, v in FIELDS.items(): obj.setdefault(k, v if not isinstance(v, list) else list(v))
json.dump(obj, open(out_path, "w"), indent=1)
print(session)
