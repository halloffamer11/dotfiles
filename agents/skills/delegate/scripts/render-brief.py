#!/usr/bin/env python3
"""
render-brief.py — fill templates/brief.md with the task's five lines.

    render-brief.py <template> <output> <tool_budget> <objective> <workdir>
                    <scope> <constraints> <write_rule> <done> <return>

Called by dispatch.sh only. Each {{PLACEHOLDER}} in the template is replaced
by the matching argument; an empty argument becomes "(none stated)" so the
child never sees a dangling heading.
"""
import sys

PLACEHOLDERS = ["TOOL_BUDGET", "OBJECTIVE", "WORKDIR", "IN_SCOPE",
                "CONSTRAINTS", "WRITE_RULE", "DONE", "RETURN"]

template_path, output_path = sys.argv[1], sys.argv[2]
values = sys.argv[3:]

with open(template_path) as f:
    text = f.read()
for name, value in zip(PLACEHOLDERS, values):
    text = text.replace("{{" + name + "}}", value or "(none stated)")
with open(output_path, "w") as f:
    f.write(text)
