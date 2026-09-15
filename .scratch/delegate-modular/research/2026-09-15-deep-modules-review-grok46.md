# Deep-modules review of the delegate skill

Judged against the code. Spec `docs/superpowers/specs/2026-09-08-delegate-redesign.md` and `agents/skills/delegate/CLAUDE.md` are cited only where they disagree with the code. Import counts are sibling `import`/`from` in `scripts/` and `tests/test_*.py`.

## Module inventory

| module | public interface | what complexity it hides | depth verdict | one-line reason |
|---|---|---|---|---|
| `catalog.py` | CLI `show`/`check`/`fmt` (`catalog.py:890`). Imported by 9 scripts and 7 tests. Callers take `load_catalog` (`catalog.py:769`), `validate_lanes` (`catalog.py:238`), `validate_routing` (`catalog.py:462`), `validate_project_routing` (`catalog.py:628`), `write_json` (`catalog.py:103`), `resolve_published_model` (`catalog.py:186`), plus constants `HARNESSES`/`EFFORTS`/`CLASSES`/`HARNESS_EFFORTS` (`catalog.py:28`). Tests also call `load_json`, `format_json`, `merge_routing`, `effective_routing`, `find_git_root`. | Strict JSON, global+project merge, Project order projection (`_effective_lanes`, `catalog.py:727`), published-name mapping. | deep | One load path; 9 scripts depend on it (`bench.py`, `bench_page.py`, `browser_probes.py`, `delegate.py`, `discover.py`, `rank.py`, `report.py`, `setup.py`, `setup_tui.py`). Surface is wide (validators exported for writers) but the merge lives behind `load_catalog`. |
| `rank.py` | CLI `<class>` and `tiers` (`rank.py:52`). Imported by 2 scripts (`delegate.py`, `report.py`) and 2 tests. Functions: `rank` (`rank.py:245`), `rank_range` (`rank.py:123`), `tier_leaders` (`rank.py:278`), `meter_observations` (`rank.py:83`), `format_rows` (`rank.py:301`), `run_usage` (`rank.py:330`), `load_cached_usage` (`rank.py:343`). Tests call `rank` and `tier_leaders` only (`test_rank.py:98`, `test_catalog.py:1005`). | Floor/ceiling/gate/cli veto, sort `(tier, order, pace, name)`, Margin steal, Meter cache validity. | deep | Selection rule is one function (`rank_range`); Class and Tier wrappers call it. `run_usage` is a subprocess shim, not the rule. |
| `usage.py` | CLI default/`--refresh`/`--max-age-min`/`--pretty` (`usage.py:15`). No script imports it; `rank.py:333`, `delegate.py:420`, `report.py:134` spawn it. Tests import `claude_reset`, `write_cache`, `load_cache`, `lane` (`test_usage_reset.py:13`). | Four vendor probes (`probe_codex` `usage.py:73`, `probe_agy` `usage.py:113`, `probe_claude` `usage.py:149`, `probe_grok` `usage.py:173`) into one JSON document. | deep | Probe mess is behind `lane()` (`usage.py:49`) and `main`. Callers treat it as a CLI, not a library, except the test. |
| `events.py` | CLI `meter`/`start`/`finish` (`events.py:5`). `append`+`meter_event` imported by `usage.py:27`; `append`+start/finish builders used by `delegate.py:401` and `delegate.py:691`. Tests import the module (`test_events.py:15`) and also drive the CLI. | Ledger line shape and append path. | deep | Small encoder. No reader. |
| `delegate.py` | CLI `dispatch`/`run` (`delegate.py:35`). Imported by `browser_probes.py:236` (`ORCHESTRATOR`) and `test_dispatch.py:30`. Library surface: `resolve` (`delegate.py:129`), `build_prompt` (`delegate.py:277`), `allocate_run_dir` (`delegate.py:351`), `run_relay` (`delegate.py:440`), `map_result` (`delegate.py:525`), `dispatch` (`delegate.py:715`), `run` (`delegate.py:869`). Tests mostly drive `main`; three cases call `map_result` (`test_dispatch.py:903`). | Prompt splice, exclusive Run dir, per-Harness relay argv, return-block parse, status map. | shallow | Dispatch work is real, but the file also reprints ranking (`_print_rank_output`, `delegate.py:847`), probes meters on its own (`delegate.py:414`), and exits the return contract for a Native lane (`delegate.py:765`). |
| `report.py` | CLI `limits`/`log`/`runs`/`cost`/`statusline` (`report.py:6`, `report.py:660`). No script or test imports it; `test_report.py:15` runs the CLI. Internally imports `load_catalog` and `rank.rank` (`report.py:27`, `report.py:32`). | Markdown tables, token dollars (`compute_cost`, `report.py:217`), statusline glyphs. | shallow | Presentation mixed with a second Gate, a second cache path, and a hand-rolled ledger reader (`report.py:565`). |
| `bench.py` | CLI (`bench.py:14`). Imported by 3 scripts (`setup.py`, `setup_tui.py`, `bench_page.py`) and 3 tests. `collect` (`bench.py:727`) and `effort_attributes` (`bench.py:320`) are the library. | Epoch CSV match, AA row attribution at the Lane's own Effort, two views (`models`/`lanes`). | deep | `collect` is the seam the wizard and the page share. `md_table` (`bench.py:183`) is local formatting. |
| `bench_page.py` | `render`/`write` (`bench_page.py:1196`). Imported by `setup.py:12` and `test_bench_page.py:32`. Pulls carry helpers from `setup_tui` (`bench_page.py:28`). | Self-contained HTML, plot JSON, display aids `sensitivity`/`beatenByLane`. | shallow | Rendering is real work, but carry/order/grouping are imported from the TUI, so the page is not a view of a policy module. |
| `effort.py` | CLI `pack`/`extract`/`check`/`run`/`aa` (`effort.py:47`). No script imports it; 3 tests do. Library: `pack_html`, `check_rows`, `aa_extract`, `split_packet`. `extract` shells `delegate.py dispatch` (`effort.py:900`). | Packet packing, number-on-page check, AA dataset extract. | deep | `check` is the trust boundary. Extract is a caller of dispatch, not a second dispatcher. |
| `discover.py` | CLI default/`--efforts` (`discover.py:760`). Imported by `setup.py:14` and 3 tests. `discover` (`discover.py:370`) is the library; tests also call `parse_codex_output` (`test_discover.py:45`), `parse_agy_output`, `parse_grok_output`, `parse_claude_help`, `group_agy_models`. | Harness CLI parse and catalog drift. | deep | One `discover()` result. Parsers are treated as public by tests. |
| `setup.py` | CLI flags (`setup.py:267`). Imported only by `test_setup.py:308`. Orchestrates `read_discovery` (`setup.py:27`), `discover.discover` (`setup.py:302`), `bench.collect` (`setup.py:341`), `setup_tui.Wizard` (`setup.py:358`). `--plain` keeps `ask_lanes`/`ask_routing` (`setup.py:181`). | Almost none of its own. | pass-through | Wires other modules. Still runs a second discovery (`discover.mjs`, `setup.py:32`) and a second wizard (`ask_lanes`). |
| `setup_tui.py` | No CLI. Imported by `setup.py`, `bench_page.py`, 3 tests. `Wizard` (`setup_tui.py:547`), `run_curses` (`setup_tui.py:1579`), `dominating_effort` (`setup_tui.py:430`), `propose_enabled` (`setup_tui.py:494`), `parse_tier_lines` (`setup_tui.py:83`), `layout_lines` (`setup_tui.py:1462`). Tests also import `_clip`/`_fit_table`/`ROW_FLOOR` (`test_setup_tui.py:1357`). | Carry rule, tier/order pages, curses layout. | shallow | Two seams in one file: Dominated/carry policy and the TUI. `bench_page.py:28` imports the policy from here. |
| `browser_probes.py` | CLI `--only`/`--probe`/`--dry-run` (`browser_probes.py:9`). Tests call `grade` (`test_browser_probes.py:51`) and the CLI. | Probe brief fill, dispatch, PASS/FAIL on `return.json`. | shallow | Driver. `pick_lowest_tier_lane` (`browser_probes.py:67`) is a second selection rule. `load_effective_catalog` (`browser_probes.py:54`) wraps `catalog.load_catalog`. |
| `ads.sh` | `install`/`check`/`path` (`ads.sh:19`). Called by `delegate.py:244`. | Pin the Relay checkout and locate `relay.mjs`. | deep | Three verbs, one commit constant (`ads.sh:14`). |

