# 0001 Settled delegate decisions

Orin settled each of these. Do not reopen one without him. Each keeps its date and
its ticket, where the reason is.

- `lanes.json` and `routing.json` both ship in this public repo via `stow/delegate/`.
  Orin ruled the subscription costs and vendor notes non-sensitive, so no split to a
  forge and no constraint on what the pre-screen may write (2026-09-10).
- `trust` is gone from the design entirely. Ranking sorts
  `(tier asc, order asc, pace desc, lane name asc)`, where `order` is the lane's place
  inside its tier from the wizard's review page and a lane without one sorts after
  every lane with one; the name term is an arbitrary deterministic tie-break. A steal
  by `margin` can happen inside a tier, which is the load balance; a catalog with no
  `order` ranks as before (tickets 01, 02 and 28).
- Each class has a floor and a ceiling; the floor is the default, and tier 4 is
  reached only by naming a lane until setup says otherwise. Tiers are what Orin sets:
  tests check the rule on fixtures, never his tiers (ticket 22).
- The Delegation section of `~/.claude/CLAUDE.md` is gone (2026-09-11); the skill is
  the only routing rule, and "Fable never runs as a worker" went with it.
- One decision per line on each page, with the same `[x]`/`[ ]` marker on every
  page: the carry page selects a model at an effort, the tier pages assign a tier,
  and no page asks a question another page already asked (Orin, 2026-09-10). TUI
  work goes to a Claude Opus agent under `/frontend-design:frontend-design`.
- `stow/delegate/.config/delegate/lanes.json` is the authoritative catalog; the live
  `~/.config/delegate/lanes.json` follows it, never the other way (Orin,
  2026-09-10).
- `ultra` lanes are generated disabled: no source scores them, and automatic task
  delegation contradicts the worker preamble (ticket 15).
- The carry page proposes a lane off when another effort of the same model, for no
  more money, beats it on more than half of the benchmarks one source scored both
  on. The AA composite index is shown and never counted (Orin, 2026-09-11, ticket
  18).
- The benchmark page's frontier is a display aid, not a rule: nothing reads it, and
  the carry rule above is the only thing that proposes a lane off (ticket 24).
- A new generation supersedes the old one, and every current-generation model shows
  for screening, at every effort (Orin, 2026-09-22; tickets 33 and 35). agy shows only
  its Gemini models. Orin: "ignore the Gemini Claude pool".
- Effort is fixed per Lane, and ranking picks a Lane, never an effort. The one path
  for a different effort is a named `dispatch --effort` (Orin, 2026-09-22; the comment at
  the Pick in `rank.py`).
