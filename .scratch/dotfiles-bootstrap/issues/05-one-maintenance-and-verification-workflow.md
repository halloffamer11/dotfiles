# 05: One maintenance and verification workflow

**What to build:** After initial bootstrap, the operator has the same simple
maintenance vocabulary on macOS and Linux: pull repository changes, reconcile
the detected profile and all skill sources, update the package layer where it is
supported, and diagnose drift without changing the machine.

**Blocked by:** 03 Fresh macOS bootstrap; 04 Portable Linux and Omarchy bootstrap.

**Status:** built 2026-10-04, waiting on Orin's merge of the PR and one
`make doctor` on each machine.

- [x] The `dots` workflow is available in the supported macOS and Omarchy shells
      and pulls the repository before reconciling the selected configuration and
      skill state (zsh and bash aliases; `make apply` follows the profile).
- [x] Routine reconciliation refreshes the unpinned external Herdr and Humanizer
      skills, so they do not depend on a separately remembered update command
      (`apply` runs `externals`, whose `skills add` refreshes an installed skill).
- [x] Package updating is platform-safe: macOS reconciles its Homebrew state,
      while Linux does not mutate distribution packages that this repository does
      not own (`make update`).
- [x] A read-only diagnostic reports the selected profile, missing prerequisites,
      conflicting files, broken managed links, and external-skill drift with a
      non-zero status when action is required (`make doctor`,
      `scripts/doctor.sh`). Drift means a declared skill is missing; checking for
      a newer upstream version would need the network, and `dots` refreshes those
      anyway.
- [x] The operator guide gives separate fresh-machine and maintenance sequences
      for macOS, Omarchy, and generic Linux, including the credentials and
      permissions that remain manual (`docs/bootstrap.md`).
- [x] Smoke checks cover all supported profiles and prove that diagnostic and
      maintenance command selection does not write to the test runner's live home
      directory (`tests/bootstrap/maintenance.sh`).
