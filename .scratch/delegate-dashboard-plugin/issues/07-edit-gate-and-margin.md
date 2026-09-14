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

**Status:** ready-for-agent

- [ ] Gate and Margin are shown and edited as percentages and stored as project overrides with their existing meaning.
- [ ] An out-of-range or malformed value is rejected and the project routing document stays byte-for-byte unchanged.
- [ ] End-to-end on fixtures: lowering Gate moves a Tier leader to a previously vetoed lane exactly as the ranking rule specifies.
- [ ] End-to-end on fixtures: changing Margin starts or stops a steal exactly as the ranking rule specifies.
- [ ] The next Class ranking reads the saved Gate and Margin.
