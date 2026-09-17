# 01: Portable skill reconciliation

**What to build:** One supported skill reconciliation operation works on macOS
and Linux. It installs the skills owned by this repository, the Claude agents,
and the declared external Herdr and Humanizer skills without making an optional
Homebrew-provided skill a prerequisite for the whole operation.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] One command reconciles repository-owned skills and Claude agents into the
      supported harness locations on macOS and Linux.
- [ ] Herdr and Humanizer are installed or refreshed from their declared upstream
      repositories through the current `skills` CLI, with no CLI or skill version
      pin.
- [ ] Only the intended Claude Code, Codex, and Kiro CLI integrations are created.
- [ ] If Homebrew or Hunk is absent, the optional Hunk skill is skipped with a
      clear notice and all other skills still reconcile successfully.
- [ ] Repeating the operation is idempotent, and automated checks prove the
      result against an isolated home directory.
