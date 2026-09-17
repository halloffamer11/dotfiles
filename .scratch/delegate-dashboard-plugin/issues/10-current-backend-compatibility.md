# 10 — Current backend compatibility

**What to build:** Update the accepted Herdr dashboard prototype to current main;
show sourced metering state and the effect of metering off; route project edits
through the canonical catalog boundary while retaining the dashboard's project
write restrictions and stale-editor protection. Keep the existing prototype scope.

**Blocked by:** None — prototype accepted and Orin approved this pass on 2026-09-17.

**Status:** paused WIP 2026-09-17 — kept at Orin’s fresh-context request; implementation and verification incomplete

- [x] Current main is merged into the isolated prototype branch; main and the Rust monitor are preserved.
- [ ] Metering on/off and its source are visible; off explains inactive Gate/Margin/Pace and cached observations.
- [ ] Gate, Margin and Project order use revision-checked catalog edits without vendor probes.
- [ ] Editor snapshots, unrelated keys, no-op bytes, fresh-global validation and project path restrictions are preserved.
- [ ] Behavioral regression checks and a disposable live Herdr check pass.
- [ ] Independent review findings are adjudicated and fixed; context and evidence are current.

## Scope approved, 2026-09-17

Orin selected “Compatibility pass first” after the restart check. Evidence:
`../research/2026-09-16-restart.md`. Main at `2680477` is merged as `70cf9bb`.
The root context conflict was resolved using current main facts and this branch's
active compatibility scope. Initial dashboard, catalog and rank checks passed.

Project policy values changed locally during the session to Gate 10% / Margin 20%.
These values are preserved in a separate branch-only policy commit, not in the implementation commit.
Production design and merging the dashboard into main remain separate decisions.

## Fresh-context checkpoint, 2026-09-17

Keep the compatibility pass. Two session-owned Grok workers were interrupted with
SIGINT and are stopped; their relays returned blocked/rc130 due to that interruption,
not an authentication failure. No worker remains active. The partial model patch is
kept as WIP. `dashboard.py` and `test_dashboard.py` were not edited by the workers.

Current model WIP adds sourced `policy.meters` and adapters for project
`catalog.edit_catalog` preview/apply. This has not had independent review.
`python3 tools/delegate-dashboard/test_dashboard.py` currently reports 26 passed,
one error and one failure:

- `test_first_move_creates_project_policy`: `KeyError: 'version'` at line 424;
  the canonical new-project write does not insert the prototype's version field.
- `test_move_stays_in_tier_and_saves_complete_order`: canonical Order saving keeps
  a partial list, while the accepted prototype requires a complete Tier-then-position
  list. Reconcile the adapter with that contract; do not merely weaken the test.

The implementation still needs the planned metering/Meter regression checks,
source-revision race and no-op checks, terminal display changes, independent review,
and disposable live Herdr acceptance. Inspect exception handling in the adapter,
project-target checks around preview/apply, and stale-global Order actions. The
module docstring still says it never imports/executes usage.py; correct that stale
statement to the no-probe contract, since rank now imports usage.

Authorizations persist: agy and Grok are approved. Claude Opus startup returned
HTTP 403 `oauth_not_allowed_for_organization`; Orin then explicitly approved a
delegate-selected fallback for this display task. Do not ask that routing question
again. Use delegate ranking excluding Claude for this job; both implementation
workers selected Grok. Use a different Model family for review.

Run evidence:
- Model: `~/.cache/delegate/runs/20260917T105619Z-grok46-high@grok-149ab396`
  (494 seconds; interrupted with partial model.py edits).
- Display fallback: `~/.cache/delegate/runs/20260917T110327Z-grok46-high@grok-99182f78`
  (62 seconds; interrupted with no edits).
- Failed Opus prompt: `~/.cache/delegate/runs/20260917T105636Z-opus-high@claude-7762ff7c`;
  CLI error response retained in `/private/tmp/delegate-dashboard-compat/tui-return.json`.

Reusable Briefs (`model-brief.md`, `tui-brief.md`, `review-brief.md`), disposable
live fixture (`live/`), `verify_no_probes.py`, and `wip-tests.log` remain in
`/private/tmp/delegate-dashboard-compat/`. Briefs need their base/status adjusted
before reuse. The no-probe helper passed against the pre-WIP baseline; run it again
after completing the patch. The owning ticket and source are durable; recreate
fixtures if /private/tmp is cleared. The prior restart record is historical evidence.

Orin approved cleanup on 2026-09-17. Deleted exactly five obsolete files: restart
`check_compatibility.py`, `main-state.json`, `prototype-state.json`, and compatibility
`impl-ranking.json`, `tui-ranking.json`. Verified all five absent. Worker Briefs, run
records, test logs, and reusable live fixtures remain.

The local project policy Gate 10% / Margin 20% change is retained separately on
this prototype branch. It must stay off main. No production merge is authorized.

Herdr state at checkpoint: the Git worktree still exists at
`/private/tmp/delegate-monitor-herdr`, but workspace `w2T` and pane `w2T:p2`
are already closed. No pane was closed by this wrap-up. On resume, use the Herdr
skill and installed help to reopen this existing worktree without changing focus.
Inspect plugin linking before relaunch; do not open the WIP for editing until its
checks pass. The dashboard was not merged to main; main receives only a CLAUDE.md
restart-pointer update for this checkpoint.
