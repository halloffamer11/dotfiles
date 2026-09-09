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

`--read-only` is not one thing. The pinned relays map it per harness: codex and claude get a real read-only sandbox and their tools work; **grok gets `--permission-mode plan`, which cancels tool calls, and agy gets `--mode plan`, which auto-denies every permission in a headless run**. A read-only dispatch to grok or agy therefore dies at its first tool call and burns the quota anyway. Ticket 14 carries the fix; until it lands, send tool-needing read-only work to codex or claude.

Open work is tracked in `.scratch/delegate-redesign/issues/`; the design is `docs/superpowers/specs/2026-09-08-delegate-redesign.md`.

Constraints for workers: the lane comes from `rank.py`; a lower lane needs a one-line reason. Unrelated working-tree files stay untouched.