## Seams

The design has six real seams. Module files sit on some of them and cut across others.

**Catalog on disk.** `lanes.json` + global/project `routing.json`. Code sits on it: `catalog.load_catalog` (`catalog.py:769`) is what `rank.py:387`, `delegate.py:131`, `delegate.py:875`, `report.py:102`, `bench.py:836`, `browser_probes.py:61` call. Cross-cut: `setup.py:72` loads the two files with `load_json`+`validate_*` and never `load_catalog`, so a `--plain` or TUI start does not apply Project order the way ranking does. Cross-cut: spec still documents `classTier` (`docs/superpowers/specs/2026-09-08-delegate-redesign.md:77`); `catalog.py:469` rejects that key. Spec sort has no Order (`docs/superpowers/specs/2026-09-08-delegate-redesign.md:96`); `rank.py:205` sorts Order before Pace.

**Meter probe.** Vendor CLIs → one observation document. Code sits on it as a process: `usage.py:236`. Cross-cut: three spawn policies. `rank.run_usage` (`rank.py:330`) runs `usage.py` with cache. `delegate.probe_meters` (`delegate.py:414`) runs `usage.py --refresh`. `report.usage_doc` (`report.py:133`) runs `usage.py` then falls back to a file open of `CACHE`. Cross-cut: cache path. `usage.get_cache_path` (`usage.py:37`) reads `DELEGATE_CACHE` then `CONSULT_CACHE`. `rank.load_cached_usage` (`rank.py:347`) copies that. `report.py:38` omits `CONSULT_CACHE`. Cross-cut: CLAUDE.md says `rank.meter_observations()` owns cache validity for ranking and any viewer (`agents/skills/delegate/CLAUDE.md:11`). Only `rank_range` (`rank.py:142`) calls it. `report.py:538` `json.load`s the cache and keys it by `lane` (`report.py:600`).

