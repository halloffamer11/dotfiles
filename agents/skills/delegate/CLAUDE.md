# Delegate

External worker routing lives in this directory. Read `SKILL.md` first, then use these files as the implementation authority:

- `catalog.py`: the two configuration files (`~/.config/delegate/lanes.json`, `routing.json`, project override `.delegate/routing.json`), validators, `show`/`check`/`fmt`. `samples/`: the starting catalog from the spec.
- `rank.py`: the selection rule over the catalog and the live meters (tier ceiling, trust, pace margin).
- `delegate.py`: one run through a pinned ADS relay (`dispatch`), and rank-then-dispatch (`run`). Run directories under `~/.cache/delegate/runs/`, never reused.
- `ads.sh`: installs and checks the relay layer, amElnagdy/delegate-skills at commit `b781ee2e23089630e2fbee1cfd6174afe4edeb76`, in `~/.local/share/delegate/ads`. `ads.sh install` is reproducible from that constant.
- `usage.py`: cached subscription-meter probes. `events.py`: the monitor ledger encoder (schema unchanged).
- `report.py`: limits, runs, and the lead's run ledger. `bench.py`: the human-only benchmark ranking under `~/.cache/delegate/bench/`; no routing code reads it.
- `schemas/return.json`: the child return contract, requested in every prompt and parsed out of the relay's final message.
- `tests/`: one test file per script, stdlib only, no network; `tests/fake-ads/relay.mjs` stands in for the relays.
- Sibling skills `../delegate-claude`, `../delegate-codex`, `../delegate-agy`, `../delegate-grok`: typed-only wrappers, about twenty lines each.

## Redesign status (spec `docs/superpowers/specs/2026-09-08-delegate-redesign.md`, tickets `.scratch/delegate-redesign/issues/01..09`)

Landed in the working tree on 2026-09-09, uncommitted: 01 catalog, 02 rank, 03 dispatch through ADS, 04/05 (`delegate.py run`, `--model`, `--harness`, the five skill files), 06 bench, 07 setup wizard, 08 cost in the report. Real runs through the new dispatcher on all four harnesses (agy and Claude read-only smokes, grok and codex write runs) left run directories under `~/.cache/delegate/runs/`. Pending: 09 advise-only hook and migration (hooks and the global CLAUDE.md live in `~/.claude`, not here; the council skill still points at `references/routing.md` and `probe.sh`). Until 09 lands, `lanes.tsv`, `dispatch.sh`, `extract.py`, `probe.sh`, `references/routing.md` and the old smoke scripts remain as the old path; `preamble.md` and `schemas/return.json` are still used by `delegate.py`. New wrapper skill directories need `make skills` to appear under `~/.claude/skills`.

Research (cited, dated): `docs/superpowers/research/2026-09-08-lane-cost.md`, `2026-09-08-lane-benchmarks.md`. Prototype of the selection rule (throwaway): `prototype-lane-selection.html`. Tier and trust stay human-set; acceptance §9 is signed off by Orin in ticket 09.

## Monitoring TUI (landed 2026-09-03, uncommitted)

Spec `docs/superpowers/specs/2026-09-02-delegate-monitor-design.md`, plan `docs/superpowers/plans/2026-09-02-delegate-monitor.md` (complete). Crate `monitor/` (package `delegate-mon`, Ratatui): display-only reader of the versioned JSONL ledger (`$DELEGATE_LEDGER` else `~/.cache/delegate/ledger.jsonl`). `events.py` encodes events; `report.py` writes the lead's `runs.jsonl`, a different file. Manual check: `cd monitor && cargo run`.

Constraints for workers: the lane comes from `rank.py`; a lower lane needs a one-line reason. Unrelated working-tree files stay untouched.
