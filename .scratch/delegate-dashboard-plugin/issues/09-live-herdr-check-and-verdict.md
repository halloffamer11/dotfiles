# 09 — Live Herdr check and prototype verdict

**What to build:** The live acceptance run and the decision the prototype exists for.
In Herdr, link the local plugin, open the dashboard as a targeted split and in at least
one other supported placement, and confirm the pinned project identity. In a disposable
project policy, change Project order, Gate and Margin, and confirm that the project
routing document and the marked Tier leader change together. No worker is dispatched
and no vendor is probed repeatedly. Then answer the two questions: is a Herdr plugin
the right host for a persistent delegation control surface, and do project-level Order,
Gate and Margin controls give useful manual steering? Record the question, the verdict
and the throwaway branch pointer on ticket 01.

Part of [01 Prototype the project delegation dashboard](01-prototype-project-delegation-dashboard.md).

**Blocked by:** 07 Edit Gate and Margin; 08 Herdr plugin launcher and make target

**Status:** ready-for-human — technical checks passed 2026-09-14; Orin's prediction/verdict remains

- [x] The dashboard opens as a targeted split and in one other placement, pinned to the invoking project.
- [x] Order, Gate and Margin edits in a disposable project change the file and the Tier leader together.
- [x] No worker dispatched and no repeated vendor probe during the check.
- [ ] Orin can predict the marked Tier leader after each kind of edit.
- [x] Ticket 01 records the tested question, the verdict and the throwaway branch pointer.

## Landed, 2026-09-14

Scope: committed on `worktree/delegate-monitor-herdr`, not merged to `main`.

The lead performed this check directly because it requires the session's live
Herdr context. Implementation tickets were routed through delegate in separate
Herdr worktrees. Ticket 08 records the normal `make -C` invoking-project checks.

After integration at `47024c3`, the locally linked `delegate.project-dashboard`
entrypoint opened as split `w2C:p6` beside the task shell `w2C:p1`, then as tab
`w2C:p7`. Both visibly pinned `/private/tmp/delegate-dashboard-live.frqMrD/project`.
The disposable global catalog and Meter fixtures were supplied through
`open.py --cwd ... --config-dir ... --meters ...`; they never replaced live config.

Fixture Tier 1 had A first (Pace 0.80) and B second (Pace 0.95), both above Gate.
Tier 2 had G first (Remaining 5%, Pace 0.75) and O second (Pace 0.80).
Initial Gate was 10%, Margin 20%, and leaders were A and O.

- `J` moved A below B, saved the full Tier-then-position list, and marked B.
- `K` restored A first. `m`, `10`, Enter saved Margin 0.1 and marked B with
  `stolen by pace: 0.95 >= 0.8 + 0.1`.
- `m`, `20`, Enter restored Margin 0.2 and marked A.
- `g`, `1`, Enter saved Gate 0.01 and marked G in Tier 2.
- Gate 101% showed an error and retained policy hash
  `88e25dd12ac70b3693a15f05c6e96e6d017b648a` byte-for-byte.
- During a new Gate entry, an external note edit hot-reloaded. Enter showed a
  conflict and retained external hash `382d2b3175e31b4663b3215045a1fbbe89bae263`.

Both test panes were closed with `q`. During the entire editing/placement check,
the live ledger hash stayed `e8955431941e1bc822b419d36b3f6134920de70c` and the live
usage-cache hash stayed `34cd3eabc12e983fda4eb65d2c1029c6860cf97c`. The disposable
global lanes, routing, and Meter hashes also stayed unchanged. No worker launch
or vendor probe was performed during this window.

Technical verdict and branch pointer are in ticket 01. Orin's predictability
verdict is still pending. Independent review
is recorded in [the review record](../research/2026-09-14-review.md). Popup routing was
checked against Herdr's installed schema, but popup was not opened live.

After the review fixes, a second smoke check in `w2N:p2` used the same disposable
fixture. It showed `p` for Project order and `g` for global fallback after a partial
Project order edit. The legend identifies fallback as derived. The pane was closed
with `q`; no live policy was changed.

User test, 2026-09-14: Orin opened the dashboard in `w1Y:p9` and saved project
Gate 0% and Margin 50%. Herdr's visible pane and the installed skill's
`rank.py impl --tier 3 --meters ~/.cache/delegate/usage.json` both selected
`grok46-high@grok`. Normal `impl` (Tiers 2-3) selected `flash-high@agy` through
a Pace steal. A Tier leader is not the Pick for a Class range.

During wrap-up, `.delegate/routing.json` also acquired `project_order` from the
user's test. This is preserved on the prototype branch, not intended for `main`.
The installed `~/.agents/skills/delegate` and `~/.claude/skills/delegate` both
resolve to `~/dotfiles/agents/skills/delegate`, not this worktree. Its catalog
validator now fails with `key 'project_order': unknown top-level key` for this
project. The branch validator accepts the file, and the branch ranker still
selects Grok for exact Tier 3 with the same cached Meters. The earlier installed
skill confirmation preceded the Project order save; it does not establish current
compatibility. Next: obtain direction for backend integration or an installed-skill
update before expecting installed dispatch to consume this project policy. No
merge, installation change, or removal of the user's policy was authorized.

Keep the disposable fixture `/tmp/delegate-dashboard-live.frqMrD` and the review
evidence until the human verdict. No fresh-context deletion was performed. The
user's dashboard pane stays open; no background implementation workers remain.
