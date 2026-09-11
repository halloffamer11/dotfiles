# 19 — Every effort a harness offers is a lane, on all four harnesses

**What to build:** Discovery knows each harness's effort list, so `--efforts`
prints a stanza per effort for a claude, agy or grok model the way it already
does for codex, and the catalog refuses a lane at an effort its harness does not
offer. After this, the wizard's carry page shows Fable, Grok 4.6 and Gemini 3.8
Flash at every effort their CLIs accept, and the harness page reports
`gemini-3.8-flash-medium` as an effort of one model, not as a model with no lane.

**Why it is missing.** Ticket 15 enumerated efforts from the one place
`discover.py` reads them: the JSON of `codex debug models`. The other three
harnesses were never given an effort list, and the ticket recorded that
"per-harness effort policing is a separate decision and was deliberately not
taken". So the catalog has 26 lanes, 24 of them codex, and one lane each for the
other three harnesses.

What each harness offers, verified 2026-09-11 with `--help` and the pinned relays:

    harness  efforts the CLI accepts                     discover.py reads   lanes today
    codex    low medium high xhigh max ultra (its JSON)  the JSON            6 per model
    claude   --effort low medium high xhigh max          nothing             xhigh only
    grok     --reasoning-effort (alias --effort);        nothing             high only
             values not listed in --help
    agy      effort is in the slug: gemini-3.8-flash-    three separate      high only
             high / -medium / -low; --effort low|medium|  models
             high also exists but the relay does not
             pass it and delegate.py ignores an override

The relays already forward the effort for claude and grok, so the nine missing
lanes run as soon as they exist. Artificial Analysis measures Grok 4.6 at low,
medium, high and xhigh, which suggests four, but that is a benchmark's list, not
the harness's: one verified probe of grok's accepted values comes first.

**Why validation belongs here.** `catalog.py` accepts any of the six efforts on
any harness, and `delegate.py --effort` does too. Generating `fable-max@claude`
without a per-harness rule means `fable-ultra@claude` is equally accepted, and
claude does not offer it. The rule is a small table beside the effort lists this
ticket adds.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `discover.py` has one effort list per harness: codex from its JSON, claude from its CLI, agy from the slug suffix family (`strip_effort_suffix` already knows it), grok from a probe of its accepted values recorded in the ticket with the command that proved it
- [ ] `--efforts claude-fable-5-1`, `--efforts grok-4.6` and `--efforts gemini-3.8-flash-high` print ready-to-paste stanzas, one per effort, with the shared price block; an agy stanza puts the effort in the model slug, since that is how agy carries it
- [ ] Discovery reports the agy slug family as one model with efforts, so the harness page and the start page's drift line stop listing `flash-medium` and `flash-low` as models with no lane
- [ ] `catalog.py check` rejects a lane whose effort its harness does not offer, and `delegate.py --effort` rejects the same override, each with a message naming the harness's list
- [ ] The nine stanzas pasted into a copy of the stowed catalog pass `check`, and the carry page lists all of them with a `why`
- [ ] The existing 26 lanes still pass `check`; the fixtures for the three harnesses cover the new lists
