# 32 — A project may set a Lane's Tier

**What to build:** a project customizes Lanes for itself. Today `lanes.json` is global
only, and a project's `.delegate/routing.json` may reorder Lanes inside a Tier
(`project_order`) but "never changes a Tier". Orin, 2026-09-18, on the dashboard's `H`/`L`
keys, which would otherwise write his live global catalog: "add to scope - allow projects
to have a lanes customization".

**Blocked by:** 31 lands first in the same worktree (both touch `rank.py`).

## Rule (session decisions; Orin may overrule)

- The customization lives in `<git-root>/.delegate/lanes.json`, beside the project's
  `routing.json`, the same pair as the global files: `{"lanes": {"<lane>": {"tier": n}}}`,
  `note` fields accepted anywhere, strict JSON, validated on read with the plain-language
  messages the other files give.
- This ticket admits one field: `tier`, 1 to 4, for a Lane that exists in the global
  catalog. Every other Lane field (harness, model, meter, price, `enabled`, `order`)
  stays global. A project that names an unknown Lane or another field fails validation.
- The effective Tier is the project's where it names one, else the global Tier. Class
  Range, Gate, overflow (ticket 29) and tier leaders all read the effective Tier.
- Order: a Lane whose Tier the project changes has no global place in its new Tier. It
  sorts after the Lanes with a place unless the project's `project_order` places it.
  `project_order` is validated against effective Tiers.
- Focused edit: `catalog.py set lanes.<lane>.tier N --scope project` becomes legal, with
  the same preview, `--expect` revision and apply sequence. Setting the project Tier equal
  to the global Tier removes the entry; an empty document removes nothing else and writes
  no empty file.
- `catalog.py show` and the rank header say when a project Tier is in effect, and for
  which Lanes.
- The setup wizard stays global.

## Scope

Paths relative to `agents/skills/delegate/`: `scripts/catalog.py` (`load_catalog`,
validation, `edit_catalog`), `scripts/rank.py` only where it reads a Tier,
`tests/test_catalog.py`, `tests/test_rank.py`, `SKILL.md` (Files and Focused catalog
changes), the skill `CLAUDE.md`, and root `CONTEXT.md` (Tier, and the project override
entry). The root `CLAUDE.md` line "reorders them inside their global Tiers and never
changes a Tier" is corrected by the session at landing.

## Acceptance

**Status:** implemented 2026-09-18 (`0f76bac`) on `worktree/delegate-redesign`; all boxes ticked. The merge to `main` is Orin's, and the rule is a session decision he may overrule.

- [x] A fixture project that moves a Tier 3 Lane to Tier 2 makes it eligible for a
      Range 1–2 Class and not for a Range 3–3 Class; the same catalog with no project
      file ranks as before.
- [x] Unknown Lane, a field other than `tier`, and a Tier outside 1–4 each fail with a
      message naming the file, the field and the rule.
- [x] `project_order` works on a Lane in its project Tier; a moved Lane without a place
      sorts after the placed Lanes.
- [x] `catalog.py set lanes.<lane>.tier N --scope project` previews and applies, refuses
      a stale revision, writes only the project file, and removes an entry that equals
      the global Tier.
- [x] No test reads Orin's Tiers; every suite under `tests/` exits 0.

## Landed, 2026-09-18

`0f76bac`, by `opus-high@claude` (the ticket 31 worker, second job in the same worktree),
about 900 s, verdict clean. `catalog.validate_project_lanes()` validates the file,
`_effective_lanes()` applies the project Tier before the Order projection, the file is part
of the edit revision, and `rank.py` and `catalog.py show` print a `project tier` line.

Checked by the session: all 13 suites under `tests/` exit 0; live `rank.py scout` is
unchanged with no project file. The implementer's fixture session shows the preview, a
refused stale revision, the apply writing only `<project>/.delegate/lanes.json`, the Lane
eligible in a Range 1-2 Class and `vetoed:floor` in a Range 3-3 Class, and the entry removed
when the Tier is set back. Known cost: the private planners now return six items, which
broke three dashboard prototype tests on merge into the layouts branch; fixed there.
