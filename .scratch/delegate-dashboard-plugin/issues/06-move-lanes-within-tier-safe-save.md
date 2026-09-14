# 06 — Move lanes inside a Tier, with a safe save

**What to build:** In the dashboard, keys move the selected lane up or down inside its
Tier; a move never crosses a Tier boundary. Each move builds the complete proposed
project routing document, validates it through delegate's project routing validation,
and saves it atomically, keeping every unrelated key (Class ranges, notes, Gate,
Margin). The whole Project order list is written in Tier-then-position sequence, so a
move in one Tier never changes another Tier. Before writing, the dashboard checks that
the file has not changed since it last loaded; if it has, it reloads when safe or shows
a conflict and needs a fresh user action. The screen shows saved, error or conflict,
and the Tier leader updates at once. Key help is on screen.

Part of [01 Prototype the project delegation dashboard](01-prototype-project-delegation-dashboard.md).
Throwaway branch only; never merged to `main`.

**Blocked by:** 04 Project order overlays global Order; 05 Read-only dashboard pinned to one project

**Status:** ready-for-agent

- [ ] Up and down moves stay inside the lane's Tier and cannot cross a boundary.
- [ ] Each accepted move saves the complete document atomically and the next Class ranking, reloaded through the public catalog boundary, reads the new Project order.
- [ ] A save keeps every unrelated key in the project routing document.
- [ ] A move that would fail validation, and a save after a concurrent external edit, both leave the project routing document byte-for-byte unchanged.
- [ ] The screen shows a saved, error or conflict state, and the affected Tier leader updates after an accepted move.
- [ ] A project with no routing document gets one created on the first move.
