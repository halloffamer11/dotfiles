# 06 — Workers can use the agent profile on the Mac

**What to build:** Workers on all four harnesses can use the agent profile — the Helium profile "GenAI", signed in to a few accounts Orin chose — through the Playwright extension, and only for the sites and actions a brief names. Orin chose to have it on every run for all four harnesses. The guard is the worker preamble and the brief. Workers never reach Orin's personal profile, because the extension is installed only in GenAI.

Facts and setup rules: `../research/2026-09-10-browser-routes.md`.

**Blocked by:** 01, 02, 03 and 04.

**Status:** open, ready-for-agent, raised by Orin 2026-09-10

- [ ] The worker preamble allows the agent profile only for the sites and actions the brief names, and not otherwise.
- [ ] The delegate `SKILL.md` tells the session how a brief names those sites and actions.
- [ ] Setup on the Mac, in conversation with Orin: the Playwright extension in Helium GenAI only, and an `agent-browser` server in all four harness configs following the setup rules. The token stays on the machine; a search of the repo finds no token.
- [ ] A manual check recorded here shows the personal profile has no Playwright extension.
- [ ] Proof on the Mac: all four agent-profile rows pass with Helium open on GenAI, and the disposable rows still pass.
