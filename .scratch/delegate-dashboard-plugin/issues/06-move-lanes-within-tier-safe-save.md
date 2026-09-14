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

**Status:** implemented 2026-09-14 in the ticket worktree; not committed

- [x] Up and down moves stay inside the lane's Tier and cannot cross a boundary.
- [x] Each accepted move saves the complete document atomically and the next Class ranking, reloaded through the public catalog boundary, reads the new Project order.
- [x] A save keeps every unrelated key in the project routing document.
- [x] A move that would fail validation, and a save after a concurrent external edit, both leave the project routing document byte-for-byte unchanged.
- [x] The screen shows a saved, error or conflict state, and the affected Tier leader updates after an accepted move.
- [x] A project with no routing document gets one created on the first move.

## Implemented, 2026-09-14

`DashboardModel.move_lane()` constructs the full carried-lane `project_order` in
Tier-then-position sequence and sends it through the reusable
`save_project_policy()` path. That path preserves the loaded project document's other
keys, calls the public `validate_project_routing()` boundary with the original global
lane and routing documents, checks the exact loaded project-policy bytes, refuses
symlink targets, and uses `catalog.write_json()` for a same-directory, fsynced temp
file followed by `os.replace()`.

The byte snapshot committed with dashboard state is the snapshot taken during that
load. A policy change later in the same refresh therefore remains visible to the next
watch pass instead of being marked consumed. A pre-save mismatch reloads and reports a
conflict; the user must repeat the move. This is the ordinary last-check/atomic-rename
protection, not filesystem locking: another writer can still race in the narrow window
between the final byte check and `os.replace()`, which is accepted for this prototype.

The terminal keeps cursor motion on `j`/`k` or arrows and lane movement on `J`/`K` or
shift-arrows. Saved, validation-error, and conflict details appear in the header, and
an accepted save reloads canonical Tier leaders immediately.

Public model-boundary tests cover both Tier bounds, the complete ordered list,
unrelated-key preservation, Class ranking after a public catalog reload, first-save
creation, merged-policy rejection, conflict byte preservation and retry, refresh-race
snapshot behavior, symlink protection, and immediate save/leader state. Verified with:

- `python3 tools/delegate-dashboard/test_dashboard.py`
- `python3 agents/skills/delegate/tests/test_catalog.py`
- `python3 -m py_compile tools/delegate-dashboard/model.py tools/delegate-dashboard/dashboard.py tools/delegate-dashboard/test_dashboard.py`
- `git diff --check`
