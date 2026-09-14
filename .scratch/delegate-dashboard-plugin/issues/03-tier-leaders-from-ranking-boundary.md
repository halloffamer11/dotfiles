# 03 — Tier leaders from the ranking boundary

**What to build:** One canonical operation, and a command-line view of it, that returns
the Tier leader and the ranked rows for each exact Tier (1 to 4), from the effective
catalog, the Meter observations and the available harnesses. It uses the rule from
ticket 02 restricted to one Tier, so the leader cannot drift from what delegate would
pick inside that Tier. A Tier leader is a preview for that Tier, not the Pick for a
Class range, and the view says so. It never probes a vendor beyond the normal cached
usage read and never dispatches.

Part of [01 Prototype the project delegation dashboard](01-prototype-project-delegation-dashboard.md).
Lands on `main`.

**Blocked by:** 02 Split the ranking rule from Class filtering

**Status:** ready-for-agent

- [ ] One operation returns, for each of the four Tiers, the Tier leader (or none) and every lane row with eligibility and reason.
- [ ] A command prints that result for the current project, in text and JSON.
- [ ] Tests on fixtures cover: the first eligible lane in Order leads; a lane below Gate is vetoed and the next lane leads; a later lane steals by Margin inside the Tier; an unknown Meter keeps its existing safe behavior; a missing harness is vetoed; lane name breaks ties deterministically; a Tier with no eligible lane has no leader.
- [ ] Tests assert the rule on fixtures, never Orin's live tiers.
