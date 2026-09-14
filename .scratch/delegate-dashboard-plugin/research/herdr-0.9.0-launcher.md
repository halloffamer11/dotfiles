# Herdr launcher checks, 2026-09-14

The installed client and server report 0.9.0, protocol 22, compatible, with no
restart needed (`herdr status`).

The [official plugin documentation](https://herdr.dev/docs/plugins/) specifies an
argv command in `herdr-plugin.toml`, runtime context in
`HERDR_PLUGIN_CONTEXT_JSON`, and five pane placements. Commands start in the
plugin directory; that directory must not be mistaken for the project.

The installed CLI's `herdr plugin pane open --help` accepts split, tab, zoomed,
and overlay. It does not accept popup. The installed socket schema does include
popup in `PluginPanePlacement`; use the socket operation for that placement.

Verified schema fields:

- `PluginInvocationContext`: `focused_pane_cwd`, `workspace_cwd`, `worktree`.
- `WorkspaceWorktreeInfo`: `checkout_path`, `repo_root`, `is_linked_worktree`.
- `PluginPaneOpenParams`: `plugin_id`, `entrypoint`, `target_pane_id`,
  `workspace_id`, `cwd`, `placement`, `direction`, `env`, `focus`, `width`, `height`.

Inspect the local schema with `herdr api schema --json`; the definitions are at
`schemas.request.$defs`. The [socket documentation](https://herdr.dev/docs/socket-api/)
describes newline-delimited request/response transport. Use the launch context
once, then pin the resolved project for the dashboard's lifetime.

Normal split launch uses an explicit target and `--no-focus`. For live checks,
only close panes created by this task. Keep policy edits in a disposable fixture.
