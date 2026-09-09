# 04 — The `/delegate` skill

**What to build:** `/delegate <class> <brief>` is the one entry point that reads meters. It ranks, prints the ordered lanes with reasons, and dispatches the pick as a background run so the session keeps working and reads `return.json` when notified. `--dry-run` stops after the print. `--effort` overrides the lane's effort dial for one job without changing its tier. Meters are probed at run start and at run finish. The skill file explains the class vocabulary and the two configuration files in the words of the spec.

**Blocked by:** 02 Ranking over the catalog; 03 One run through an ADS relay.

**Status:** landed 2026-09-09 in the working tree (uncommitted)

- [x] `/delegate scout <brief>` prints the ranking and starts a run in the background; the session is notified on exit and reads the return file
- [x] `--dry-run` prints the ranking and starts nothing
- [x] `--effort low` on a high-effort lane passes low to the relay and the lane's tier is unchanged in the print
- [x] When no lane is eligible the skill stops with the reasons and starts nothing
- [x] The skill reads no environment variable and no `mode` or `balance` setting
- [x] The Workflow path is documented as courier-optional, not required
