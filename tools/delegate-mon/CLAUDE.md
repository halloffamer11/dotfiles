# Delegate Monitor (`delegate-mon`)

Rust crate for delegate monitoring. Moved out of the delegate skill to `tools/delegate-mon/` on 2026-09-09; a skill directory holds only what the skill executes.

## Purpose

Task 3: TUI for delegate monitoring. Provides the `delegate-mon` binary (`cargo run` from this directory). Implements the Ratatui 0.30 + crossterm terminal interface with density-over-chrome layouts, real-time meter gauges, open thread tracking, selectable weekly burn charts (1h/24h/7d), background refresh/ranking probes, and rank overlay.

## References

- Design spec: `docs/superpowers/specs/2026-09-02-delegate-monitor-design.md`
- Implementation plan: `docs/superpowers/plans/2026-09-02-delegate-monitor.md`
- Delegate skill root: `../../agents/skills/delegate/`
