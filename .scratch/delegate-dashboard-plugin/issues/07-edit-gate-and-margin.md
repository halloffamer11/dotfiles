# 07 — Edit Gate and Margin

**What to build:** In the dashboard, the user edits the project's Gate and Margin as
percentages. The stored values keep their existing numeric meaning and validation. Each
edit uses the same validate, atomic-save and conflict path as ticket 06, and all Tier
leaders recalculate at once: lowering Gate can make a newly allowed lane the leader,
and changing Margin can start or stop a steal. Global Gate and Margin are never
written.

Part of [01 Prototype the project delegation dashboard](01-prototype-project-delegation-dashboard.md).
Throwaway branch only; never merged to `main`.

**Blocked by:** 06 Move lanes inside a Tier, with a safe save

**Status:** implemented as `2833ce7`, integrated as `47024c3`; live checks recorded in ticket 09

- [x] Gate and Margin are shown and edited as percentages and stored as project overrides with their existing meaning.
- [x] An out-of-range or malformed value is rejected and the project routing document stays byte-for-byte unchanged.
- [x] End-to-end on fixtures: lowering Gate moves a Tier leader to a previously vetoed lane exactly as the ranking rule specifies.
- [x] End-to-end on fixtures: changing Margin starts or stops a steal exactly as the ranking rule specifies.
- [x] The next Class ranking reads the saved Gate and Margin.

## Implemented, 2026-09-14

`DashboardModel.begin_percentage_edit()` captures the displayed fractional value,
complete project document, and exact loaded bytes. `save_percentage_edit()` parses a
finite value from 0 through 100, converts it to the existing 0-through-1 fraction,
then uses `save_project_policy()` for delegate's public merged-policy validation,
conflict check, atomic write, reload, and saved/error state. An edit keeps its opening
snapshot even if hot reload observes an external policy change while the user types,
so submission reports a conflict without overwriting the external bytes.

The terminal opens prefilled Gate and Margin editors with `g` and `m`; Enter saves and
Escape cancels. Its input buffer drains pasted characters and complete escape
sequences one key at a time, retaining incomplete sequences for the next read. Every
successful edit reloads the dashboard through canonical `rank.tier_leaders()`, while
global policy and cached Meter observations remain display-only.

Fixture tests cover precise fractional display and prefill, invalid and nonfinite
input, byte and unrelated-key preservation, cancellation, conflict after a reload
during entry, batched input and split escape sequences, Gate eligibility, Margin
steals in both directions, read-only global policy and Meter bytes, and the next
Class rank after public catalog reload.
Verified with:

- `python3 tools/delegate-dashboard/test_dashboard.py`
- `python3 agents/skills/delegate/tests/test_rank.py`
- `python3 -m py_compile tools/delegate-dashboard/model.py tools/delegate-dashboard/dashboard.py tools/delegate-dashboard/test_dashboard.py`
- `git diff --check`
