# 07 — Agent-profile parity on omarchy

**What to build:** Workers on all four harnesses can use an agent profile on omarchy, as they can on the Mac. Helium on omarchy has one profile, "You", so the GenAI profile is new there. Whether Helium on Arch accepts the Playwright extension has not been checked yet.

Facts and setup rules: `../research/2026-09-10-browser-routes.md`.

**Blocked by:** 05 and 06.

**Status:** open, ready-for-agent, raised by Orin 2026-09-10

- [ ] omarchy runs the same delegate code as the Mac, including 06.
- [ ] Setup, in conversation with Orin: a new GenAI profile in Helium on omarchy, signed in to the same accounts, with the Playwright extension installed only there, its token kept on the machine, and an `agent-browser` server in all four harness configs following the setup rules.
- [ ] A manual check recorded here shows omarchy's personal profile has no Playwright extension.
- [ ] Proof: the full probe table on omarchy matches the Mac, carrying any exception recorded in 05.
