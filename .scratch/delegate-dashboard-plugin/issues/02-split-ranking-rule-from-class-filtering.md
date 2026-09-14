# 02 — Split the ranking rule from Class filtering

**What to build:** A prefactor of delegate's ranking. Today one ranking function both
restricts candidates to a Class floor and ceiling and applies the selection rule
(carried state, Gate, harness availability, unknown Meter, sort by Tier, Order, Pace and
lane name, then the Margin steal). Split it so the rule runs over a given Tier range,
and Class ranking becomes a thin caller that supplies the Class floor (or the per-job
Tier) and ceiling. No Pick, reason, veto text or row order changes for any caller.
This makes an exact-Tier leader (ticket 03) a second caller instead of a copy of the
arithmetic.

Part of [01 Prototype the project delegation dashboard](01-prototype-project-delegation-dashboard.md).
Landing target: `main`; this ticket worktree is not merged.

**Blocked by:** None — can start immediately.

**Status:** implemented in this isolated ticket worktree; not landed on `main`

- [x] The selection rule exists once in `rank_range`; Class ranking calls it with the Class floor (or per-job Tier) and the Class ceiling.
- [x] Every Class Pick, reason, veto text and row order is unchanged for the same catalog, Meters and harnesses.
- [x] The existing catalog, ranking, dispatch and report suites pass without edits to their expectations.

## Implementation and evidence

- `agents/skills/delegate/scripts/rank.py` exposes `rank_range` as the canonical
  inclusive-Tier selection boundary; `rank` only resolves Class bounds and
  preserves Class-specific reason text before calling it.
- Passing checks: `test_catalog.py`, `test_rank.py`, `test_dispatch.py`, and
  `python3 -m py_compile agents/skills/delegate/scripts/rank.py`.
- `test_report.py` passes with the inherited `NO_COLOR` setting cleared. With
  `NO_COLOR=1`, only its color-output assertion fails; report code was not changed.
