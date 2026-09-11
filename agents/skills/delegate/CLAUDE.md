# Delegate

External worker routing lives in this directory. Read `SKILL.md` first, then use these files as the implementation authority:

- `scripts/catalog.py`: the two configuration files (`~/.config/delegate/lanes.json`, `routing.json`, project override `.delegate/routing.json`), validators, `show`/`check`/`fmt`. `assets/samples/`: the starting catalog from the spec.
- `scripts/rank.py`: the selection rule over the catalog and the live meters (tier ceiling, pace, pace margin).
- `scripts/delegate.py`: one run through a pinned ADS relay (`dispatch`), and rank-then-dispatch (`run`). Run directories under `~/.cache/delegate/runs/`, never reused.
- `scripts/ads.sh`: installs and checks the relay layer, **halloffamer11/delegate-skills** (our fork of amElnagdy) at commit `1ff8bd6` on its `integration/read-only-fixes` branch, in `~/.local/share/delegate/ads`. `ads.sh install` is reproducible from that constant. The fork exists to carry the grok and agy read-only fixes (ticket 14).
- `scripts/usage.py`: cached subscription-meter probes. `scripts/events.py`: the monitor ledger encoder (schema unchanged).
- `scripts/report.py`: limits, runs, and the lead's run ledger. `scripts/bench.py`: the human-only benchmark ranking under `~/.cache/delegate/bench/`; no routing code reads it.
- `scripts/setup.py`, `scripts/setup_tui.py`: interactive catalog wizard (TUI on a TTY, prompt-driven under `--plain` or pipes).
- `scripts/browser_probes.py`: browser capability probe runner across harnesses (`--only`, `--probe`, `--dry-run`).
- `assets/preamble.md`: brief preamble prepended to worker prompts.
- `assets/probes/`: capability probe briefs for disposable browser (`disposable.md`) and agent profile (`agent-profile.md`).
- `assets/schemas/return.json`: the child return contract, requested in every prompt and parsed out of the relay's final message.
- `references/`: `tui-research.md`, `tui-mockup.md`.
- `tests/`: one test file per script, stdlib only, no network; `tests/fake-ads/relay.mjs` stands in for the relays.
- Sibling skills `../delegate-claude`, `../delegate-codex`, `../delegate-agy`, `../delegate-grok`: typed-only wrappers, about twenty lines each.

`--read-only` is not one thing. The pinned relays map it per harness: codex gets its read-only sandbox; claude gets plan mode with only Read, Glob and Grep; grok gets `--sandbox read-only --always-approve` and agy gets `--sandbox --dangerously-skip-permissions`. For grok and agy the sandbox is the boundary and the auto-approve only lets tools run inside it; both replaced plan modes that auto-denied every tool in a headless run (ticket 14). On Linux, grok's read-only sandbox also blocks network for child processes.

No worker can use a browser through delegate yet: the claude relay denies every MCP tool and codex runs skip the user config. That is the open work in `.scratch/delegate-browser/issues/`.

Other open work is tracked in `.scratch/delegate-redesign/issues/`; the design is `docs/superpowers/specs/2026-09-08-delegate-redesign.md`.

Constraints for workers: the lane comes from `rank.py`; a lower lane needs a one-line reason. Unrelated working-tree files stay untouched.
