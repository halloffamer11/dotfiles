# 04: Portable Linux and Omarchy bootstrap

**What to build:** On Linux, one bootstrap command applies the supported
machine-agnostic layer. It gives Omarchy its repository-owned Linux
configuration and gives other Linux systems the conservative common subset,
without claiming to provision every distribution's system packages.

**Blocked by:** 01 Portable skill reconciliation; 02 Platform-safe configuration
profiles.

**Status:** ready-for-agent

- [ ] Bootstrap checks for Git, Make, GNU Stow, Node.js, and npm before changing
      the home directory, and names the missing prerequisites without prescribing
      an unverified distribution command.
- [ ] Omarchy bootstrap reconciles the Omarchy profile, repository-owned skills,
      Claude agents, and the declared external skills.
- [ ] Generic-Linux bootstrap reconciles the common profile and the same skill
      layer without selecting Omarchy-specific configuration.
- [ ] Neither Linux profile invokes macOS casks, Borders, Hammerspoon, Swift audio
      builds, or any other macOS-only operation.
- [ ] The result states that Linux system-package installation remains owned by
      the distribution or the operator.
- [ ] Automated isolated-home checks prove both Linux profiles and idempotent
      reruns.
