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
A capability level from 1 (lowest) to 4 (frontier) that Orin gives each lane in setup. It belongs to the lane, not the model.

**Order**:
A lane's place inside its tier, from 1, that Orin sets on the setup wizard's review page. Ranking sorts by tier, then order, then pace, then lane name; a lane without an order comes after every lane with one.
_Avoid_: priority, rank (when you mean the order)

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
The lower of a meter's two window fractions still unspent.
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