**Ranking rule.** Floor, Ceiling, Gate, Order, Pace, Margin, Pick. Code sits on it: `rank_range` (`rank.py:123`), with `rank` (`rank.py:245`) and `tier_leaders` (`rank.py:278`) as callers. Cross-cut: `delegate.run` (`delegate.py:869`) reloads catalog, meters, and present harnesses, then reprints the same header `rank.main` prints (`delegate.py:847` vs `rank.py:458`). Cross-cut: `rank` still accepts unused `effort=None` (`rank.py:245`), leftover from spec `--effort` (`docs/superpowers/specs/2026-09-08-delegate-redesign.md:102`). Cross-cut: `browser_probes.pick_lowest_tier_lane` (`browser_probes.py:67`) sorts `(tier, name)` and ignores Order, Pace, Gate. Cross-cut: `usage.py:32` `GATE = 0.10` sets `status` (`usage.py:57`); `rank.py:139` uses `routing.gate`; `report.py:206` prints "under 10%"; `report.py:175` `--eligible` keeps `status == "ok"`; `report.py:627` ORs `remaining_weekly <= gate_threshold` with `status == "unavailable"`.

**Relay boundary.** Pinned `relay.mjs` per Harness. Code sits on it: `ads.sh` plus `run_relay` (`delegate.py:440`). Cross-cut: Native lane (`harness == ORCHESTRATOR`, `delegate.py:765`) prints a spawn line and `sys.exit(0)` before ledger and `return.json`. `browser_probes.native_agent` (`browser_probes.py:236`) imports `delegate.ORCHESTRATOR` to detect that. `lane-opus-high.md` is a spawn target, not a Relay. Cross-cut: `setup.py:32` still runs ADS `discover.mjs` while `discover.py:370` queries the same CLIs.

