# 08 — Herdr plugin launcher and make target

**What to build:** A thin local Herdr plugin (plugin v1 manifest, one terminal pane
entrypoint) that opens the dashboard. It resolves the project from the Herdr invocation
worktree or working directory and passes it to the dashboard, which pins it. The normal
launch is a targeted split beside the invoking pane; the same entrypoint must also open
as a tab, zoomed pane, overlay or popup. The manifest holds no delegate logic, so the
dashboard still runs outside Herdr. One documented task-runner target prepares, links
and opens the local plugin. No marketplace publishing. The Shift-U usage popup stays
unchanged.

Read the Herdr 0.9.0 plugin documentation and `herdr plugin --help` before writing the
manifest; do not guess its fields.

Part of [01 Prototype the project delegation dashboard](01-prototype-project-delegation-dashboard.md).
Throwaway branch only; never merged to `main`.

**Blocked by:** 05 Read-only dashboard pinned to one project

**Status:** implemented 2026-09-14; split and tab launches verified on the prototype branch

**Branch:** `worktree/delegate-monitor-herdr` (initial launcher `b1c4ba7`, integrated as `9c859d6`)

- [x] The plugin manifest declares one pane entrypoint; the opener supports split, tab, zoomed, overlay, and popup placements.
- [x] Launch resolves the invoking project and the dashboard shows that identity; changing Herdr focus afterwards does not change it.
- [x] One task-runner target prepares, links and opens the plugin as a split beside the current pane, and is documented where the Makefile documents its targets.
- [x] The manifest contains no ranking, catalog or Meter logic.
- [x] The Shift-U popup configuration is unchanged.

## Implementation evidence

- `make delegate-dashboard` requires a Herdr pane, links this directory, and opens
  the one `dashboard` entrypoint with `--no-focus`; the default placement is `split`.
- `DELEGATE_DASHBOARD_PLACEMENT=tab|zoomed|overlay|popup make delegate-dashboard`
  selects the corresponding placement. The installed 0.9.0 CLI handles the first
  four; `open.py` sends `plugin.pane.open` over `HERDR_SOCKET_PATH` for `popup`.
- `launcher.py --cwd DIRECTORY` wins over `worktree.checkout_path`, then
  `focused_pane_cwd`, then `workspace_cwd`. It rejects an implicit plugin-root
  selection and passes the resolved directory to `dashboard.py --cwd`.
- Compile, help, TOML parsing, context-resolution fixtures, and `make -n` checks
  passed on 2026-09-14. Live launch and pinning remain unverified until
  `tools/delegate-dashboard/dashboard.py` lands; no Herdr pane was opened here.

## Live integration, 2026-09-14

The worker timed out after writing the launcher; the lead inspected and completed
its integration. `make -C <prototype-checkout> delegate-dashboard` now opens a
split beside the invoking pane. Split `w2C:p4` and tab `w2C:p5` both displayed
`delegate-dashboard-t08`, while the user stayed focused in a different workspace.
Both showed canonical leaders after the invoking shell's PATH was passed through.

The installed CLI requires placement-specific targeting: a split takes a target
pane, a tab takes a workspace. The make target uses the documented `plugin link
PATH` form. The opener passes the invoking pane's cwd explicitly, so `make -C`
does not accidentally select the build directory; explicit `--cwd` wins.
`--config-dir` and `--meters` support disposable acceptance fixtures. These values
travel as launch environment only; the command still starts in the plugin root.
Popup uses the installed socket schema; it has not been opened in the live check.
