# 01: Portable skill reconciliation

**What to build:** One supported skill reconciliation operation works on macOS
and Linux. It installs the Claude agents and the declared skills (the personal
ones from `halloffamer11/skills`, plus Herdr and Humanizer) without making an
optional Homebrew-provided skill a prerequisite for the whole operation. This
repository owns no skills since the 2026-10-01 split, and delegate has its own
installer.

**Blocked by:** None (can start immediately).

**Status:** built and merged 2026-10-04.

- [x] One command reconciles the declared skills and Claude agents into the
      supported harness locations on macOS and Linux: `make skills externals`
      (both are in `make apply`).
- [x] Herdr and Humanizer are installed or refreshed from their declared upstream
      repositories through the current `skills` CLI, with no CLI or skill version
      pin (`skills@latest`, no `@version` on any skill).
- [x] Only the intended Claude Code, Codex, and Kiro CLI integrations are created
      (`SKILL_AGENTS`).
- [x] If Homebrew or Hunk is absent, the optional Hunk skill is skipped with a
      clear notice and all other skills still reconcile successfully.
- [x] Repeating the operation is idempotent, and automated checks prove the
      result against an isolated home directory: `make test-bootstrap` runs
      `tests/bootstrap/skills.sh`, with stub `npx` and `brew`.