**Return contract.** `assets/schemas/return.json` requested in the prompt (`delegate.py:322`), parsed by `find_return_block` (`delegate.py:76`), written by `map_result` (`delegate.py:641`). This sits on the seam for Relayed lanes. Cross-cut: Native path never writes `return.json`. SKILL.md tells the session to treat the agent's final message as the claim (`agents/skills/delegate/SKILL.md:30`). `courier.md:16` is a poll-and-cat of that file.

**Benchmark sources.** Accepted rows in, human-facing ranking out. Code sits on it: `effort.py` `check`/`aa`, then `bench.collect` (`bench.py:727`). Spec still describes an AA API key (`docs/superpowers/specs/2026-09-08-delegate-redesign.md:127`); `bench.py` has no key loader (`test_bench.py:439` asserts that). Cross-cut: the carry rule that proposes a Lane off (`dominating_effort`, `setup_tui.py:430`) lives in the TUI file and is imported by the HTML page (`bench_page.py:28`). Cross-cut: `setup.py:121` subprocesses `bench.py` on the `--plain` path and calls `bench.collect` on the TUI path (`setup.py:341`).

## Pass-through and speculative layers

- `delegate.ledger_start` (`delegate.py:399`) and `ledger_finish` (`delegate.py:690`) only call `events.append`.
- `report.load_catalog_or_die` (`report.py:100`) is `load_catalog` plus `sys.exit`.
- `browser_probes.load_effective_catalog` (`browser_probes.py:54`) is `load_catalog` plus `sys.exit`.
- `rank.run_usage` (`rank.py:330`) is `subprocess` + `json.loads`, returning `{}` on any error.
- `rank.rank(..., effort=None)` (`rank.py:245`) documents the argument as unused.
- `setup.py` `--plain` (`setup.py:305`) is a second, thinner wizard (`ask_lanes` `setup.py:181`) beside `Wizard`.
- `setup.py.read_discovery` (`setup.py:27`) is a leftover ADS `discover.mjs` path; `discover.discover` runs next (`setup.py:302`).
- Four typed-only wrappers (`agents/skills/delegate-claude/SKILL.md` and siblings) copy the same rank-then-filter-then-`dispatch` recipe, one Harness name changed. Spec said they call dispatch and do not read meters (`docs/superpowers/specs/2026-09-08-delegate-redesign.md:120`); the files now run `rank.py --json` first.
- `courier.md` runs `delegate.py dispatch` and prints `return.json` (`agents/agents/courier.md:12`).
- `effort.format_json` (`effort.py:126`) matches `catalog.format_json` (`catalog.py:98`).
- `bench.md_table` (`bench.py:183`) and `report.md_table` (`report.py:51`) are two table printers.
- `browser_probes.ALL_HARNESSES` (`browser_probes.py:32`) copies `catalog.HARNESSES` (`catalog.py:28`). `ads.sh:17` copies it again.

## Leaks

- `test_setup_tui.py:1357` imports `_clip`, `_fit_table`, `ROW_FLOOR`, `TIER_ONELINER`. `layout_lines` (`setup_tui.py:1462`) is the stated screen seam; the underscored helpers are not.
- `test_usage_reset.py:13` imports `claude_reset`, `lane`, `write_cache`, `load_cache`. No test drives `usage.py` as the probe CLI.
- `test_discover.py:45` imports harness parsers. `discover()` (`discover.py:370`) is the module's result.
- `test_dispatch.py:903` calls `map_result` on fixture dirs. That is the return-map interface; the rest of the file uses `main`. Acceptable if `map_result` is kept public.
- `test_catalog.py:1005` ranks through `rank.rank` / `rank.tier_leaders` to check Project order. That is the right seam. `test_rank.py` never names `rank_range` or `meter_observations`; those stay unenforced as named APIs.
- Meter document key `lane` (`usage.py:64`) is a Meter identity (`codex`, `claude-fable`). Catalog Lanes are a different name. `rank.py:151` and `report.py:600` look up catalog Meter names in that field. Two vocabularies, one key.
- `usage.py:9` says `rank.py` sorts on `score`. `rank.py:205` sorts Pace and never reads `score`.
- `report.py:565` parses `ledger.jsonl`. `events.py` has no read API. The monitor TUI is a third reader, outside this skill.
- `browser_probes.py:236` imports `delegate` only for `ORCHESTRATOR`.
- `report.py:175` `--eligible` claims to drop meters `rank.py` would skip, then filters `status == "ok"` from `usage.py`, not `rank` rows.

