#!/usr/bin/env python3
import json
import sys

original = sys.stdin.read()
settings = json.loads(original or "{}")
agy = {{ if . }}True{{ else }}False{{ end }}
command = '"$HOME/.local/bin/fleet-check" --brief'
if agy:
    command += " --format agy"
    group = settings.setdefault("fleet-check", {})
    entry = {"type": "command", "command": command}
else:
    group = settings.setdefault("hooks", {})
    entry = {"hooks": [{"type": "command", "command": command}]}
entries = group.setdefault("SessionStart", [])


def has_command(group):
    handlers = group.get("hooks", [group])
    return not group.get("matcher") and any(
        handler.get("command") == command and handler.get("type", "command") == "command"
        for handler in handlers)


if any(has_command(group) for group in entries):
    sys.stdout.write(original)
else:
    entries.append(entry)
    print(json.dumps(settings, indent=2, ensure_ascii=False))
