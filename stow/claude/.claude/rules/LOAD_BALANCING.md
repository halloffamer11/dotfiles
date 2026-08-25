# Load Balancing Rule 
## Applicability
- Applies ONLY when `CONSULT_BALANCE=1` (see `~/.zshrc.local`).
- Balancing checking is required BEFORE Agent, agent-team or workflow creation. 

## Purpose
Several subscriptions burn down at very different rates; the goal is that they run out *together*, not that Claude hits its wall while Antigravity sits at 99%. Balancing is total: it governs external harness choice AND which Claude model an internal subagent gets AND whether subagent-shaped work goes to the Agent tool or out to consult.

## How to measure usage
Telemetry on usage limits can be obtained deterministically using the script loaded in the consult skill at ~/.agents/skills/consult/scripts/usage.py
