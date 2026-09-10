# Blast radius — removing `trust` (q1a)

Mapped 2026-09-10 by grep over the whole worktree, then by reading every hit.
Decisions recorded in `issues/01-lane-catalog-and-validators.md` and
`issues/02-ranking-over-the-catalog.md`.

## A. Must land in one commit — code and shipped config are coupled

Once the validator drops `trust` from `allowed_lane_fields`, every catalog that
still carries the key is rejected by the unknown-field rule. Code and both
catalogs therefore move together or delegate stops running.

| File | Sites | Change |
|---|---|---|
| `agents/skills/delegate/scripts/catalog.py` | 180, 184, 262-266, 466, 470 | Drop from `allowed_lane_fields` and `required_lane_fields`; delete the 1..5 range check; drop `-trust` from the print sort key and the `trust` column from the lane line. |
| `agents/skills/delegate/scripts/rank.py` | 18, 104, 125, 144, 195 | Drop the docstring sort term, the `lane_def.get("trust")` read, the `trust` row key, `-tr` from `sort_key`, and `trust=` from the text line. |
| `agents/skills/delegate/scripts/setup.py` | 188, 214 | Delete the `ask_int("trust", ...)` prompt and the `trust` half of the confirm line. |
| `agents/skills/delegate/scripts/setup_tui.py` | 33, 98, 152, 195, 206, 213, 251 | Delete `self._trust`; delete the `1`..`5` key handler; stop writing `trust` into the result lanes; drop the `trust` column, its cell, the `1-5: trust` footer text, the confirm cell, and `"trust"` from `_fit_table` priority names. |
| `agents/skills/delegate/assets/samples/lanes.json` | 6 lanes | Delete the `trust` key. One `basis` string says "not trusted alone" — prose, keep or reword. |
| `stow/delegate/.config/delegate/lanes.json` | 7 lanes | Delete the `trust` key. **This is the file `~/.config/delegate/lanes.json` symlinks to from the main checkout**, so it is live the moment the branch merges. Its `astra-high@codex` note names trust as a placeholder to confirm — reword. |

## B. Behaviour changes, not just deletions

1. **Tie-break inside a tier changes.** The sort key goes from
   `(unknown, tier, -trust, -pace)` to `(unknown, tier, -pace)`. Equal-pace
   lanes in the same tier now fall to the stable catalog order.
   In the sample catalog tier 1 holds `luna-low@codex` (trust 3) before
   `flash-high@agy` (trust 4), so an equal-pace `scout` pick **flips from
   flash to luna**. `test_rank.py` case 9A and `test_dispatch.py` case 20 both
   assert flash and will fail. Decide the intended winner before rewriting them;
   reordering the catalog keys is the lever if flash must keep winning.
2. **`rank.py --json` row schema loses the `trust` key.** Any consumer reading
   it breaks; only `test_rank.py` case 12 does today.
3. **`rank.py` text line loses `trust=`.** `test_dispatch.py` case 21 matches
   the literal `"tier=2 trust=5"`.
4. **`catalog.py` lane print loses a column and re-sorts.**

## C. Tests to rewrite or delete

| File | Sites | Change |
|---|---|---|
| `tests/test_catalog.py` | 117-126 | Delete case 2.4 (trust 0 / trust 6 rejection). Consider replacing it with a case proving a stray `trust` key is now an unknown-field rejection. |
| `tests/test_rank.py` | 347-368, 448 | Rewrite case 9 around the new tie-break (see B.1); drop `"trust"` from `required_row_keys`. |
| `tests/test_dispatch.py` | 682, 692 | Case 21 assertion drops `trust=5`; case 20's expected lane may flip (B.1). |
| `tests/test_setup.py` | 112, 152, 162-164, 179 | Drop trust from the sample-equality check, the existing-value default case, and the changed-lane case. |
| `tests/test_setup_tui.py` | 131-134 | Delete case 4 ("trust edit changes one lane"). |

## D. Prose and specification

| File | Sites | Change |
|---|---|---|
| `agents/skills/delegate/SKILL.md` | 3, 16, 22, 36 | Frontmatter `description` ("picked by tier, trust, and remaining subscription usage") — this string is what the skill list shows. Also the Trust definition, the lanes.json field list, and the selection rule. |
| `agents/skills/delegate/CLAUDE.md` | 6 | `rank.py` description names trust as a selection input. |
| `agents/skills/delegate/scripts/bench.py` | 4, 581, 743 | Three prose strings calling the report "evidence for tier and trust decisions". Output text only, no logic. |
| `agents/skills/council/SKILL.md` | 43 | **Consumer outside the delegate skill.** The adjudicator is "the highest-tier, highest-trust available lane". Needs a replacement rule — see the open question. |
| `docs/superpowers/specs/2026-09-08-delegate-redesign.md` | 16 hits: title, 15, 24, 25, 47-67, 70, 88, 94, 101, 120, 152 | The design of record, including the title and the section 5 rule. |
| `CLAUDE.md` (project) | 17 | The waiting-on-Orin item asks Orin to set `meter_weight` **and trust** on `astra-high@codex`; the trust half dissolves. |
| `.scratch/.../issues/06, 07, 07b, 11, 12` | see grep | Ticket prose. 07b §2 and §4 and 12 define the trust interaction and its start-screen definition; both need the trust parts cut, and 12's acceptance line "Tier and trust are defined on the start screen" becomes tier only. |
| `.scratch/.../research/2026-09-09-effort-data-sources.md` | 5, 102 | Research record. Historical — leave as written. |

## E. Confirmed NOT affected (false positives)

`delegate.py`, `report.py`, `events.py`, `usage.py`, `ads.sh` — zero hits.
`scripts/effort.py` ("trust boundary", a provenance idea) and
`tests/test_effort.py` ("trusted" as a bad-provenance test string) are unrelated.
`references/kiro.md` `--trust-tools` is a kiro-cli flag. `Brewfile` `trusted:`
is a Homebrew tap option. `agents/agents/debugger.md`, `agents/skills/toolsmith`,
`agents/skills/facebook-marketplace` are ordinary English.
