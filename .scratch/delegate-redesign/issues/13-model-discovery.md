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

**Status:** landed 2026-09-10 (`7123899`, `1ab5cb2`). All boxes ticked. `discover.py --efforts <model>` generated the 19 effort lanes the catalog now carries (`bc0f773`), and it is what established that grok and agy expose no effort dial at all.

- [x] `scripts/discover.py` lists every model each present harness offers, with its lane or `none`
- [x] It names lanes whose model no longer appears in the harness
- [x] It exits 0 regardless of what it finds, and supports `--json`
- [x] A missing harness binary is reported as missing, not an error
- [x] `tests/test_discover.py` drives it from captured fixture output for all three harnesses; no network, no live CLI
- [x] The wizard start screen shows the no-lane list (ticket 12)

## Landed 2026-09-10

`scripts/discover.py` (466 lines) and `tests/test_discover.py` (14 assertions,
all fixture-driven). Fixtures in `tests/fixtures/discover/` are real output
captured from the three live CLIs on 2026-09-10; the codex one is pruned to the
fields the script reads, values unaltered.

Two decisions taken while building it:

- Only codex models with `visibility: "list"` are reported. `gpt-reserve` and
  `codex-auto-review` are `"hide"` — internal, never offered to a human.
- A catalog that fails to validate is a warning on stderr and an empty lane map,
  not an exit code. The script is a report; refusing to run would make it a gate.

The start screen notice followed the same day. `setup.py` passes either the
`discover()` dict or a string saying why discovery did not run — one shape, decided
at the call site — and the start screen prints the models with no lane and the lanes
whose model is retired, counted and truncated to the width. No drift says so in a
line of its own, because a silent absence and a failed probe must not look the same.
Discovery shells out to three harness CLIs, so any failure becomes that reason
string and the wizard carries on; `--no-discover` skips it.

The orientation prose was compressed from fourteen body lines to ten. Fourteen did
not fit the 80x16 minimum the wizard enforces, and the first pass had reacted by
changing the global layout arithmetic for every screen; trimming the start screen
was the right half of that trade.
