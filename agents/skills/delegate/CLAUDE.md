# Delegate

External worker routing lives in this directory. Read `SKILL.md` first, then use these files as the implementation authority:

- `scripts/catalog.py`: the two configuration files (`~/.config/delegate/lanes.json`, `routing.json`, project override `.delegate/routing.json`), validators, `show`/`check`/`fmt`. It also owns the mapping from a benchmark source's printed model name to a lane model (`resolve_published_model`, the lane field `published_as`); `bench.py` and the setup pre-screen both read it from here. `assets/samples/`: the starting catalog from the spec.
- `scripts/rank.py`: the selection rule over the catalog and the live meters (tier ceiling, pace, pace margin).
- `scripts/delegate.py`: one run through a pinned ADS relay (`dispatch`), and rank-then-dispatch (`run`). Run directories under `~/.cache/delegate/runs/`, never reused.
- `scripts/ads.sh`: installs and checks the relay layer, **halloffamer11/delegate-skills** (our fork of amElnagdy) at commit `1ff8bd6129b78124bd0e6e99fb6e4144b2ca4fe5` (branch `integration/read-only-fixes`), in `~/.local/share/delegate/ads`. `ads.sh install` is reproducible from that constant. The fork exists to carry the grok and agy read-only fixes (ticket 14; upstream PRs #119 and #120).
- `scripts/usage.py`: cached subscription-meter probes. `scripts/events.py`: the monitor ledger encoder (schema unchanged).
- `scripts/report.py`: limits, runs, and the lead's run ledger. `scripts/bench.py`: the human-only benchmark ranking under `~/.cache/delegate/bench/`; no routing code reads it. `collect()` returns two views of the same figures: `models` (one figure per benchmark, for comparing against models nobody runs) and `lanes` (only the figures measured at that lane's own effort, with `mean`/`n` over those). `effort_attributes(measured, lane_effort)` is the whole attribution rule and the wizard and the page both read it from there.
- `scripts/setup.py`, `scripts/setup_tui.py`: interactive catalog wizard (TUI on a TTY, prompt-driven under `--plain` or pipes). Each page makes one decision per line with the same `[x]`/`[ ]` box: the carry page selects a model at an effort, the four tier pages assign a tier. `scripts/bench_page.py`: the HTML board the wizard's `o` key opens, which reads its attribution and its domination rule from `bench.py` and `setup_tui.py` rather than deciding either again.
- `scripts/discover.py`: what each present harness offers — models, their lane or `none`, and `--efforts <model>` for ready-to-paste lane stanzas per effort. It is the only thing that may say an effort exists.
- `scripts/effort.py`: `pack`/`extract`/`check` over a benchmark page. `check` is the trust boundary: it rejects any number that is not on the page, and no worker may originate a number or an identifier.
- `assets/preamble.md`: brief preamble prepended to worker prompts.
- `assets/schemas/return.json`: the child return contract, requested in every prompt and parsed out of the relay's final message.
- `tests/`: one test file per script, stdlib only, no network; `tests/fake-ads/relay.mjs` stands in for the relays.
- Sibling skills `../delegate-claude`, `../delegate-codex`, `../delegate-agy`, `../delegate-grok`: typed-only wrappers, about twenty lines each.

`--read-only` is not one thing. The pinned relays map it per harness: codex and claude get a real read-only sandbox and their tools work; **grok is fixed as of the fork pin** — read-only is now `--sandbox read-only --always-approve`, which is kernel-enforced (Seatbelt/Landlock) and strictly stronger than the advisory plan mode it replaced. **agy is fixed as of the fork pin** — read-only runs under Antigravity's filesystem sandbox with tool auto-approval inside it (`--sandbox --dangerously-skip-permissions`), confining the run to its workspace. `--write` is no longer the workaround it was before 2026-09-10; do not reach for it to get agy's tools working. Note the ADS skill docs for agy still describe the old plan mode (ticket 14 follow-up); the relay code is what runs. If a gate cancels a tool anyway, `map_result` returns `blocked` with reason `permission gate cancelled the run at <tool>` rather than `partial`; it recognises grok's event shape only (`gate_cancelled_tool`, fixture `tests/fixtures/dispatch/grok-gate-cancel/`).

Open work is tracked in `.scratch/delegate-redesign/issues/`; the design is `docs/superpowers/specs/2026-09-08-delegate-redesign.md`.

Constraints for workers: the lane comes from `rank.py`; a lower lane needs a one-line reason. Unrelated working-tree files stay untouched.