## Findings

1. **high — Carry rule sits in the TUI.** `dominating_effort` / `propose_enabled` (`setup_tui.py:430`, `setup_tui.py:494`) are catalog policy. `bench_page.py:28` imports them so the page and the wizard do not diverge. Move the rule (and `group_lanes` / `lane_order`) to a module both call, e.g. beside `bench.collect`. Guard with `test_setup_tui.py` domination cases and `test_bench_page.py`.

2. **high — Gate is three rules.** `usage.GATE` (`usage.py:32`) stamps `status`. `rank_range` uses `routing.gate` (`rank.py:139`). `report.py:206` hardcodes 10%. `report.py:175` and `report.py:627` mix `status` with remaining. Keep probe math in `usage.py`; keep eligibility in `rank`. Point `limits --eligible` and the statusline at `rank` rows. Guard with `test_rank.py` and `test_report.py`.

3. **high — Meter validity is not shared.** `meter_observations` (`rank.py:83`) is the documented viewer boundary (`CLAUDE.md:11`) and is used only inside `rank_range` (`rank.py:142`). `report.py:538` reads the cache itself. One function should feed ranking and the statusline. Guard with `test_rank.py` case 21 (`test_rank.py:858`) plus a statusline fixture that is malformed.

4. **high — Setup discovers twice.** `read_discovery` runs ADS `discover.mjs` (`setup.py:32`). Then `discover.discover` queries the CLIs (`setup.py:302`). Spec named the Node script (`docs/superpowers/specs/2026-09-08-delegate-redesign.md:121`); the Python module is what tests cover. Drop `discover.mjs` from the main path. Guard with `test_setup.py` and `test_discover.py`.

5. **medium — `delegate.run` reprints ranking.** `_print_rank_output` (`delegate.py:847`) copies `rank.main` (`rank.py:458`). Meters and present-harness detection are copied (`delegate.py:890` vs `rank.py:391`). `run` should call `rank.rank` (it already does, `delegate.py:904`) and a shared formatter. Delete unused `effort` on `rank` (`rank.py:245`). Guard with `test_dispatch.py` dry-run and `test_rank.py` CLI.

6. **medium — Native dispatch leaves the return seam.** `delegate.py:765` prints `delegate: native` and exits without `return.json` or ledger events. Relayed jobs go through `map_result` (`delegate.py:525`). Either write a native run dir that the session fills, or make `dispatch` return a structured native record the wrappers already consume. Guard with `test_dispatch.py` native cases (`test_dispatch.py:195`).

7. **medium — Meter identity vs Lane name.** `usage.lane()` names the observation `f"{harness}-{meter}"` (`usage.py:64`). Rank looks up `lane_def["meter"]` in that map (`rank.py:151`). The JSON field is called `lane`. Rename the observation key to the Meter, or add an explicit Meter id and stop overloading `lane`. Guard with `test_usage_reset.py` and `test_rank.py`.

8. **medium — Tests pin internals.** `test_setup_tui.py:1357` (`_clip`, `_fit_table`); `test_usage_reset.py:13`; `test_discover.py:45`. Promote `layout_lines`/`overlay` as the screen API; test usage through the CLI document; test discovery through `discover()`. Do not make underscored helpers load-bearing.

9. **medium — Ledger has writers, no reader.** `events.append` (`events.py:27`) is used by `usage.py:234` and `delegate.py:401`. `report.py:565` re-parses the file for running glyphs. Add a read/scan function and use it in `cmd_statusline`. Guard with `test_events.py` and `test_report.py`.

