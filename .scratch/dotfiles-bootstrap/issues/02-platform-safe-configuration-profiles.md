# 02: Platform-safe configuration profiles

**What to build:** Configuration reconciliation selects a macOS, Omarchy, or
generic-Linux profile. Each machine receives the shared configuration plus only
the platform configuration that can operate there, while retaining an explicit
profile override for machines that cannot be identified automatically.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] macOS receives the current shared configuration, Borders configuration,
      and whole-directory Hammerspoon link with no regression in the existing
      result.
- [ ] Omarchy receives the shared configuration plus its Bash, Ghostty, Herdr,
      Hyprland, and Voxtype configuration, and receives no macOS-only artifact.
- [ ] Generic Linux receives only the configuration declared portable, and the
      result identifies optional packages that were not selected.
- [ ] Automatic profile selection has a documented explicit override.
- [ ] A dry run against isolated home directories proves the selected links for
      all three profiles and reports existing-file conflicts without modifying
      them.
