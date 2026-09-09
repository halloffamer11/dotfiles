# 13 — Deterministic model discovery

**What to build:** A small script that lists what each harness offers and says which of those models have no lane. Nothing more. It reports; the human decides.

`gpt-6-astra` has been priority 1 in Orin's Codex CLI for some time and had no lane until 2026-09-09, so the wizard could not show it and ranking could never pick it. Nothing in the tool noticed. The 2026-09-08 assessment recorded the same gap and it went unfixed because no one was looking.

`scripts/discover.py`:

- Runs the list command for each harness present on PATH: `codex debug models` (JSON on stdout), `agy models`, `grok models`. Claude lanes are named by hand and have no list command; say so rather than guessing.
- Prints one line per model: harness, slug, and `lane: <name>` or `lane: none`. Then a short tail naming the slugs with no lane, and any lane whose model no longer appears in its harness — drift runs both ways, and a lane pointing at a retired slug fails only at dispatch time.
- Exits 0 whether or not drift exists. This is a report, not a gate; a non-zero exit would make it a blocker in something else's pipeline eventually.
- `--json` for machine reading, matching `rank.py`'s flag.

Keep it deterministic and dumb: no ranking, no tier guesses, no writes to the catalog. Authoring a lane needs a meter, a weight, a timeout and a price, which is a human's job and one `catalog.py` already validates.

The wizard's start screen (ticket 12) shows the same "no lane" list as a notice, so the human meets drift at the moment they are already deciding tiers.

**Blocked by:** nothing.

**Status:** open, raised by Orin 2026-09-09: "we need a deterministic script to discover new models. this should be simple."

- [ ] `scripts/discover.py` lists every model each present harness offers, with its lane or `none`
- [ ] It names lanes whose model no longer appears in the harness
- [ ] It exits 0 regardless of what it finds, and supports `--json`
- [ ] A missing harness binary is reported as missing, not an error
- [ ] `tests/test_discover.py` drives it from captured fixture output for all three harnesses; no network, no live CLI
- [ ] The wizard start screen shows the no-lane list (ticket 12)
