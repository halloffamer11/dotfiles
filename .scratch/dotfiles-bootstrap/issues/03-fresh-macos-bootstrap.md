# 03: Fresh macOS bootstrap

**What to build:** After Apple command-line tools, Homebrew, and the repository
clone exist, one bootstrap command provisions a new Mac with the repository's
packages, configuration, skills, macOS audio helpers, and isolated Delegate
Codex home.

**Blocked by:** 01 Portable skill reconciliation; 02 Platform-safe configuration
profiles.

**Status:** ready-for-agent

- [ ] Node.js and npm are part of the declared macOS package state, so external
      skill installation does not depend on an undeclared prerequisite.
- [ ] The bootstrap command installs or upgrades the declared Homebrew state,
      reconciles the macOS configuration and skills, builds both audio helpers,
      and creates Delegate's isolated Codex home.
- [ ] A missing Homebrew installation stops before partial provisioning and gives
      the operator the supported starting instruction.
- [ ] Existing home-file conflicts are reported with safe recovery guidance;
      bootstrap never adopts or overwrites them silently.
- [ ] Missing Codex authentication is a clear non-fatal follow-up, and rerunning
      the relevant operation after login completes that integration.
- [ ] Automated checks prove the macOS command graph and an end-to-end isolated
      home run without changing the operator's live home directory.
