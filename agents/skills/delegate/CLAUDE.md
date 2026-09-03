# Delegate

External worker routing lives in this directory. Read `SKILL.md` first, then use these files as the implementation authority:

- `lanes.tsv`: eligible lanes and work classes.
- `rank.py`: quota-aware deterministic lane ranking.
- `usage.py`: cached subscription-meter probes.
- `dispatch.sh`: the single child-harness entry point.
- `schemas/return.json`: normalized child return contract.
- `tests/`: dispatcher and envelope verification.

## Active sub-project: monitoring TUI

Build a local, read-mostly monitoring cockpit as a separate Rust sub-project. The design is not yet approved and no implementation has started.

Accepted requirements:

- Use Rust. Ratatui is the current framework candidate.
- Take visual inspiration from `btop` and `macmon`: dense but aligned panels, exact percentages beside progress bars, sparklines or time-series graphs, and clear color thresholds.
- Show remaining quota for every meter, including 5-hour and weekly windows, binding window, reset time, pace, and cache freshness.
- Show open delegate threads with lane, class when known, elapsed time, and lifecycle state.
- Show burn rate over selectable time windows, initially 1 hour, 24 hours, and 7 days.
- Keep JSONL as the initial durable event store. Watch files for updates.
- Permit manual usage refresh and lane reranking. Do not add dispatch, resume, stop, or Herdr-wide agent controls.
- Treat the TUI as a consumer of a versioned state/event contract, not as the owner of routing logic.

Known data gap: the current ledger samples Claude hook events and meter state, but `dispatch.sh` does not emit a complete start/finish lifecycle with lane, class, duration, result, and child session. Design the event contract before polishing the UI.

References:

- <https://github.com/aristocratos/btop>
- <https://github.com/vladkens/macmon>
- <https://ratatui.rs/>

Next session: finish the reference and Ratatui research, propose 2–3 architecture approaches, revise the visual mockup around percentage bars, open threads, and time-series burn, then get explicit design approval. After approval, write the architectural spec and implementation plan before coding.