10. **low — Second selection in browser probes.** `pick_lowest_tier_lane` (`browser_probes.py:67`) ignores Order, Pace, and Gate. Call `rank_range` with the Harness present-set, or document that probes are not Picks. Guard with `test_browser_probes.py`.

11. **low — Cache path drift.** `report.py:38` drops `CONSULT_CACHE` that `usage.py:37` and `rank.py:348` still read. One `get_cache_path`. Guard with `test_usage_reset.py` / `test_rank.py` missing-cache case (`test_rank.py:832`).

12. **low — Duplicate constants and printers.** `HARNESSES` copied in `browser_probes.py:32` and `ads.sh:17`. `format_json` in `effort.py:126` and `catalog.py:98`. `md_table` in `report.py:51` and `bench.py:183`. Dedup when the files that own them next change. Guard with the existing tests of those files.

## What is already right

- `catalog.load_catalog` is the catalog seam ranking, dispatch, report, and bench already share.
- `rank_range` is the selection rule; `rank` and `tier_leaders` call it instead of copying the steal loop.
- `effort.check` / `aa` keep numbers on the page; `bench.collect` attributes one figure per Lane at that Lane's Effort; routing code does not read `~/.cache/delegate/bench/`.
- Relayed dispatch owns prompt, exclusive Run dir, Relay argv, and `return.json` in one file. Tests drive that through `main` plus a fake `relay.mjs`.
- `ads.sh` pins the Relay. `events.py` is only an encoder.
- Typed wrappers filter `rank.py --json` rows and then `dispatch`; they do not reimplement Floor/Margin in Python.
- Tests chdir to a temp tree with no Git root so the checkout's `.delegate/routing.json` cannot leak in.

## Refactoring order

Each step is one commit. Do not mix a seam move with a behaviour change.

1. **Share cache path.** Export `usage.get_cache_path` (or a tiny `paths` helper) and use it in `rank.load_cached_usage` and `report.CACHE`. Tests: `test_usage_reset.py`, `test_rank.py` missing-cache, `test_report.py` limits.

2. **Drop unused `rank(..., effort=)`.** Tests: `test_rank.py`.

3. **Share rank formatting.** Move the class header + `format_rows` print from `rank.main` and `delegate._print_rank_output` to one function. Tests: `test_rank.py` CLI, `test_dispatch.py` `run --dry-run`.

4. **One discovery on setup.** Delete `read_discovery`'s `discover.mjs` call from the default path; keep `--discover-json` if a fixture still needs it. Tests: `test_setup.py`, `test_discover.py`.

5. **Extract carry/order helpers** from `setup_tui.py` to a module `bench_page` and `Wizard` both import. No behaviour change. Tests: `test_setup_tui.py`, `test_bench_page.py`.

6. **Gate and eligibility.** Stop treating `usage.status` as ranking. `limits --eligible` and statusline gated marks consume `rank` / `meter_observations`. Tests: `test_rank.py`, `test_report.py`.

7. **Meter observation reader.** `report.cmd_statusline` takes the dict `meter_observations` returns. Tests: `test_rank.py` case 21, new malformed-cache case in `test_report.py`.

8. **Ledger read API** in `events.py`; `cmd_statusline` uses it. Tests: `test_events.py`, `test_report.py`.

9. **Meter identity.** Rename or dual-write the observation key so catalog Meter names are explicit. Tests: `test_usage_reset.py`, `test_rank.py`, `test_report.py`.

10. **Native run record.** Write the run dir and a native marker instead of exiting before the contract, or return a struct the SKILL already handles. Tests: `test_dispatch.py` native, `test_browser_probes.py` dry-run.

11. **Probe selection.** Replace `pick_lowest_tier_lane` with `rank_range` or a documented subset. Tests: `test_browser_probes.py`.

12. **Test surface.** Point `test_setup_tui.py` at `layout_lines`/`overlay` only; point `test_discover.py` at `discover()` for drift, keep one parser unit file if the CLIs stay messy. Tests: the same files, green.
