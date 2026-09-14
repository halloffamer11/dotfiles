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

**Status:** ready-for-agent

- [ ] The plugin manifest declares one pane entrypoint that accepts Herdr's supported placements.
- [ ] Launch resolves the invoking project and the dashboard shows that identity; changing Herdr focus afterwards does not change it.
- [ ] One task-runner target prepares, links and opens the plugin as a split beside the current pane, and is documented where the Makefile documents its targets.
- [ ] The manifest contains no ranking, catalog or Meter logic.
- [ ] The Shift-U popup configuration is unchanged.
