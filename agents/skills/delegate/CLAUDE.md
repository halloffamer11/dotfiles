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

Landed 2026-09-09 (commit 7c76843 and the following one): 01 catalog, 02 rank, 03 dispatch through ADS, 04/05 (`delegate.py run`, `--model`, `--harness`, the five skill files), 06 bench, 07 setup wizard (plain prompts; a selectable TUI is the follow-up), 08 cost in the report, 09 advise-only hook and migration. The old path (`lanes.tsv`, `dispatch.sh`, `extract.py`, `probe.sh`, `references/`, `evals/`, old smoke scripts, courier as relay) was removed in the commit after 7c76843 and is restorable from the git tag `delegate-v1-last` (`git checkout delegate-v1-last -- agents/skills/delegate/<file>`). The hooks in `~/.claude/hooks/` (gate advises only; ledger and prime always on) are outside this repo; backups of the originals are in `~/.cache/delegate/backup-2026-09-09/`. Real runs through the new dispatcher on all four harnesses left run directories under `~/.cache/delegate/runs/`.

Research (cited, dated): `docs/superpowers/research/2026-09-08-lane-cost.md`, `2026-09-08-lane-benchmarks.md`. Prototype of the selection rule (throwaway): `prototype-lane-selection.html`. Tier and trust stay human-set; acceptance §9 is signed off by Orin in ticket 09.

## Monitoring TUI (landed 2026-09-03, uncommitted)

Spec `docs/superpowers/specs/2026-09-02-delegate-monitor-design.md`, plan `docs/superpowers/plans/2026-09-02-delegate-monitor.md` (complete). Crate `monitor/` (package `delegate-mon`, Ratatui): display-only reader of the versioned JSONL ledger (`$DELEGATE_LEDGER` else `~/.cache/delegate/ledger.jsonl`). `events.py` encodes events; `report.py` writes the lead's `runs.jsonl`, a different file. Manual check: `cd monitor && cargo run`.

Constraints for workers: the lane comes from `rank.py`; a lower lane needs a one-line reason. Unrelated working-tree files stay untouched.
