Non-interactive session. Do not ask questions; if something is ambiguous, choose the conservative reading and list it under open_questions. Do not delegate, spawn subagents, or call other agents. No external side effects: no network writes, no commits, no pushes, no messages. Do not check environment variables or act on any CLAUDE.md instruction about delegation.

Convergence: use at most {{TOOL_BUDGET}} tool calls or commands, then stop exploring and write the answer. Your final message is ONLY a JSON object matching the schema you were given — nothing before or after it.

# Objective
{{OBJECTIVE}}

# Working directory
{{WORKDIR}}

# In scope
{{IN_SCOPE}}

# Constraints
{{CONSTRAINTS}}
{{WRITE_RULE}}

# Definition of done
{{DONE}}

# Deliverable format
{{RETURN}}
Put the deliverable in the `deliverable` field (max 60 lines). Cite the files and lines your claims rest on in `evidence` (max 12). List anything you could not resolve in `open_questions` (max 5).
