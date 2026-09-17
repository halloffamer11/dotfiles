# 05: One maintenance and verification workflow

**What to build:** After initial bootstrap, the operator has the same simple
maintenance vocabulary on macOS and Linux: pull repository changes, reconcile
the detected profile and all skill sources, update the package layer where it is
supported, and diagnose drift without changing the machine.

**Blocked by:** 03 Fresh macOS bootstrap; 04 Portable Linux and Omarchy bootstrap.

**Status:** ready-for-agent

- [ ] The `dots` workflow is available in the supported macOS and Omarchy shells
      and pulls the repository before reconciling the selected configuration and
      skill state.
- [ ] Routine reconciliation refreshes the unpinned external Herdr and Humanizer
      skills, so they do not depend on a separately remembered update command.
- [ ] Package updating is platform-safe: macOS reconciles its Homebrew state,
      while Linux does not mutate distribution packages that this repository does
      not own.
- [ ] A read-only diagnostic reports the selected profile, missing prerequisites,
      conflicting files, broken managed links, and external-skill drift with a
      non-zero status when action is required.
- [ ] The operator guide gives separate fresh-machine and maintenance sequences
      for macOS, Omarchy, and generic Linux, including the credentials and
      permissions that remain manual.
- [ ] Smoke checks cover all supported profiles and prove that diagnostic and
      maintenance command selection does not write to the test runner's live home
      directory.
