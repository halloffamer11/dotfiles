# Worktrees: Herdr location, `.scratch` names

One slug ties an effort's tickets, branch, worktree and Herdr workspace together.
Herdr owns the location; `.scratch/` owns the name.

## Conventions

- The slug is the effort's directory name: `.scratch/<effort-slug>/` (see
  `issue-tracker.md`).
- The branch is `worktree/<effort-slug>`. A worker that needs its own checkout gets a
  sibling `worktree/<effort-slug>-<part>` based on the effort branch, merged back into
  it, then removed.
- The checkout is always Herdr's default path,
  `~/.herdr/worktrees/<repo>/worktree-<effort-slug>`. Never pass `--path`, and never use
  `/tmp` or `/private/tmp`: macOS clears them, and a cleared directory takes uncommitted
  work with it.
- The Herdr workspace label is the slug.
- Disposable files of an effort (worker Briefs, live fixtures, logs) go in
  `.scratch/<effort-slug>/_work/` inside the worktree. Git ignores `_work/`, so it
  survives a restart and goes away with the worktree. Accepted evidence still goes in
  `_data/` or `research/`.

## Commands

Run these from a Herdr pane in the primary checkout. Each returns JSON; read IDs and
paths from it.

- Create: `herdr worktree create --cwd "$PWD" --branch worktree/<slug> --base main --label <slug> --no-focus`
- Reopen a closed workspace: `herdr worktree open --cwd "$PWD" --branch worktree/<slug> --label <slug> --no-focus`
- Remove after the merge: `herdr worktree remove --workspace <id>`, then delete the branch.
- Find them: `herdr worktree list --cwd "$PWD"`.

A worktree is a blast radius for a delegate worker (`delegate.py --write <path>`); the
primary checkout never is.

## Exception on record

`worktree/delegate-monitor-herdr` holds the `.scratch/delegate-dashboard-plugin/` effort.
The branch predates this rule and keeps its name; its checkout moved from `/private/tmp`
to the Herdr path on 2026-09-18.
