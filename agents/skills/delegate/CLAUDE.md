# Delegate

External worker routing lives in this directory. Read `SKILL.md` first, then use these files as the implementation authority:

- `scripts/catalog.py`: the two configuration files (`~/.config/delegate/lanes.json`, `routing.json`, project override `.delegate/routing.json`), validators, `show`/`check`/`fmt`. `assets/samples/`: the starting catalog from the spec.
- `scripts/rank.py`: the selection rule over the catalog and the live meters (tier ceiling, trust, pace margin).
- `scripts/delegate.py`: one run through a pinned ADS relay (`dispatch`), and rank-then-dispatch (`run`). Run directories under `~/.cache/delegate/runs/`, never reused.
- `scripts/ads.sh`: installs and checks the relay layer, amElnagdy/delegate-skills at commit `b781ee2e23089630e2fbee1cfd6174afe4edeb76`, in `~/.local/share/delegate/ads`. `ads.sh install` is reproducible from that constant.
- `scripts/usage.py`: cached subscription-meter probes. `scripts/events.py`: the monitor ledger encoder (schema unchanged).
- `scripts/report.py`: limits, runs, and the lead's run ledger. `scripts/bench.py`: the human-only benchmark ranking under `~/.cache/delegate/bench/`; no routing code reads it.
- `scripts/setup.py`, `scripts/setup_tui.py`: interactive catalog wizard (TUI on a TTY, prompt-driven under `--plain` or pipes).
- `assets/preamble.md`: brief preamble prepended to worker prompts.
- `assets/schemas/return.json`: the child return contract, requested in every prompt and parsed out of the relay's final message.
- `references/`: `tui-research.md`, `tui-mockup.md`.
- `tests/`: one test file per script, stdlib only, no network; `tests/fake-ads/relay.mjs` stands in for the relays.
- Sibling skills `../delegate-claude`, `../delegate-codex`, `../delegate-agy`, `../delegate-grok`: typed-only wrappers, about twenty lines each.

Constraints for workers: the lane comes from `rank.py`; a lower lane needs a one-line reason. Unrelated working-tree files stay untouched.
