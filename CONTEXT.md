# Dotfiles

Machine configuration and agent tooling. Today the terms below belong to delegate,
which is the routing of worker jobs to external or native models by capability and
remaining subscription usage.

## Delegate: who runs a job

**Harness**:
A CLI that runs models: `claude`, `codex`, `agy`, or `grok`.

**Orchestrator harness**:
The harness that runs the session that plans, dispatches, and checks results. Today it is always Claude Code.
_Avoid_: lead harness, parent

**Model**:
One vendor model, such as `gpt-5.6-luna` or `claude-opus-5`.

**Effort**:
How hard a model reasons on one job: low, medium, high, xhigh, or max. Not every model accepts every level.

**Level**:
A model's slug with its version taken out: `gpt-6-sol` and `gpt-5.6-sol` are both level `gpt-sol`. One level is one line of models, at one version each.
_Avoid_: family (when you mean the level), tier

**Superseded**:
Said of a model that its harness replaces — codex names the replacement — or that another model of the same level, at a higher version, replaces. Its lanes leave the catalog at the next setup save.
_Avoid_: retired (which is a model the harness no longer lists at all), deprecated

**Generation**:
The models of a harness that are not superseded. Setup shows every current-generation model of every harness on the carry page, at every effort.

**Lane**:
One model at one effort on one harness, named `<model-effort>@<harness>`. It is the unit that gets a tier and that ranking picks.
_Avoid_: route, worker, model (when you mean the lane)

**Carried lane**:
A lane that setup keeps in ranking.
_Avoid_: active lane

**Dominated**:
Said of an effort when another effort of the same model scores at least as well at no more cost. Setup proposes a dominated effort off.

**Published name**:
The name a benchmark source prints for a model, when it differs from the model's own name.

**Native lane**:
A lane that runs as a subagent inside the orchestrator harness.

**Relayed lane**:
A lane that runs as a separate CLI process through a relay.

**Relay**:
The program that runs one job on a harness CLI in a separate process and returns the result.

**ADS**:
The package that provides the relays: `amElnagdy/delegate-skills`, used through the fork `halloffamer11/delegate-skills` at a pinned commit. The letters are not spelled out anywhere.
_Avoid_: ADS as a name for the concept; say relay

## Delegate: capability

**Tier**:
A capability level from 1 (lowest) to 4 (frontier) that Orin gives each lane in setup. It belongs to the lane, not the model. A project may set its own Tier for a lane, and everything that reads a Tier — the Class range, the Gate, Overflow, the Tier leaders — reads the effective one.

**Project tier**:
The Tier a project sets for a lane in `.delegate/lanes.json`, for jobs in that project only. It is the one lane field a project may set; every other field, `enabled` and Order included, stays global. A lane the project moves has no place in its new tier until Project order gives it one.

**Order**:
A lane's place inside its tier, from 1, that Orin sets on the setup wizard's review page. Ranking sorts by tier, then order, then pace, then lane name; a lane without an order comes after every lane with one.
_Avoid_: priority, rank (when you mean the order)

**Project order**:
A project's preferred order for lanes inside their effective tiers. It overrides Order for jobs in that project. It does not change a lane's Tier; a Project tier does that.

**Tier leader**:
The lane ranking selects when selection is restricted to one Tier. It is a preview for that Tier, not the Pick for a Class range.

**Class**:
The kind of job: scout, mechanical, impl, review, or hard-impl.
_Avoid_: task type, category

**Floor**:
The lowest tier a class accepts. It is the default for each job of that class.
_Avoid_: need, minimum tier

**Ceiling**:
The highest tier a class accepts. It is extra capability for when a job needs it, and the most the class can ever get.
_Avoid_: cap, max tier

**Range**:
The tiers from the floor to the ceiling of a class. It is the normal range of operation for that class.
_Avoid_: band

**Overflow**:
Admitting the tier above a class's ceiling for one job, when subscription usage
is the only thing stopping the range: at least one carried lane in it is under
the gate, and every veto there is a gate veto or an absent harness CLI. A lane
whose CLI is absent counts like a lane switched off, because the catalog is
shared across machines and this one cannot run that lane. Overflow steps one
tier at a time, never goes below the floor, and never reaches tier 4. Any other
veto in the range, and a range with no gated lane in it, stop the job instead.
The routing key `overflow` turns it off.
_Avoid_: fallback, escalation, exception

**Named dispatch**:
A job sent to a lane the caller chose. Ranking and the range are skipped.

## Delegate: usage

**Meter**:
One subscription quota. Each lane uses exactly one meter, and many lanes can share a meter.
_Avoid_: quota (when you mean the meter)

**Meter weight**:
How much of its meter one job on a lane uses, compared with other lanes. It feeds the report, not the ranking.

**Window**:
One quota period of a meter: 5-hour or weekly.

**Remaining**:
The fraction of a Meter still unspent: the lower of its Window fractions, and the
one Window's fraction when a Meter has only one. Remaining is unknown only when no
Window was read. Where no vendor joins the two Windows, the lower one is an
assumption, and the Meter's note says so.
_Avoid_: r (in prose)

**Gate**:
The lowest remaining a meter may have and still take a job.

**Pace**:
The rate a meter can afford from now to its weekly reset, divided by the rate of an even spend across the whole week. It comes from one reading: 1.0 is on track, and above 1 means quota will expire unspent.
_Avoid_: velocity, speed, burn rate

**Burn rate**:
How fast a meter's remaining falls, measured across readings over time.

**Margin**:
How much higher a lane's pace must be to take a job from the pick when it sorts after the pick: at a higher tier, or lower in the order of the same tier.

**Pick**:
The one lane ranking selects for a job: the first lane by tier, order, pace and lane name, unless a lane after it has a pace higher by the margin.

## Delegate: one job

**Brief**:
The task file the orchestrator writes for one job.

**Run**:
One dispatch of a brief and its directory, never reused.

## Delegate: browsers

**Disposable browser**:
A fresh browser that Playwright starts for one run, with no logins and no saved state. A worker may read and write in it.

**Agent profile**:
A browser profile kept only for workers and signed in to a few chosen accounts, reached through the Playwright extension. Workers never reach the human's personal profile; the extension is installed only in the agent profile.
_Avoid_: live browser, authenticated browser
