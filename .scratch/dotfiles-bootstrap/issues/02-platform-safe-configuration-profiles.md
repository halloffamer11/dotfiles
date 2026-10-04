# 02: Platform-safe configuration profiles

**What to build:** Configuration reconciliation selects a macOS, Omarchy, or
generic-Linux profile. Each machine receives the shared configuration plus only
the platform configuration that can operate there, while retaining an explicit
profile override for machines that cannot be identified automatically.

**Blocked by:** None (can start immediately).

**Status:** built and merged 2026-10-04; waiting on one check
on omarchy: if its `local.mk` sets `CONFIG_PACKAGES`, that list still wins over
the profile; delete the line to let the omarchy profile choose.

- [x] macOS receives the current shared configuration, Borders configuration,
      and whole-directory Hammerspoon link with no regression in the existing
      result: the macOS package list is exactly the old default.
- [x] Omarchy receives the shared configuration plus its Bash, Ghostty, Herdr,
      Hyprland, and Voxtype configuration, and receives no macOS-only artifact
      (no Borders, WezTerm, zsh or Hammerspoon link).
- [x] Generic Linux receives only the configuration declared portable
      (`COMMON_PACKAGES`: claude, git, nvim, starship, yazi), and the result
      names the packages it did not select.
- [x] Automatic profile selection has a documented explicit override:
      `make PROFILE=linux ...` or a `PROFILE` line in `local.mk` (Makefile header).
- [x] A dry run against isolated home directories proves the selected links for
      all three profiles and reports existing-file conflicts without modifying
      them: `make configs-plan`, checked by `tests/bootstrap/configs.sh`.
