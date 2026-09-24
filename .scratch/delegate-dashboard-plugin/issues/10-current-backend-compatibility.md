# 10 — Current backend compatibility

**What to build:** Update the accepted Herdr dashboard prototype to current main;
show sourced metering state and the effect of metering off; route project edits
through the canonical catalog boundary while retaining the dashboard's project
write restrictions and stale-editor protection. Keep the existing prototype scope.

**Blocked by:** None — prototype accepted and Orin approved this pass on 2026-09-17.

**Status:** implemented 2026-09-18 (`e428385`, `040e136`, `3b3e00d`, `91c2ef1`, review fixes) on `worktree/delegate-monitor-herdr` — all boxes ticked; Orin's review of the updated prototype is open. Open, Orin's: the one decision below (project saves keep the canonical `catalog.edit_catalog` document shape).

- [x] Current main is merged into the isolated prototype branch; main and the Rust monitor are preserved.
- [x] Metering on/off and its source are visible; off explains inactive Gate/Margin/Pace and cached observations.
- [x] Gate, Margin and Project order use revision-checked catalog edits without vendor probes.
- [x] Editor snapshots, unrelated keys, no-op bytes, fresh-global validation and project path restrictions are preserved.
- [x] Behavioral regression checks and a disposable live Herdr check pass.
- [x] Independent review findings are adjudicated and fixed; context and evidence are current.

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

## Implemented, 2026-09-18

`/private/tmp` was cleared between sessions: the checkout and
`/private/tmp/delegate-dashboard-compat/` were lost, the branch was intact. The
checkout now lives at Herdr's default path
`~/.herdr/worktrees/dotfiles/worktree-delegate-monitor-herdr`, and the plugin link
points there. The convention is `docs/agents/worktrees.md` on main. The reusable
Briefs, `make_live_fixture.py` and `verify_no_probes.py` are in the git-ignored
`.scratch/delegate-dashboard-plugin/_work/`.

**Decision, against the checkpoint note above:** the adapter keeps the document shape
that `catalog.edit_catalog(scope="project")` writes: the complete moved Tier, the
already-named lanes of other Tiers, and no injected `version`. The alternative was a
second writer that disagrees with `catalog.py order --scope project` for the same
action. The spec's purpose holds and is now tested directly: a move never changes
the effective Order of another Tier. The two failing tests were rewritten to prove
more, not less (canonical-plan equality, other-Tier rows, unrelated keys, rank reads
the new Order). Orin may overrule this at review.

Dispatch, by `/delegate` ranking (Codex under the Gate at 1%, agy Meter unknown):
- model adapter and tests: `grok46-high@grok`, 815 s, run `20260918T133056Z-…-56586336`, verdict clean.
- metering display, own sibling worktree `worktree/delegate-monitor-herdr-tui`, merged as
  `3b3e00d`: `grok46-high@grok`, 427 s, run `20260918T133056Z-…-dd2d31bc`, verdict clean.
- independent review, different Model family: `flash-high@agy`, 332 s, run
  `20260918T134545Z-…-28f4374e`, verdict findings.

Review adjudication (six findings; areas 1, 3, 4, 5 clean):
1. Accepted, fixed: a global Gate/Margin edit during percentage entry now conflicts
   (`PercentageEdit.global_signatures`).
2. Accepted, fixed: an identical `save_project_policy` proposal is a no-op save.
3. Accepted, fixed: the validation-rejection test now asserts the validator's message.
4. Recorded, no change: a symlink swapped in between `edit_catalog`'s last revision check
   and its write is followed. That is the canonical backend on main, and the context
   file already says the byte check is not a filesystem lock.
5. Rejected: a global change in another Tier does not make a move stale; `edit_catalog`
   plans from a fresh snapshot, and the moved Tier is compared with a fresh catalog.
6. Rejected: the Order test also asserts the literal saved list and the file on disk.

Checks, all run by the lead after the workers returned: `test_dashboard.py` 42 passed;
`test_catalog.py` and `test_rank.py` pass; `verify_no_probes.py` reports no process,
socket or URL call during refresh, a move and two percentage saves.

Live Herdr check, disposable fixture of ticket 09 (A/B in Tier 1, G at 5%/O in Tier 2),
plugin split `w2Z:p2` opened with `--no-focus`, closed with `q`:
- `J`/`K` moved A down and back; the file held `project_order` for Tier 1 only and
  Tier 2 stayed `g` (global fallback) with its leader unchanged.
- Margin 10% marked B `stolen by pace: 0.95 >= 0.8 + 0.1`; 20% restored A.
- Gate 1% made G lead Tier 2; Gate 101% showed an error with bytes unchanged; saving
  the stored Gate again kept the same hash and mtime.
- An external note edit during Gate entry gave Conflict and kept the external bytes.
- `"meters": false` in global routing, then in project routing (and project `true` over
  global `false`): the header showed `Meters off|on [source]`, Gate and Margin `inactive`,
  the effect line, `Remaining 5% cached`, and G became the Tier 2 pick with no Gate veto.
  Margin stayed editable while off.
- Fixture `lanes.json`, global `routing.json` and `usage.json` hashes were unchanged at the
  end. The live `~/.cache/delegate/usage.json` changed once at 09:46:46; by timing that is
  the review worker's start probe, and the no-probe helper covers the dashboard itself.
- Found and fixed in this check: a narrow pane clipped the Meters source (`91c2ef1`).

Not done: popup placement was not opened live (as in ticket 09). No merge to main; the
branch's Gate 10% / Margin 20% project policy stays off main.
